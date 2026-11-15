"""Point predictions from SoilGrids WCS, kept separate from field measurements."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO

import httpx
from PIL import Image

SOURCE = "https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html"
WCS = "https://maps.isric.org/mapserv"
DEPTHS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100)]
PROPERTIES = {"sand": (10, 100), "silt": (10, 100), "clay": (10, 100),
              "phh2o": (10, 14), "soc": (10, 1000), "wv0033": (1000, .8), "wv1500": (1000, .8)}


def texture(sand, silt, clay):
    total = sand + silt + clay
    if not 95 <= total <= 105:
        return None
    sand, silt, clay = (x * 100 / total for x in (sand, silt, clay))
    if silt + 1.5 * clay < 15:
        return "Arenosa"
    if silt + 2 * clay < 30:
        return "Arenosa franca"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50):
        return "Franco arenosa"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "Franca"
    if silt >= 80 and clay < 12:
        return "Limosa"
    if silt >= 50 and clay < 27:
        return "Franco limosa"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "Franco arcillo arenosa"
    if 27 <= clay < 40 and sand <= 20:
        return "Franco arcillo limosa"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "Franco arcillosa"
    if clay >= 35 and sand > 45:
        return "Arcillo arenosa"
    if clay >= 40 and silt >= 40:
        return "Arcillo limosa"
    return "Arcillosa"


def pixel(client, lon, lat, prop, depth, stat):
    scale, limit = PROPERTIES[prop]
    try:
        params = {"map": f"/map/{prop}.map", "SERVICE": "WCS", "VERSION": "1.0.0",
                  "REQUEST": "GetCoverage", "COVERAGE": f"{prop}_{depth}cm_{stat}",
                  "CRS": "EPSG:4326", "RESPONSE_CRS": "EPSG:4326",
                  "BBOX": ",".join(f"{x:.7f}" for x in (lon-.001, lat-.001, lon+.001, lat+.001)),
                  "WIDTH": 1, "HEIGHT": 1, "FORMAT": "GEOTIFF_INT16"}
        res = client.get(WCS, params=params)
        res.raise_for_status()
        with Image.open(BytesIO(res.content), formats=["TIFF"]) as im:
            if im.size != (1, 1):
                return None
            value = im.getpixel((0, 0)) / scale
        return value if 0 <= value <= limit else None
    except (httpx.HTTPError, OSError, ValueError, TypeError):
        return None


def lookup(lon, lat):
    surface = [(p, "0-5", "mean") for p in ("sand", "silt", "clay", "phh2o", "soc")]
    interval = [("phh2o", "0-5", stat) for stat in ("Q0.05", "Q0.95")]
    retention = [(p, f"{a}-{b}", "mean") for a, b in DEPTHS for p in ("wv0033", "wv1500")]
    fields = surface + interval + retention
    # Bounded concurrency per request. The cache lives with the saved lot version.
    with httpx.Client(timeout=6) as client, ThreadPoolExecutor(max_workers=5) as pool:
        def read(args):
            return pixel(client, lon, lat, *args)

        values = dict(zip(fields, pool.map(read, fields)))
        missing = [args for args,value in values.items() if value is None]
        values.update(zip(missing, pool.map(read, missing)))
    top = {p:values[(p,d,s)] for p,d,s in surface}
    if not any(v is not None for v in top.values()):
        return None
    fractions = [top[x] for x in ("sand", "silt", "clay")]
    bounds = [values[k] for k in interval]
    layers = [dict(from_cm=a,to_cm=b,fc=values[("wv0033",f"{a}-{b}","mean")],
                   wp=values[("wv1500",f"{a}-{b}","mean")]) for a,b in DEPTHS]
    return dict(provider="ISRIC SoilGrids 2.0 · WCS", url=SOURCE, resolution_m=250,
                retrieved=datetime.now(timezone.utc).isoformat(), location=[lon,lat],
                coverage=sum(value is not None for value in values.values()),
                surface_cm=[0,5], surface=top,
                texture=texture(*fractions) if None not in fractions else None,
                ph_interval=bounds if None not in bounds and bounds[0] <= bounds[1] else None,
                retention=layers)


def retention_at_depth(profile, depth_m):
    if not profile or not depth_m or not 0 < depth_m <= 1:
        return None
    target = depth_m * 100
    capacity = wilting = covered = 0.
    for layer in profile["retention"]:
        weight = max(0., min(layer["to_cm"], target) - layer["from_cm"])
        if not weight:
            break
        fc, wp = layer["fc"], layer["wp"]
        if fc is None or wp is None or fc <= wp:
            return None
        capacity += fc * weight
        wilting += wp * weight
        covered += weight
    if abs(covered-target) > 1e-6:
        return None
    return dict(theta_fc=capacity/covered,theta_wp=wilting/covered)
