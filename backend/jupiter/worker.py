import json
import logging
import math
import os
import threading
import time

from .climate import (chunks, copy_rows, get_power, ingest_climate, inspect, keep_file, parse_date,
                      source_key)
from .db import STORAGE, engine, many, one, query
from .jobs import JobError, LeaseLost, claim, complete, fail, guard, renew
from .model import CROPS, run_model
from .catalog import CONTEXT
from .evidence import moisture
from .signals import environmental_signals, simulation_timeline
from .report import render
from .storage import persist, restore

LOG = logging.getLogger("jupiter.worker")

def stage_profile(conn, path, item):
    kind = item["kind"]
    query(conn, "CREATE TEMP TABLE stage_profile (row_no int, payload jsonb) ON COMMIT DROP")
    count = 0

    def profile_rows():
        nonlocal count
        for chunk in chunks(path, []):
            for row in chunk.to_dict("records"):
                count += 1
                try:
                    if row["field_id"] != str(item["field_id"]):
                        raise ValueError()
                    if kind == "soil":
                        parse_date(row["sampled_on"])
                        low, high = float(row["depth_from_cm"]), float(row["depth_to_cm"])
                        if not 0 <= low < high <= 1000:
                            raise ValueError()
                        row["depth_from_cm"], row["depth_to_cm"] = low, high
                        if not all(0 < len(row[k].strip()) <= 100 for k in ("sample_id","variable","value","unit","method")):
                            raise ValueError()
                        if row["variable"] != "texture" and not math.isfinite(float(row["value"])):
                            raise ValueError()
                    elif (row["crop_code"] not in CROPS.keys() | CONTEXT.keys() or len(row["cultivar"]) > 100 or
                          parse_date(row["planting_date"]) >= parse_date(row["harvest_date"])):
                        raise ValueError()
                    yield count+1,json.dumps(row)
                except (ValueError, TypeError) as exc:
                    raise JobError(f"Fila {count+1}: revisa lote, fecha, profundidad o valores del contrato.") from exc
    copy_rows(conn, "stage_profile", ["row_no","payload"], profile_rows())
    if not count:
        raise JobError("El CSV no contiene filas.")
    if kind == "soil":
        query(conn, """
          INSERT INTO soil_samples(import_id,field_id,sample_code,sampled_on,depth_from_cm,depth_to_cm)
          SELECT :i,:f,payload->>'sample_id',min((payload->>'sampled_on')::date),
            (payload->>'depth_from_cm')::real,(payload->>'depth_to_cm')::real
          FROM stage_profile GROUP BY 3,5,6
        """, i=item["id"], f=item["field_id"])
        bad = one(conn, """SELECT 1 FROM stage_profile GROUP BY payload->>'sample_id',
          payload->>'depth_from_cm', payload->>'depth_to_cm' HAVING count(DISTINCT payload->>'sampled_on')>1
            OR count(*)<>count(DISTINCT payload->>'variable') LIMIT 1""")
        if bad:
            raise JobError("Hay variables duplicadas o fechas inconsistentes para una muestra de suelo.")
        query(conn, """
          INSERT INTO soil_results(sample_id,variable,value,unit,method)
          SELECT s.id,p.payload->>'variable',p.payload->>'value',p.payload->>'unit',p.payload->>'method'
          FROM stage_profile p JOIN soil_samples s ON s.import_id=:i AND s.sample_code=p.payload->>'sample_id'
            AND s.depth_from_cm=(p.payload->>'depth_from_cm')::real AND s.depth_to_cm=(p.payload->>'depth_to_cm')::real
        """, i=item["id"])
    else:
        bad = one(conn, "SELECT 1 FROM stage_profile GROUP BY payload HAVING count(*)>1 LIMIT 1")
        if bad:
            raise JobError("El CSV contiene campañas duplicadas.")
        query(conn, """
          INSERT INTO campaigns(import_id,field_id,crop_code,cultivar,planting_date,harvest_date)
          SELECT :i,:f,payload->>'crop_code',payload->>'cultivar',(payload->>'planting_date')::date,
            (payload->>'harvest_date')::date FROM stage_profile
        """, i=item["id"], f=item["field_id"])
    return {"rows":count}

def do_import(job):
    with engine.begin() as conn:
        item = one(conn, """
            SELECT i.*,f.snapshot,d.storage_key,d.sha256,d.created
            FROM imports i JOIN field_versions f ON f.field_id=i.field_id AND f.version=i.field_version
            JOIN data_files d ON d.id=i.file_id WHERE i.id=:id
        """, id=job["target"])
        path = restore(conn, item["owner"], item["storage_key"])
        if item["kind"] == "climate":
            dataset = ingest_climate(conn,path,{"sha256":item["sha256"], "id":item["file_id"], "created":item["created"]},
                                     item["snapshot"]["lon"],item["snapshot"]["lat"],item["field_id"])
            summary = {**dataset["metadata"], "dataset_id":str(dataset["id"])}
        else:
            summary = stage_profile(conn,path,item)
        guard(conn,job)
        query(conn,"UPDATE imports SET summary=CAST(:s AS jsonb) WHERE id=:i",s=json.dumps(summary),i=item["id"])
        complete(conn,job)

def do_analysis(job, progress):
    with engine.connect() as conn:
        run = one(conn,"SELECT * FROM analysis_runs WHERE id=:id",id=job["target"])
    site = run["field_snapshot"]
    if site["multicell"]:
        raise JobError("Esta geometría requiere evaluación multicelda. Crea un punto exploratorio o divide el terreno.")
    key = source_key(site["lon"],site["lat"])
    with engine.connect() as conn:
        if run["dataset_id"]:
            dataset = one(conn,"SELECT id,metadata FROM datasets WHERE id=:i",i=run["dataset_id"])
        else:
            dataset = one(conn,"SELECT id,metadata FROM datasets WHERE cache_key=:k",k=key)
    if not dataset:
        path, temporary = get_power(site["lon"],site["lat"])
        try:
            with engine.begin() as conn:
                file = keep_file(conn,run["owner"],path)
                dataset = ingest_climate(conn,path,file,site["lon"],site["lat"],cache_key=key)
        finally:
            if temporary:
                path.unlink(missing_ok=True)
    progress(42)
    with engine.connect() as conn:
        rows = many(conn,"SELECT * FROM climate_daily WHERE dataset_id=:i ORDER BY date",i=dataset["id"])
        soil = many(conn, """
            SELECT s.sample_code,s.sampled_on,s.depth_from_cm,s.depth_to_cm,r.variable,r.value,r.unit,r.method
            FROM soil_samples s JOIN soil_results r ON r.sample_id=s.id
            JOIN imports i ON i.id=s.import_id WHERE s.field_id=:f AND i.field_version=:v AND i.created<=:cutoff
            ORDER BY s.sampled_on DESC,s.sample_code,s.depth_from_cm,r.variable LIMIT 100
        """, f=run["field_id"], v=run["field_version"], cutoff=run["input_cutoff"] or run["created"])
        campaigns = many(conn, """
            SELECT c.crop_code,c.cultivar,c.planting_date,c.harvest_date
            FROM campaigns c JOIN imports i ON i.id=c.import_id WHERE c.field_id=:f AND i.field_version=:v AND i.created<=:cutoff
            ORDER BY c.harvest_date DESC LIMIT 100
        """, f=run["field_id"], v=run["field_version"], cutoff=run["input_cutoff"] or run["created"])
    output, daily = run_model(rows,dataset["metadata"],site,run["inputs"],run["inputs"].get("regional_soil"))
    progress(82)
    output["moisture"] = moisture(site["lon"],site["lat"])
    output["environment"] = environmental_signals(rows,dataset["metadata"],site,output["elevation_m"],output["moisture"])
    for option in output["alternatives"]:
        option["timeline"] = simulation_timeline(daily[option["id"]])
    output.update(dataset_id=str(dataset["id"]),soil=soil,campaigns=campaigns)
    with engine.begin() as conn:
        guard(conn,job)
        query(conn,"UPDATE analysis_runs SET dataset_id=:d WHERE id=:i",d=dataset["id"],i=run["id"])
        query(conn,"""INSERT INTO results(run_id,model_version,output,daily)
            VALUES(:i,:v,CAST(:o AS jsonb),CAST(:d AS jsonb))""", i=run["id"],v=output["version"],
            o=json.dumps(output,default=str),d=json.dumps(daily))
        complete(conn,job)

def do_report(job, progress):
    with engine.connect() as conn:
        item = dict(one(conn, """
            SELECT r.*,a.field_snapshot,a.inputs,a.created AS run_created,x.output,x.daily
            FROM reports r JOIN analysis_runs a ON a.id=r.run_id JOIN results x ON x.run_id=a.id
            WHERE r.id=:i
        """,i=job["target"]))
    artifact, hashes = render(item,job["lease"],progress)
    try:
        with engine.begin() as conn:
            guard(conn,job)
            for filename in ("report.pdf", "metrics.csv", "daily.csv"):
                persist(conn, item["owner"], artifact + "/" + filename)
            query(conn,"""UPDATE reports SET artifact_key=:a,sha_pdf=:pdf,sha_csv=:csv,sha_daily=:daily
                WHERE id=:i""",a=artifact,i=item["id"],**hashes)
            complete(conn,job)
    except LeaseLost:
        import shutil
        shutil.rmtree(STORAGE / artifact)
        raise

def process(job):
    done, lost = threading.Event(), threading.Event()

    def progress(value=None):
        if lost.is_set():
            raise LeaseLost()
        with engine.begin() as conn:
            renew(conn,job,value)

    def heartbeat():
        while not done.wait(8):
            try:
                progress()
            except LeaseLost:
                lost.set()
                return
            except Exception as exc:
                LOG.warning("Heartbeat: %s",type(exc).__name__)

    thread = threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        if job["kind"] == "import":
            do_import(job)
        else:
            {"analysis":do_analysis,"report":do_report}[job["kind"]](job,progress)
    except LeaseLost:
        pass
    except JobError as exc:
        with engine.begin() as conn:
            fail(conn,job,exc)
    except Exception as exc:
        LOG.error("Trabajo %s (%s): %s",job["id"],job["kind"],type(exc).__name__)
        if os.getenv("JUPITER_DEV_LOG") == "1":
            LOG.exception("Diagnóstico del procesador")
        with engine.begin() as conn:
            fail(conn,job,JobError("El procesador encontró un error. Reintenta el trabajo.",True))
    finally:
        done.set()
        thread.join(timeout=2)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("Procesador de Júpiter Jr listo")
    while True:
        try:
            with engine.begin() as conn:
                job = claim(conn)
            if job:
                process(job)
            else:
                time.sleep(.7)
        except Exception as exc:
            LOG.error("Cola temporalmente inaccesible: %s",type(exc).__name__)
            time.sleep(3)

if __name__ == "__main__":
    main()
