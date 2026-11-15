"""Database-backed artifacts for hosts with an ephemeral filesystem."""
import hashlib
import os
from uuid import uuid4

from .db import STORAGE, one, query


def persist(conn, owner, key):
    if os.getenv("DATABASE_FILE_STORAGE") != "1":
        return
    content = (STORAGE / key).read_bytes()
    query(conn, """
        INSERT INTO stored_files(storage_key,owner,content,sha256)
        VALUES (:key,:owner,:content,:sha)
        ON CONFLICT(storage_key) DO UPDATE SET content=excluded.content,sha256=excluded.sha256
        WHERE stored_files.owner=excluded.owner
    """, key=key, owner=owner, content=content, sha=hashlib.sha256(content).hexdigest())


def restore(conn, owner, key):
    path = STORAGE / key
    if path.is_file():
        return path
    row = one(conn, "SELECT content,sha256 FROM stored_files WHERE storage_key=:key AND owner=:owner",
              key=key, owner=owner)
    if not row:
        return path
    content = bytes(row["content"])
    if hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise RuntimeError("Stored artifact failed its integrity check.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
