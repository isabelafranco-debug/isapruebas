import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
import json
import subprocess
from .db import ROOT

from fastapi import HTTPException, Request, Response
from .db import one, query

WINDOWS_PORTABLE = os.getenv("JUPITER_WINDOWS_PORTABLE") == "1"

if WINDOWS_PORTABLE:
    class NodePasswords:
        def hash(self, password, salt=None):
            proc = subprocess.run(
                ["node", str(ROOT / "scripts/argon2.mjs")],
                input=json.dumps(dict(password=password, salt=salt)),
                capture_output=True, text=True, check=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return proc.stdout.strip()

        def verify(self, encoded, password):
            return secrets.compare_digest(encoded, self.hash(password, encoded.split("$")[4]))

    PASSWORDS = NodePasswords()
else:
    from argon2 import PasswordHasher
    PASSWORDS = PasswordHasher()
DUMMY = PASSWORDS.hash(secrets.token_urlsafe(32))
COOKIE = "jupiter_session"
HTTPS = os.getenv("SECURE_COOKIES", "0") == "1"
ORIGINS = set(os.getenv("APP_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(","))
if not HTTPS and any(origin.split("://")[-1].split(":")[0] not in {"localhost","127.0.0.1"} for origin in ORIGINS):
    raise RuntimeError("Activa HTTPS para orígenes externos a loopback.")

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def session(conn, request, required=True):
    token = request.cookies.get(COOKIE, "")
    row = one(conn, """
      SELECT u.id,u.name,u.email,u.guide_seen,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
      WHERE token_hash=:h AND revoked IS NULL AND expires>now()
    """, h=digest(token)) if token else None
    if required and not row:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return row

def validate_origin(request: Request):
    if request.headers.get("origin") not in ORIGINS:
        raise HTTPException(403, "El origen de esta solicitud no está permitido.")

def authorize_write(request, user):
    validate_origin(request)
    token = request.headers.get("X-CSRF-Token", "")
    if not token.isascii() or not secrets.compare_digest(token, user["csrf"]):
        raise HTTPException(403, "La sesión de esta pestaña cambió. Recarga y repite la acción.")

def revoke(conn, request):
    token = request.cookies.get(COOKIE)
    if token:
        query(conn, "UPDATE sessions SET revoked=now() WHERE token_hash=:h", h=digest(token))

def start_session(conn, request: Request, response: Response, user):
    revoke(conn, request)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    query(conn, """INSERT INTO sessions(token_hash,user_id,csrf,expires)
                VALUES(:h,:o,:c,:e)""",
          h=digest(token), o=user["id"], c=csrf, e=datetime.now(timezone.utc)+timedelta(hours=24))
    response.set_cookie(COOKIE, token, max_age=86400, secure=HTTPS, httponly=True, samesite="strict")
    return {**dict(user), "csrf": csrf}

def limit(conn, request, email, action):
    peer = request.client.host if request.client else "loopback"
    counts = []
    for key, maximum in [(f"{action}:peer:{peer}", 45), (f"{action}:email:{email}", 8)]:
        row = one(conn, """
          INSERT INTO auth_limits(scope,attempts,resets) VALUES(:k,1,now()+interval '15 minutes')
          ON CONFLICT(scope) DO UPDATE SET attempts=CASE WHEN auth_limits.resets<now() THEN 1 ELSE auth_limits.attempts+1 END,
            resets=CASE WHEN auth_limits.resets<now() THEN excluded.resets ELSE auth_limits.resets END
          RETURNING attempts
        """, k=digest(key))
        counts.append(row["attempts"] > maximum)
    return any(counts)

def verify(password, user):
    try:
        return PASSWORDS.verify(user["password_hash"] if user else DUMMY, password) and user is not None
    except Exception as exc:
        if type(exc).__name__ != "VerifyMismatchError":
            raise
        return False
