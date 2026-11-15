import json
import logging
import os
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError

from . import auth
from .climate import CAMPAIGN, COLS, LIMIT, SOIL, inspect, keep_file
from .db import ROOT, STORAGE, engine, many, one, query
from .geometry import FIELD_COLUMNS, save_field, seed_pilot
from .jobs import JobError, enqueue
from .model import CROPS
from .catalog import CONTEXT, catalog
from .soil import lookup

LOG = logging.getLogger("jupiter.api")
app = FastAPI(title="Júpiter Jr", version="1.2.1", docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class Registration(Credentials):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class FieldInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    geometry: dict
    source: str = Field(default="dibujo manual", max_length=80)
    version: int | None = Field(default=None, ge=1)

class AnalysisInput(BaseModel):
    previous: str = Field(default="unknown", max_length=20)
    allowed_crops: list[str] | None = Field(default=None, min_length=3, max_length=len(CROPS))
    use_regional_soil: bool = False
    irrigation: str = Field(default="unknown", pattern="^(unknown|rainfed|confirmed)$")
    irrigation_mm: float | None = Field(default=None, ge=0, le=100)
    priority: str = Field(default="balanced", pattern="^(balanced|water|cover|diversity)$")
    elevation_m: float | None = Field(default=None, ge=-450, le=8000)
    theta_fc: float | None = Field(default=None, gt=0, le=.8)
    theta_wp: float | None = Field(default=None, ge=0, lt=.8)
    depth_m: float | None = Field(default=None, ge=.1, le=3)
    soil_ph: float | None = Field(default=None, ge=0, le=14)
    soil_ec: float | None = Field(default=None, ge=0, le=100)
    plant_month: int = Field(default=11, ge=1, le=12)
    plant_months: list[int] | None = Field(default=None, min_length=3, max_length=3)
    trial: bool = False
    rainfall_shift_pct: float = Field(default=-15, ge=-60, le=60)
    warming_c: float = Field(default=1, ge=-4, le=6)

    @field_validator("previous")
    @classmethod
    def previous_crop(cls, value):
        if value != "unknown" and value not in CROPS and value not in CONTEXT:
            raise ValueError("Cultivo desconocido")
        return value

    @field_validator("plant_months")
    @classmethod
    def campaign_months(cls, value):
        if value is not None and any(not 1 <= month <= 12 for month in value):
            raise ValueError("Selecciona un mes válido para cada campaña")
        return value

    @field_validator("allowed_crops")
    @classmethod
    def crop_selection(cls, value):
        if value is not None and (len(set(value)) != len(value) or not set(value) <= CROPS.keys()):
            raise ValueError("Selecciona cultivos válidos y distintos")
        return value

class ReportInput(BaseModel):
    rotation_id: str = Field(min_length=1, max_length=40)

def read_user(request: Request):
    with engine.connect() as conn:
        return dict(auth.session(conn, request))

def write_user(request: Request, user=Depends(read_user)):
    auth.authorize_write(request, user)
    return user

def owned(conn, table, ident, owner):
    row = one(conn, f"SELECT * FROM {table} WHERE id=:i AND owner=:o", i=ident, o=owner)
    if not row:
        raise HTTPException(404, "No encontramos este recurso en tu cuenta.")
    return row

@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc):
    fields = ", ".join(".".join(str(x) for x in e["loc"][1:]) for e in exc.errors())
    return JSONResponse({"detail": f"Revisa los datos de la solicitud ({fields or 'formato'})."}, status_code=422)

@app.exception_handler(JobError)
async def upload_error(_request, exc):
    return JSONResponse({"detail": exc.message}, status_code=422)

@app.exception_handler(Exception)
async def unexpected_error(_request, exc):
    LOG.error("Error de solicitud: %s", type(exc).__name__)
    return JSONResponse({"detail": "Ocurrió un error interno. Vuelve a intentar."}, status_code=500)

@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            one(conn, "SELECT revision.version_num FROM alembic_version revision")
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)

@app.post("/api/auth/register", status_code=201)
def register(body: Registration, request: Request, response: Response):
    auth.validate_origin(request)
    email = body.email.casefold()
    with engine.begin() as conn:
        limited = auth.limit(conn, request, email, "register")
    if limited:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos.")
    try:
        with engine.begin() as conn:
            user = one(conn, """INSERT INTO users(name,email,password_hash) VALUES(:n,:e,:p)
                    RETURNING id,name,email,guide_seen""", n=body.name, e=email, p=auth.PASSWORDS.hash(body.password))
            seed_pilot(conn, user["id"])
            return auth.start_session(conn, request, response, user)
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", "") == "23505":
            raise HTTPException(409, "Ese correo ya está registrado.") from exc
        raise

@app.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response):
    auth.validate_origin(request)
    email = body.email.casefold()
    with engine.begin() as conn:
        limited = auth.limit(conn, request, email, "login")
        user = one(conn, "SELECT id,name,email,password_hash,guide_seen FROM users WHERE email=:e", e=email)
    if limited:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos.")
    if not auth.verify(body.password, user):
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    with engine.begin() as conn:
        return auth.start_session(conn, request, response,
                                  {key: user[key] for key in ["id","name","email","guide_seen"]})

@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, user=Depends(write_user)):
    with engine.begin() as conn:
        auth.revoke(conn, request)
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE, secure=auth.HTTPS, httponly=True, samesite="strict")
    return response

@app.get("/api/me")
def me(user=Depends(read_user)):
    return user

@app.post("/api/me/guide", status_code=204)
def see_guide(user=Depends(write_user)):
    with engine.begin() as conn:
        query(conn, "UPDATE users SET guide_seen=true WHERE id=:i", i=user["id"])

@app.post("/api/me/guide/start")
def start_guide(user=Depends(write_user)):
    with engine.begin() as conn:
        claimed = one(conn, "UPDATE users SET guide_seen=true WHERE id=:i AND NOT guide_seen RETURNING id", i=user["id"])
    return {"show":bool(claimed)}

@app.get("/api/fields")
def fields(offset: int = 0, user=Depends(read_user)):
    with engine.connect() as conn:
        return many(conn, f"SELECT {FIELD_COLUMNS} FROM fields WHERE owner=:o ORDER BY updated DESC LIMIT 100 OFFSET :skip",
                    o=user["id"], skip=max(offset, 0))

@app.post("/api/fields", status_code=201)
def create_field(body: FieldInput, user=Depends(write_user)):
    with engine.begin() as conn:
        return save_field(conn, user["id"], body.name, body.geometry, body.source)

@app.get("/api/fields/{field_id}")
def field(field_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        row = one(conn, f"SELECT {FIELD_COLUMNS} FROM fields WHERE id=:f AND owner=:o", f=field_id, o=user["id"])
    if not row:
        raise HTTPException(404, "No encontramos este lote en tu cuenta.")
    return dict(row)

@app.patch("/api/fields/{field_id}")
def update_field(field_id: UUID, body: FieldInput, user=Depends(write_user)):
    with engine.begin() as conn:
        owned(conn, "fields", field_id, user["id"])
        return save_field(conn, user["id"], body.name, body.geometry, body.source, field_id=field_id, version=body.version)

@app.get("/api/templates/{kind}")
def template(kind: str):
    headers = {"climate":["date",*COLS], "soil":SOIL, "campaigns":CAMPAIGN}
    if kind not in headers:
        raise HTTPException(404, "Plantilla no disponible.")
    return PlainTextResponse(",".join(headers[kind])+"\n", media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="plantilla-{kind}.csv"'})

@app.get("/api/fields/{field_id}/imports")
def imports(field_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        owned(conn, "fields", field_id, user["id"])
        return many(conn, """
          SELECT i.id,i.kind,i.summary,i.created,j.id AS job_id,j.status,j.error
          FROM imports i JOIN jobs j ON j.target=i.id AND j.kind='import' WHERE i.field_id=:f AND i.owner=:o
          ORDER BY i.created DESC LIMIT 30
        """, f=field_id, o=user["id"])

@app.post("/api/fields/{field_id}/imports", status_code=202)
def import_file(field_id: UUID, kind: str = Form(), file: UploadFile = File(), user=Depends(write_user)):
    if kind not in {"climate","soil","campaigns"}:
        raise HTTPException(422, "Elige clima, suelo o campañas.")
    with engine.connect() as conn:
        current = owned(conn, "fields", field_id, user["id"])
        version = current["version"]
    incoming = STORAGE / "incoming"
    incoming.mkdir(exist_ok=True)
    temp = incoming / str(uuid4())
    try:
        with temp.open("xb") as out:
            total = 0
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > LIMIT:
                    raise HTTPException(413, "El CSV supera 20 MiB.")
                out.write(chunk)
        if not total:
            raise HTTPException(422, "El CSV está vacío.")
        _header, columns = inspect(temp, kind)
        with engine.begin() as conn:
            original = keep_file(conn, user["id"], temp)
            item = one(conn, """
                INSERT INTO imports(owner,field_id,field_version,file_id,kind) VALUES(:o,:f,:v,:a,:k)
                ON CONFLICT(owner,field_id,field_version,file_id,kind,contract) DO UPDATE SET kind=excluded.kind RETURNING id
            """, o=user["id"], f=field_id, v=version, a=original["id"], k=kind)
            task = enqueue(conn, user["id"], "import", item["id"], f"import:{item['id']}")
            return {**dict(task), "headers": columns}
    finally:
        temp.unlink(missing_ok=True)

@app.get("/api/crops")
def crops(user=Depends(read_user)):
    return catalog()

@app.get("/api/field-exposure")
def field_exposure(user=Depends(read_user)):
    with engine.connect() as conn:
        rows = many(conn,"""SELECT DISTINCT ON (f.id) f.id,f.name,ST_X(f.point) AS lon,ST_Y(f.point) AS lat,
          ST_AsGeoJSON(f.geom)::json AS geometry,a.id AS analysis_id,a.created,r.output
          FROM fields f LEFT JOIN analysis_runs a ON a.field_id=f.id AND a.field_version=f.version
          LEFT JOIN results r ON r.run_id=a.id
          WHERE f.owner=:o ORDER BY f.id,(r.run_id IS NOT NULL) DESC,a.created DESC LIMIT 100""",o=user["id"])
    fields = []
    for row in rows:
        output = row["output"] or {}
        selected = next(iter(output.get("alternatives",[])),{})
        historical = selected.get("metrics",{}).get("historical",{})
        duration = sum(crop["duration"] for crop in selected.get("calendar",[]))
        stress = historical.get("stress_days")
        fields.append({**{k:row[k] for k in ("id","name","lon","lat","geometry","analysis_id","created")},
                       "stress_pct":round(100*stress/duration,1) if stress is not None and duration else None,
                       "hot_days":historical.get("hot_days"),"frost_days":historical.get("frost_days"),
                       "support":output.get("source",{}).get("support"),"model":output.get("version")})
    return fields


@app.get("/api/fields/{field_id}/soil-profile")
def soil_profile(field_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        field = owned(conn,"fields",field_id,user["id"])
        entry = one(conn,"SELECT profile FROM regional_soil WHERE field_id=:i AND field_version=:v",
                    i=field_id,v=field["version"])
    return entry["profile"] if entry else None


@app.post("/api/fields/{field_id}/soil-profile")
def query_soil(field_id: UUID, user=Depends(write_user)):
    with engine.connect() as conn:
        field = owned(conn,"fields",field_id,user["id"])
        snapshot = one(conn,"SELECT snapshot FROM field_versions WHERE field_id=:i AND version=:v",
                       i=field_id,v=field["version"])["snapshot"]
        cached = one(conn,"SELECT profile FROM regional_soil WHERE field_id=:i AND field_version=:v",
                     i=field_id,v=field["version"])
    if cached and cached["profile"].get("coverage") == 17:
        return cached["profile"]
    if snapshot["multicell"]:
        raise HTTPException(422,"Usa un punto o un lote pequeño para consultar el perfil regional.")
    profile = lookup(snapshot["lon"],snapshot["lat"])
    if profile is None:
        if cached:
            return cached["profile"]
        raise HTTPException(503,"SoilGrids no entregó datos para este punto. Reintenta o usa observaciones del lote.")
    with engine.begin() as conn:
        row = one(conn,"""INSERT INTO regional_soil (field_id,field_version,profile) VALUES(:i,:v,CAST(:p AS jsonb))
          ON CONFLICT(field_id,field_version) DO UPDATE SET profile=CASE
            WHEN (excluded.profile->>'coverage')::int > coalesce((regional_soil.profile->>'coverage')::int,0)
            THEN excluded.profile ELSE regional_soil.profile END RETURNING profile""",
                  i=field_id,v=field["version"],p=json.dumps(profile))
    return row["profile"]


@app.post("/api/fields/{field_id}/analyses", status_code=202)
def analyze(field_id: UUID, body: AnalysisInput, user=Depends(write_user)):
    if body.theta_fc is not None and body.theta_wp is not None and body.theta_wp >= body.theta_fc:
        raise HTTPException(422, "La marchitez debe ser menor que la capacidad de campo.")
    if body.irrigation == "confirmed" and not body.irrigation_mm:
        raise HTTPException(422, "Indica la lámina diaria máxima de riego confirmada.")
    with engine.begin() as conn:
        current = owned(conn, "fields", field_id, user["id"])
        version = one(conn, "SELECT snapshot FROM field_versions WHERE field_id=:f AND version=:v",
                      f=field_id, v=current["version"])["snapshot"]
        soil = one(conn,"SELECT profile FROM regional_soil WHERE field_id=:i AND field_version=:v",
                   i=field_id,v=current["version"])
        if body.use_regional_soil:
            from .soil import retention_at_depth
            if (body.theta_fc is not None or body.theta_wp is not None or
                    not soil or retention_at_depth(soil["profile"],body.depth_m) is None):
                raise HTTPException(422,"Para usar la retención regional, indica una profundidad útil cubierta (hasta 1 m) y deja vacías la capacidad de campo y la marchitez.")
        dataset = one(conn, """
           SELECT (summary->>'dataset_id')::uuid AS id FROM imports
           WHERE field_id=:f AND field_version=:v AND kind='climate' AND summary IS NOT NULL
           ORDER BY created DESC LIMIT 1
        """, f=field_id, v=current["version"])
        inputs = {**body.model_dump(),"regional_soil":soil["profile"] if soil else None}
        run = one(conn, """
            INSERT INTO analysis_runs(owner,field_id,field_version,inputs,field_snapshot,dataset_id,input_cutoff)
            VALUES(:o,:f,:v,CAST(:i AS jsonb),CAST(:s AS jsonb),:dataset,now()) RETURNING id
        """, o=user["id"], f=field_id, v=current["version"], i=json.dumps(inputs),
               s=json.dumps(version), dataset=dataset["id"] if dataset else None)
        return dict(enqueue(conn, user["id"], "analysis", run["id"], f"analysis:{run['id']}"))

@app.get("/api/analyses")
def analyses(user=Depends(read_user)):
    with engine.connect() as conn:
        return many(conn, """
            SELECT a.id,a.field_id,a.created,a.field_snapshot->>'name' AS field_name,j.status,j.id AS job_id
            FROM analysis_runs a JOIN jobs j ON j.target=a.id AND j.kind='analysis'
            WHERE a.owner=:o ORDER BY a.created DESC LIMIT 50
        """, o=user["id"])

@app.get("/api/analyses/{run_id}")
def analysis(run_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        row = owned(conn, "analysis_runs", run_id, user["id"])
        output = one(conn, "SELECT output, model_version FROM results WHERE run_id=:r", r=run_id)
        return dict(id=row["id"], created=row["created"], field=row["field_snapshot"], inputs=row["inputs"],
                    result=output["output"] if output else None)

@app.get("/api/jobs/{job_id}")
def job(job_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        row = owned(conn, "jobs", job_id, user["id"])
        return {k: row[k] for k in ("id","target","kind","status","progress","attempts","error")}

@app.post("/api/jobs/{job_id}/{action}")
def job_action(job_id: UUID, action: str, user=Depends(write_user)):
    with engine.begin() as conn:
        owned(conn, "jobs", job_id, user["id"])
        if action == "cancel":
            query(conn, """UPDATE jobs SET cancel_requested=true,
                status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END
                WHERE id=:i AND status IN ('queued','running')""", i=job_id)
        elif action == "retry":
            query(conn, """UPDATE jobs SET status='queued', attempts=0,progress=0,error=NULL,
                available=now(),cancel_requested=false WHERE id=:i AND status IN ('failed','cancelled')""", i=job_id)
        else:
            raise HTTPException(404, "Acción desconocida.")
        return {"job_id": job_id}

@app.post("/api/analyses/{run_id}/reports", status_code=202)
def create_report(run_id: UUID, body: ReportInput, user=Depends(write_user)):
    with engine.begin() as conn:
        owned(conn, "analysis_runs", run_id, user["id"])
        result = one(conn, "SELECT output FROM results WHERE run_id=:r", r=run_id)
        if not result or body.rotation_id not in [record["id"] for record in result["output"]["alternatives"]]:
            raise HTTPException(422, "Selecciona una alternativa disponible en un análisis terminado.")
        row = one(conn, """
          INSERT INTO reports(owner,run_id,rotation_id,producer,template_version) VALUES(:o,:a,:rot,:p,2)
          ON CONFLICT(run_id,rotation_id,template_version) DO UPDATE SET rotation_id=excluded.rotation_id RETURNING id
        """, o=user["id"], a=run_id, rot=body.rotation_id, p=user["name"])
        return dict(enqueue(conn, user["id"], "report", row["id"], f"report:{row['id']}"))

@app.get("/api/reports")
def reports(user=Depends(read_user)):
    with engine.connect() as conn:
        return many(conn, """
           SELECT r.id,r.run_id,r.rotation_id,r.created,r.artifact_key IS NOT NULL AS ready,
             a.field_snapshot->>'name' AS field_name,j.status,j.id AS job_id
           FROM reports r JOIN analysis_runs a ON r.run_id=a.id JOIN jobs j ON j.target=r.id AND j.kind='report'
           WHERE r.owner=:o ORDER BY r.created DESC LIMIT 50
        """, o=user["id"])

@app.get("/api/reports/{report_id}")
def report(report_id: UUID, user=Depends(read_user)):
    with engine.connect() as conn:
        item = owned(conn, "reports", report_id, user["id"])
        return {k:item[k] for k in ("id","run_id","rotation_id","created","sha_pdf","sha_csv","sha_daily")}

@app.get("/api/reports/{report_id}/{format}")
def download(report_id: UUID, format: str, user=Depends(read_user)):
    files = {"pdf":("report.pdf","application/pdf"), "csv":("metrics.csv","text/csv"),
             "daily":("daily.csv","text/csv")}
    with engine.connect() as conn:
        item = owned(conn, "reports", report_id, user["id"])
    if format not in files or not item["artifact_key"]:
        raise HTTPException(404, "El archivo aún no está disponible.")
    source, media = files[format]
    from .storage import restore
    with engine.connect() as conn:
        path = restore(conn, user["id"], item["artifact_key"] + "/" + source)
    if not path.is_file():
        raise HTTPException(404, "El archivo no está disponible en el almacenamiento.")
    return FileResponse(path, media_type=media, filename=f"jupiter-{str(report_id)[:8]}-{source}")

if os.getenv("SERVE_WEB") == "1":
    dist = ROOT / "web/dist"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/regional/offline-sw.js", include_in_schema=False)
    def offline_worker():
        return FileResponse(dist / "regional/offline-sw.js", media_type="text/javascript",
                            headers={"Service-Worker-Allowed":"/", "Cache-Control":"no-cache"})

    app.mount("/regional", StaticFiles(directory=dist / "regional"), name="regional")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Ruta desconocida.")
        if path in {"agro-aerial.webp", "favicon.svg"} and (dist / path).is_file():
            return FileResponse(dist / path)
        return FileResponse(dist / "index.html", headers={"Cache-Control":"no-cache"})
