import csv
import hashlib
import json
import os
import re
import shutil
from itertools import batched
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pandas as pd

from .db import PILOT, PILOT_CSV, PILOT_SHA, PORTABLE, STORAGE, one, query
from .jobs import JobError

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER = dict(zip(
    "T2M T2M_MIN T2M_MAX RH2M WS2M ALLSKY_SFC_SW_DWN PRECTOTCORR".split(),
    "tmean_c tmin_c tmax_c rh_pct wind2m_ms solar_mj_m2_day precip_mm_day".split(),
))
COLS = list(POWER.values())
RANGES = [(-90, 65), (-95, 65), (-90, 75), (0, 100), (0, 100), (0, 65), (0, 2000)]
START, END = date(2015, 1, 1), date(2025, 12, 31)
CHUNK = max(1, int(os.getenv("CSV_CHUNK_SIZE", "10000")))
LIMIT = 20 * 1024 * 1024
SOIL = ["sample_id","field_id","sampled_on","depth_from_cm","depth_to_cm","variable","value","unit","method"]
CAMPAIGN = ["field_id","crop_code","cultivar","planting_date","harvest_date"]

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def is_pilot(lon, lat):
    return abs(lon - PILOT[0]) < 1e-8 and abs(lat - PILOT[1]) < 1e-8

def source_key(lon, lat):
    return f"POWER:AG:daily:UTC:{START}:{END}:{lon:.9f}:{lat:.9f}:" + ",".join(POWER)

def power_parameters(lon, lat):
    return dict(community="AG", latitude=f"{lat:.9f}", longitude=f"{lon:.9f}", start="20150101",
                end="20251231", format="CSV", parameters=",".join(POWER), **{"time-standard":"UTC"})

def get_power(lon, lat):
    if is_pilot(lon, lat) and PILOT_CSV.exists():
        if sha(PILOT_CSV) != PILOT_SHA:
            raise JobError("El archivo piloto no coincide con la copia verificada.")
        return PILOT_CSV, False
    folder = STORAGE / "incoming"
    folder.mkdir(exist_ok=True)
    path = folder / str(uuid4())
    try:
        with httpx.stream("GET", POWER_URL, params=power_parameters(lon, lat), timeout=35) as response:
            response.raise_for_status()
            with path.open("xb") as stream:
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > LIMIT:
                        raise JobError("La respuesta de NASA POWER excede el límite permitido.")
                    stream.write(chunk)
        return path, True
    except httpx.HTTPError as exc:
        path.unlink(missing_ok=True)
        raise JobError("NASA POWER no respondió para este punto. Reintenta o carga un CSV de clima propio.", True) from exc
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def inspect(path, kind):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            header = []
            first = stream.readline(8193)
            if len(first) > 8192:
                raise ValueError()
            line = first
            if first.strip() == "-BEGIN HEADER-" and kind == "climate":
                while line and line.strip() != "-END HEADER-" and len(header) < 128:
                    header.append(line.rstrip("\r\n"))
                    line = stream.readline(8193)
                    if len(line) > 8192:
                        raise ValueError()
                if line.strip() != "-END HEADER-":
                    raise ValueError()
                header.append("-END HEADER-")
                line = stream.readline(8193)
            cols = next(csv.reader([line]))
    except (UnicodeError, StopIteration, ValueError, csv.Error) as exc:
        raise JobError("CSV inválido. Usa UTF-8, coma, decimal con punto y fechas ISO.") from exc
    contracts = {"soil": SOIL, "campaigns": CAMPAIGN, "climate": ["date", *COLS]}
    required = ["YEAR","DOY",*POWER] if header else contracts[kind]
    if sorted(cols) != sorted(required):
        raise JobError("Encabezado esperado: " + ", ".join(required))
    return header, cols

def check_power(header, lon, lat):
    text = "\n".join(header)
    point = re.search(r"latitude\s+(-?[0-9.]+)\s+longitude\s+(-?[0-9.]+)", text, re.I)
    dates = re.search(r"Dates.*?: (\d\d/\d\d/\d{4}) through (\d\d/\d\d/\d{4}) in UTC", text)
    elevation = re.search(r"=\s*(-?[0-9.]+) meters", text, re.I)
    if not point or not dates:
        raise JobError("El encabezado POWER debe identificar coordenadas, fechas y estándar UTC.")
    if abs(float(point[1])-lat) > .000051 or abs(float(point[2])-lon) > .000051:
        raise JobError("Las coordenadas del archivo POWER no coinciden con el punto de este lote.")
    from datetime import datetime
    start, end = (datetime.strptime(dates[i], "%m/%d/%Y").date() for i in (1,2))
    solar = next((line for line in header if line.startswith("ALLSKY_SFC_SW_DWN")), "")
    rainfall = next((line for line in header if line.startswith("PRECTOTCORR")), "")
    if "mm/day" not in rainfall or not any(unit in solar for unit in ("MJ/m^2/day","kW-hr/m^2/day","kWh/m^2/day")):
        raise JobError("El encabezado POWER debe indicar radiación y precipitación con unidades reconocidas.")
    for variable, unit in zip(list(POWER)[:5], ("(C)", "(C)", "(C)", "(%)", "(m/s)")):
        if not any(re.match(rf"{variable}\s", line) and unit in line for line in header):
            raise JobError(f"Unidad POWER incompatible para {variable}.")
    return start, end, 1 if "MJ/m^2/day" in solar else 3.6, float(elevation[1]) if elevation else None

def chunks(path, header, size=None):
    try:
        yield from pd.read_csv(path, encoding="utf-8-sig", skiprows=len(header), dtype=str,
                               keep_default_na=False, chunksize=size or CHUNK, index_col=False,
                               on_bad_lines="error")
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise JobError("No se pudo leer el CSV. Revisa codificación, columnas y delimitadores.") from exc

def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError()
    return date.fromisoformat(value)

def daily_rows(path, header, factor, size=None):
    row_number = 1 + len(header)
    for chunk in chunks(path, header, size):
        for raw in chunk.to_dict("records"):
            row_number += 1
            try:
                if header:
                    y, doy = int(raw["YEAR"]), int(raw["DOY"])
                    when = date(y, 1, 1) + timedelta(days=doy - 1)
                    if when.year != y:
                        raise ValueError()
                    values = [raw[col] for col in POWER]
                else:
                    when = parse_date(raw["date"])
                    values = [raw[col] for col in COLS]
                vals = [None if v.strip() in {"","-999","-999.0","-999.00"} else float(v) for v in values]
                if vals[5] is not None:
                    vals[5] *= factor
                if any(v is not None and not low <= v <= high for v, (low, high) in zip(vals, RANGES)):
                    raise ValueError()
                if all(v is not None for v in vals[:3]) and not vals[1] <= vals[0] <= vals[2]:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError) as exc:
                raise JobError(f"Fila {row_number}: fecha o valor fuera del formato o rango climático.") from exc
            yield (when, *vals, "incomplete" if None in vals else "ok")

def keep_file(conn, owner, path):
    from .storage import persist
    digest = sha(path)
    key = f"originals/{owner}/{digest}.csv"
    dest = STORAGE / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        staging = dest.with_name(f"{digest}.{uuid4()}.tmp")
        try:
            shutil.copyfile(path, staging)
            staging.replace(dest)
        finally:
            staging.unlink(missing_ok=True)
    row = one(conn, """INSERT INTO data_files(owner,storage_key,sha256,bytes) VALUES(:o,:k,:s,:b)
        ON CONFLICT(owner,sha256) DO UPDATE SET sha256=excluded.sha256 RETURNING *""",
              o=owner, k=key, s=digest, b=path.stat().st_size)
    persist(conn, owner, key)
    return dict(row)

def copy_rows(conn, table, columns, rows):
    names = ",".join(columns)
    with conn.connection.driver_connection.cursor() as cursor:
        if PORTABLE:
            # PGlite's network adapter supports ordinary statements. Keep the
            # same bounded staging and publication behavior using batch inserts.
            row_sql = "(" + ",".join(["%s"] * len(columns)) + ")"
            for batch in batched(rows,200):
                cursor.execute(f"INSERT INTO {table} ({names}) VALUES "+",".join([row_sql]*len(batch)),
                               tuple(value for row in batch for value in row))
        else:
            with cursor.copy(f"COPY {table} ({names}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)


def ingest_climate(conn, path, file, lon, lat, field_id=None, cache_key=None):
    if cache_key:
        query(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:k,0))", k=cache_key)
        existing = one(conn, "SELECT id,metadata FROM datasets WHERE cache_key=:k", k=cache_key)
        if existing:
            return dict(existing)
    header, _ = inspect(path, "climate")
    start, end, factor, elevation = check_power(header, lon, lat) if header else (None,None,1,None)
    query(conn, """CREATE TEMP TABLE stage_climate
        (LIKE climate_daily INCLUDING DEFAULTS) ON COMMIT DROP""")
    placeholder = uuid4()
    rows = ((placeholder, *row) for row in daily_rows(path, header, factor))
    copy_rows(conn, "stage_climate", ["dataset_id","date",*COLS,"qc_flag"], rows)
    stats = one(conn, """
      SELECT min(date) AS start,max(date) AS end,count(*) AS rows,count(DISTINCT date) AS distinct,
        count(*) FILTER(WHERE qc_flag<>'ok') AS incomplete, avg(tmean_c) AS mean_temp
      FROM stage_climate
    """)
    if not stats["rows"]:
        raise JobError("El CSV no tiene observaciones.")
    if stats["rows"] != stats["distinct"]:
        raise JobError("El CSV contiene fechas duplicadas, incluso entre bloques.")
    start, end = start or stats["start"], end or stats["end"]
    expected = (end-start).days + 1
    if not 0 < expected <= 40000 or stats["start"] < start or stats["end"] > end:
        raise JobError("Las fechas del CSV quedan fuera del intervalo declarado o permitido.")
    missing = expected - stats["rows"]
    full_year_mean = one(conn, """
        SELECT avg(total) AS mean FROM (
          SELECT extract(year FROM date)::int AS yr, sum(precip_mm_day) AS total
          FROM stage_climate GROUP BY yr
          HAVING count(precip_mm_day) = make_date(extract(year FROM date)::int+1,1,1)
                                       - make_date(extract(year FROM date)::int,1,1)
        ) AS annual
    """)["mean"]
    meta = dict(product="NASA POWER Daily · AG" if header else "CSV del productor",
                source_class="estimado por la fuente" if header else "declarado por el productor",
                source_url=POWER_URL if header else None, point=[lon,lat], start=start.isoformat(),
                end=end.isoformat(), time_standard="UTC" if header else "día civil declarado",
                header=header, input_solar_unit="MJ/m²/día" if factor == 1 else "kWh/m²/día",
                units=dict(zip(COLS,["°C","°C","°C","%","m/s","MJ/m²/día","mm/día"])),
                variables=list(POWER) if header else COLS,
                support="MERRA-2 0,5° × 0,625°; CERES aprox. 1°" if header else "punto del lote declarado al importar",
                version=None, rows=stats["rows"], missing_days=missing, incomplete_days=stats["incomplete"],
                mean_temp_c=stats["mean_temp"], mean_annual_rain_mm=full_year_mean, elevation_m=elevation,
                sha256=file["sha256"], recorded=file["created"].isoformat())
    if cache_key and (start != START or end != END or missing):
        raise JobError("NASA POWER devolvió una serie fuera del intervalo esperado o con días ausentes.", True)
    row = one(conn, """INSERT INTO datasets(cache_key,field_id,file_id,metadata)
        VALUES(:k,:f,:a,CAST(:m AS jsonb)) RETURNING id,metadata""",
        k=cache_key, f=field_id, a=file["id"], m=json.dumps(meta))
    query(conn, """INSERT INTO climate_daily SELECT :ds,date,tmean_c,tmin_c,tmax_c,rh_pct,
                wind2m_ms,solar_mj_m2_day,precip_mm_day,qc_flag FROM stage_climate""", ds=row["id"])
    return dict(row)
