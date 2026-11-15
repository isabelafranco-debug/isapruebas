"""Build a province basemap and a Bolivian administrative search index from geoBoundaries ADM1–3."""
import json
from pathlib import Path
import sys


PROVINCES = set("Andrés Ibáñez|Angel Sandoval|Chiquitos|Cordillera|Florida|Germán Busch|Guarayos|Ichilo|Manuel María Caballero|Ñuflo De Chávez|Obispo Santistéban|Sara|Vallegrande|Velasco|Warnes".split("|"))
ROOT = Path(__file__).resolve().parents[1]


def polygons(feature):
    geometry = feature["geometry"]
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def extent(feature):
    points = [p for polygon in polygons(feature) for p in polygon[0]]
    x, y = zip(*points)
    return [min(x), min(y), max(x), max(y)]


def crossings(rings, y):
    return sorted(x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                  for ring in rings for (x1, y1), (x2, y2) in zip(ring, ring[1:])
                  if (y1 > y) != (y2 > y))


def representative(feature, bounds):
    _, ymin, _, ymax = bounds
    candidates = []
    for fraction in (.3, .4, .5, .6, .7):
        y = ymin + fraction * (ymax - ymin)
        for polygon in polygons(feature):
            x = crossings(polygon, y)
            candidates.extend((b - a, (a + b) / 2, y) for a, b in zip(x[::2], x[1::2]))
    _, x, y = max(candidates)
    return [x, y]


def main(directory):
    output = ROOT / "web/public/regional"
    output.mkdir(exist_ok=True)
    region, places, features = None, [], []
    for level, label in enumerate(("Departamento", "Provincia", "Municipio"), 1):
        data = json.loads((directory / f"ADM{level}.json").read_bytes())
        for feature in data["features"]:
            props = feature["properties"]
            name = props["shapeName"]
            bounds = extent(feature)
            center = representative(feature, bounds)
            if level == 1 and name == "Santa Cruz":
                region = feature
            regional = ((level == 1 and name == "Santa Cruz") or (level == 2 and name in PROVINCES))
            if level == 3:
                regional = any(a <= center[0] <= b for x in polygons(region)
                               for sides in [crossings(x, center[1])] for a, b in zip(sides[::2], sides[1::2]))
            places.append(dict(id=props["shapeID"], name=name, kind=label, regional=regional,
                               center=center, bounds=bounds))
            if regional and level == 2:
                features.append(dict(type="Feature", geometry=feature["geometry"], properties={"name": name, "kind": "province"}))
            if regional and level > 1:
                geometry = dict(type="Point", coordinates=center)
                features.append(dict(type="Feature", geometry=geometry,
                                     properties={"name": name, "kind": "label" if level == 2 else "municipality"}))
    alias = next(p for p in places if p["kind"] == "Municipio" and p["name"] == "Santa Cruz de la Sierra")
    alias["aliases"] = "Santa Cruz de la Sierra capital"
    for name, data in (("places.json", places), ("santa-cruz.geojson", dict(type="FeatureCollection", features=features))):
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        (output / name).write_text(content, encoding="utf-8")
    print(len(places), len([f for f in features if f['properties']['kind'] == 'province']))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
