import json
import math
from fastapi import HTTPException
from .db import PILOT, one, query

FIELD_COLUMNS = """id, name, version, pilot, source, area_ha, multicell, updated,
 ST_AsGeoJSON(geom,9)::jsonb AS geometry, ST_X(point) AS lon, ST_Y(point) AS lat"""

def validate_geometry(value):
    def reject():
        raise HTTPException(422, "Revisa las coordenadas, los anillos y el número de vértices del terreno.")

    kind = value.get("type")
    coords = value.get("coordinates")
    if kind not in {"Point", "Polygon", "MultiPolygon"} or not isinstance(coords, (list, tuple)):
        reject()
    if kind == "Point":
        vertices = [coords]
    else:
        polygons = [coords] if kind == "Polygon" else coords
        vertices = []
        if not polygons:
            reject()
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                reject()
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    reject()
                vertices.extend(ring)
    if not vertices or len(vertices) > 2000:
        reject()
    for point in vertices:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            reject()
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in point):
            reject()
        if not (-180 <= point[0] <= 180 and -89.9 <= point[1] <= 89.9):
            reject()
    return json.dumps({"type": kind, "coordinates": coords})

def save_field(conn, owner, name, geometry, source, field_id=None, pilot=False, version=None):
    geo = validate_geometry(geometry)
    check = one(conn, """
        WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326) AS geom)
        SELECT ST_IsValid(geom) AS valid,
          ST_XMax(geom)-ST_XMin(geom) AS span,
          CASE WHEN ST_IsValid(geom) AND GeometryType(geom)<>'POINT'
               THEN ST_Area(geom::geography)/10000 END AS area,
          CASE WHEN ST_IsValid(geom) AND GeometryType(geom)<>'POINT'
               THEN ST_MaxDistance(geom,geom)>0.05 ELSE false END AS multicell
        FROM g
    """, geo=geo)
    if not check["valid"] or check["span"] > 180 or (check["area"] is not None and not 0 < check["area"] <= 1000000):
        raise HTTPException(422, "El perímetro se cruza, tiene superficie cero o excede los límites admitidos.")
    params = dict(owner=owner, name=name, geo=geo, source=source, area=check["area"], multicell=check["multicell"])
    if field_id is None:
        farm = one(conn, """INSERT INTO farms(owner,name) VALUES (:owner,'Mi finca')
                    ON CONFLICT(owner,name) DO UPDATE SET name=excluded.name RETURNING id""", owner=owner)
        row = one(conn, f"""
            INSERT INTO fields(owner,farm_id,name,geom,point,area_ha,multicell,pilot,source)
            SELECT :owner,:farm,:name,g,ST_PointOnSurface(g),:area,:multicell,:pilot,:source
            FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326) AS g) AS ge
            RETURNING {FIELD_COLUMNS}
        """, **params, farm=farm["id"], pilot=pilot)
    else:
        row = one(conn, f"""
            UPDATE fields SET name=:name, geom=g, point=ST_PointOnSurface(g), source=:source,
              area_ha=:area, multicell=:multicell, version=version+1, updated=now()
            FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326) AS g) AS ge
            WHERE id=:field AND owner=:owner AND version=:version RETURNING {FIELD_COLUMNS}
        """, **params, field=field_id, version=version)
        if row is None:
            raise HTTPException(409, "El lote cambió. Vuelve a abrirlo antes de guardar.")
    snapshot = dict(row)
    query(conn, """INSERT INTO field_versions(field_id,version,snapshot)
      VALUES (:f,:v,CAST(:s AS jsonb))""", f=row["id"], v=row["version"], s=json.dumps(snapshot, default=str))
    return snapshot

def seed_pilot(conn, owner):
    return save_field(conn, owner, "PT_priner lote", {"type": "Point", "coordinates": PILOT},
                      "punto piloto de referencia", pilot=True)
