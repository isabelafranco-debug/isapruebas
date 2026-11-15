"""Explain observations, simulation and unverified agronomic considerations."""
import calendar
import json
from collections import defaultdict
from functools import lru_cache
from statistics import mean, median

import httpx
import numpy as np

from .climate import POWER_URL, is_pilot, power_parameters
from .db import ROOT
from .model import et0

MOISTURE_SOURCE = "https://power.larc.nasa.gov/docs/methodology/data/sources_hydrology/"
NRCS = "https://www.nrcs.usda.gov/conservation-basics/soil/soil-health/soil-health-on-cropland"
PRIORITIES = {"balanced":"equilibrio entre agua, cobertura y diversidad", "water":"menor déficit hídrico",
              "cover":"mayor cobertura", "diversity":"diversidad de familias"}


def climate_indicators(rows, latitude, elevation):
    years = defaultdict(list)
    for row in rows:
        years[row["date"].year].append(row)
    annual = []
    for year, data in sorted(years.items()):
        if len(data) != 365 + calendar.isleap(year) or any(
                r[k] is None for r in data for k in ("tmin_c","tmax_c","tmean_c","precip_mm_day")):
            continue
        demands = et0(data,latitude,elevation) if elevation is not None else []
        rain = round(sum(r["precip_mm_day"] for r in data), 1)
        demand = round(float(np.sum(demands)), 1) if len(demands) and np.isfinite(demands).all() else None
        annual.append(dict(year=year,rain_mm=rain,et0_mm=demand, balance_mm=round(rain-demand,1) if demand is not None else None,
                           temp_c=round(mean(r["tmean_c"] for r in data),2),
                           frost_days=sum(r["tmin_c"] <= 0 for r in data), hot_days=sum(r["tmax_c"] >= 35 for r in data)))
    return annual


@lru_cache(maxsize=32)
def moisture(lon, lat):
    try:
        if is_pilot(lon, lat):
            response = json.loads((ROOT / "data/reference/NASA_POWER_PT_priner_GWET_2015_2025.json").read_bytes())
        else:
            params = {**power_parameters(lon,lat),"format":"JSON","parameters":"GWETTOP,GWETROOT"}
            result = httpx.get(POWER_URL,params=params,timeout=10)
            result.raise_for_status()
            response = result.json()
        series = response["properties"]["parameter"]
        months = defaultdict(list)
        for date, value in series["GWETROOT"].items():
            if isinstance(value,(int,float)) and 0 <= value <= 1:
                months[date[:6]].append(value)
        complete = {month:mean(values) for month,values in months.items()
                    if len(values) == calendar.monthrange(int(month[:4]),int(month[4:]))[1]}
        season = []
        for month in range(1,13):
            history = [val for key,val in complete.items() if int(key[4:]) == month]
            season.append(round(median(history)*100,1) if len(history) >= 5 else None)
        anomalies = []
        for key,value in sorted(complete.items()):
            base = season[int(key[4:])-1]
            if base is not None:
                anomalies.append(dict(month=f"{key[:4]}-{key[4:]}",wetness=round(value*100,1),
                                      anomaly=round(value*100-base,1)))
        if not anomalies:
            return None
        return dict(source="NASA POWER · MERRA-2 GWETROOT",url=MOISTURE_SOURCE,monthly=anomalies,
                    normal=season,support="Regional · 0,5° × 0,625° · 2015–2025 · UTC")
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
        return None


def recommendation(record, reference, assumed, regional, priority):
    historic, sensitivity = (record["metrics"][k] for k in ("historical","sensitivity"))
    reasons = [f"Puntuación {record['score']:.1f}/100 con prioridad de {PRIORITIES[priority]}. "
               f"Cobertura media simulada: {historic['cover_pct']:.1f} %. "
               f"Cambios de familia: {round(record['diversity']*2)} de 2 transiciones."]
    if historic["deficit_mm"] is None:
        title = "Completa los datos para evaluar esta alternativa"
        reasons.append("Falta evidencia para comparar el uso de agua. La puntuación solo usa cobertura y diversidad.")
    else:
        title = "Alternativa para explorar" if assumed or regional else "Alternativa para validar en el lote"
        reasons.append(f"Déficit medio: {historic['deficit_mm']:.1f} mm en {len(historic['windows'])} ventanas de tres campañas. "
                       f"En sensibilidad: {sensitivity['deficit_mm']:.1f} mm. "
                       f"Rango histórico: {historic['deficit_range'][0]:.1f}–{historic['deficit_range'][1]:.1f} mm.")
        if reference and reference["metrics"]["historical"]["deficit_mm"] is not None:
            difference = historic["deficit_mm"] - reference["metrics"]["historical"]["deficit_mm"]
            comparison = f"{abs(difference):.1f} mm {'más' if difference > 0 else 'menos'} que la referencia" if difference else "Igual a la referencia"
            reasons.append(comparison + " en déficit medio del histórico.")
        reasons.append(f"Durante el cultivo se estiman {historic['hot_days']:.1f} días con máxima ≥35 °C y "
                       f"{historic['frost_days']:.1f} con mínima ≤0 °C por ventana. "
                       f"El calendario deja {historic['fallow_days']:.0f} días fuera de cultivo simulado.")
    if "Fabaceae" in record["families"]:
        reasons.append("Las leguminosas pueden fijar nitrógeno con nodulación efectiva. Revisa inoculación, rastrojo y análisis de nutrientes antes de ajustar fertilización.")
    if "cover" in record["crops"] or "cowpea" in record["crops"]:
        reasons.append("Las leguminosas de cobertura aportan residuos. Valida su terminación para proteger el suelo y gestionar el consumo de agua.")
    if record["diversity"]:
        reasons.append("Alternar familias puede interrumpir ciclos de plagas específicas. Confirma hospedantes y antecedentes sanitarios.")
    if any(code in record["crops"] for code in ("wheat","sunflower","sesame","sorghum","maize")):
        reasons.append("El catálogo incluye raíces profundas en parte de la secuencia. Confirma profundidad útil y capas compactadas; el modelo limita la raíz al perfil declarado.")
    if "sorghum" in record["crops"]:
        reasons.append("Si buscas forraje, confirma cultivar de sorgo, manejo y demanda con el comprador o tu equipo ganadero.")
    if "cassava" in record["crops"] or "potato" in record["crops"] or "sweetpotato" in record["crops"]:
        reasons.append("La cosecha de raíces y tubérculos remueve el suelo. Planifica rastrojo, tránsito y cobertura posterior para reducir exposición a lluvia y erosión.")
    if "potato" in record["crops"] or "tomato" in record["crops"]:
        reasons.append("Valida la aptitud térmica y altitud para la horticultura de tu zona. Tomate y papa comparten familia y pueden compartir problemas sanitarios.")
    if assumed or regional:
        reasons.append("Verifica retención y profundidad con muestras locales antes de decidir la siembra.")
    return dict(title=title,reasons=reasons,source=NRCS,
                check="Confirma ventana de siembra, cultivar, sanidad, disponibilidad de maquinaria, comprador y costos. El modelo no estima ingresos, erosión ni rendimiento.")
