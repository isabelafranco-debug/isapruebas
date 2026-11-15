"""Monthly point-support alignment and descriptive, reproducible comparisons."""
import calendar
from collections import defaultdict
from statistics import mean, median

import numpy as np

from .model import et0


def trend(points, label, unit):
    valid = [(float(x),float(y)) for x,y in points if y is not None]
    if len(valid) < 5:
        return None
    x,y = np.array(valid).T
    slope,intercept = np.polyfit(x-x[0],y,1)
    residual = y-(intercept+slope*(x-x[0]))
    total = float(np.sum((y-y.mean())**2))
    pairs = [(y[j]-y[i])/(x[j]-x[i]) for i in range(len(x)) for j in range(i+1,len(x)) if x[j]!=x[i]]
    return dict(label=label,unit=unit,n=len(x),start=int(x[0]),end=int(x[-1]),
                ols_decade=round(float(slope)*10,3),sen_decade=round(float(median(pairs))*10,3),
                r2=round(max(0,1-float(np.sum(residual**2))/total),3) if total else 0)


def correlation(months, first, second, label):
    pairs = [(m[first],m[second]) for m in months if m[first] is not None and m[second] is not None]
    if len(pairs) < 12:
        return None
    a,b = np.array(pairs).T
    value = float(np.corrcoef(a,b)[0,1]) if a.std() and b.std() else None
    return dict(label=label,n=len(pairs),r=round(value,3) if value is not None else None)


def environmental_signals(rows, source, site, elevation, moisture):
    grouped = defaultdict(list)
    demand = et0(rows,site["lat"],elevation) if elevation is not None else np.full(len(rows),np.nan)
    for row,reference in zip(rows,demand):
        grouped[row["date"].strftime("%Y-%m")].append((row,reference))
    wetness = {m["month"]:m for m in moisture["monthly"]} if moisture else {}
    months = []
    for key,data in sorted(grouped.items()):
        year,month = map(int,key.split("-"))
        complete = len(data)==calendar.monthrange(year,month)[1]
        rains = [r["precip_mm_day"] for r,_ in data]
        temps = [r["tmean_c"] for r,_ in data]
        evaporation = [d for _,d in data]
        rain = round(sum(rains),1) if complete and None not in rains else None
        temp = round(mean(temps),2) if complete and None not in temps else None
        reference = round(float(np.sum(evaporation)),1) if complete and np.isfinite(evaporation).all() else None
        balance = round(rain-reference,1) if rain is not None and reference is not None else None
        observed = wetness.get(key,{})
        months.append(dict(month=key,rain_mm=rain,temp_c=temp,et0_mm=reference,balance_mm=balance,
                           wetness=observed.get("wetness"),anomaly=observed.get("anomaly"),
                           phase="Oferta menor que demanda" if balance is not None and balance<0 else
                                 "Oferta igual o mayor que demanda" if balance is not None else "Datos incompletos"))
    annual = defaultdict(list)
    for month in months:
        annual[int(month["month"][:4])].append(month)
    trends = []
    for key,label,unit,aggregation in [
        ("rain_mm","Precipitación","mm/década",sum),
        ("temp_c","Temperatura media","°C/década",mean),
        ("anomaly","Anomalía de humedad radicular","puntos porcentuales/década",mean),
    ]:
        points = [(year,aggregation([m[key] for m in data])) for year,data in sorted(annual.items())
                  if len(data)==12 and all(m[key] is not None for m in data)]
        result = trend(points,label,unit)
        if result:
            trends.append(result)
    relationships = [correlation(months,"rain_mm","wetness","Lluvia y humedad radicular"),
                     correlation(months,"temp_c","et0_mm","Temperatura y ET₀")]
    return dict(monthly=months,trends=trends,correlations=[r for r in relationships if r],
                alignment="Meses completos UTC vinculados al punto representativo del lote. Las propiedades de suelo se conservan como perfil estático por profundidad.",
                support=source["support"],
                method="Se agregan totales de lluvia y ET₀, y medias de temperatura y humedad. Se conservan valores faltantes y escalas nativas. La asociación por punto conserva el soporte regional.",
                uncertainty="OLS y Theil–Sen describen la serie disponible. Once años permiten explorar cambios recientes. La estacionalidad puede influir en las correlaciones mensuales. Valida tendencias y microclimas con series más largas y estaciones locales.")


def simulation_timeline(daily):
    result = {}
    for scenario,rows in daily.items():
        groups = defaultdict(list)
        for row in rows:
            groups[row[0][:7]].append(row)
        result[scenario] = [dict(month=key,deficit_mm=round(sum(r[6] for r in data),1),
                                 stress_days=sum(r[6]>.1 for r in data),
                                 fallow_days=sum(r[1]=="fallow" for r in data),
                                 rain_mm=round(sum(r[2] for r in data),1),
                                 demand_mm=round(sum(r[4] for r in data),1),
                                 actual_mm=round(sum(r[5] for r in data),1),
                                 irrigation_mm=round(sum(r[8] for r in data),1))
                             for key,data in sorted(groups.items())]
    return result
