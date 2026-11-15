import calendar
from datetime import date, timedelta
from itertools import product

import numpy as np

from .climate import COLS
from .jobs import JobError

VERSION = "water-balance-1.2.0"
CATALOG_VERSION = "fao56-regional-3"
FAO = "https://www.fao.org/4/x0490e/x0490e00.htm"
# FAO 56 tables 11, 12, 22 and 23 provide reference coefficients and ranges.
# The calendar and crop cover assumptions require local cultivar calibration.
CROPS = {
    "soy": dict(name="Soya", family="Fabaceae", days=[20,30,55,25], kc=[.4,1.15,.5],
                root=.8, p=.5, window=[10,11,12,1], ph=[5.5,7.8], ec=5, cover=.86),
    "maize": dict(name="Maíz", family="Poaceae", days=[25,35,50,30], kc=[.3,1.2,.35],
                  root=1.1, p=.55, window=[9,10,11,12,1], ph=[5.5,7.8], ec=1.7, cover=.83),
    "sorghum": dict(name="Sorgo", family="Poaceae", days=[20,30,45,25], kc=[.3,1.05,.55],
                    root=1.2, p=.55, window=[10,11,12,1,2], ph=[5.5,8.3], ec=6.8, cover=.79),
    "cover": dict(name="Cobertura (mucuna)", family="Fabaceae", days=[20,30,30,15], kc=[.3,.95,.55],
                  root=.5, p=.5, window=[10,11,12,1,2], ph=[5,7.8], ec=None, cover=.93),
    "bean": dict(name="Frejol seco", family="Fabaceae", days=[20,30,40,20], kc=[.4,1.15,.35],
                 root=.75,p=.45,window=[4,5,10,11],ph=None,ec=1.,cover=.80),
    "peanut": dict(name="Maní", family="Fabaceae", days=[25,35,45,25], kc=[.4,1.15,.60],
                   root=.75,p=.50,window=[10,11,12,1],ph=None,ec=3.2,cover=.82),
    "sesame": dict(name="Sésamo", family="Pedaliaceae", days=[20,30,40,20], kc=[.35,1.10,.25],
                   root=1.25,p=.60,window=[11,12,1],ph=None,ec=None,cover=.65),
    "sunflower": dict(name="Girasol", family="Asteraceae", days=[25,35,45,25], kc=[.35,1.10,.35],
                      root=1.15,p=.45,window=[4,5,6],ph=None,ec=None,cover=.78),
    "wheat": dict(name="Trigo de primavera", family="Poaceae", days=[20,30,60,40], kc=[.30,1.15,.30],
                  root=1.25,p=.55,window=[5,6,7],ph=None,ec=6.,cover=.80),
    "cotton": dict(name="Algodón",family="Malvaceae",days=[30,50,60,55],kc=[.35,1.15,.50],
                   root=1.2,p=.65,window=[10,11,12],ph=None,ec=7.7,cover=.78),
    "cassava": dict(name="Yuca de ciclo corto",family="Euphorbiaceae",days=[20,40,90,60],kc=[.30,.80,.30],
                    root=.65,p=.35,window=[10,11,12,1],ph=None,ec=None,cover=.83),
    "potato": dict(name="Papa",family="Solanaceae",days=[25,30,45,30],kc=[.50,1.15,.75],
                   root=.5,p=.35,window=[4,5,6,9,10],ph=None,ec=1.7,cover=.78),
    "tomato": dict(name="Tomate",family="Solanaceae",days=[30,40,40,25],kc=[.60,1.15,.80],
                   root=.9,p=.40,window=[4,5,6,9,10],ph=None,ec=2.5,cover=.80),
    "sweetpotato": dict(name="Camote",family="Convolvulaceae",days=[15,30,50,30],kc=[.50,1.15,.65],
                        root=1.,p=.65,window=[10,11,12,1],ph=None,ec=1.5,cover=.87),
    "cowpea": dict(name="Caupí",family="Fabaceae",days=[20,30,30,20],kc=[.40,1.05,.35],
                   root=.8,p=.45,window=[10,11,12,1,2,4,5],ph=None,ec=4.9,cover=.84),
}
for code in ("soy", "maize", "sorghum"):
    CROPS[code]["window"] += [5,6,7] if code != "soy" else [6,7]
WEIGHTS = {"balanced":[.50,.30,.20],"water":[.78,.12,.10],"cover":[.23,.67,.10],"diversity":[.25,.15,.60]}


def planting_months(inputs):
    return inputs.get("plant_months") or [inputs["plant_month"]]*3


def planting_dates(year, inputs):
    return [date(year+i,month,1) for i,month in enumerate(planting_months(inputs))]

def et0(rows, latitude, elevation, warming=0):
    valid = np.array([all(row[c] is not None for c in COLS[:6]) for row in rows])
    t, low, high, rh, wind, solar = np.array(
        [[row[c] if row[c] is not None else np.nan for c in COLS[:6]] for row in rows],dtype=float).T
    t, low, high = t+warming, low+warming, high+warming
    j = np.array([row["date"].timetuple().tm_yday for row in rows])
    lat = np.radians(latitude)
    angle = 2*np.pi*j/365
    dr, decl = 1+.033*np.cos(angle), .409*np.sin(angle-1.39)
    omega = np.arccos(np.clip(-np.tan(lat)*np.tan(decl),-1,1))
    ra = (24*60/np.pi)*.0820*dr*(omega*np.sin(lat)*np.sin(decl)+np.cos(lat)*np.cos(decl)*np.sin(omega))
    rso = (.75+.00002*elevation)*ra

    def es(temp):
        return .6108 * np.exp(17.27*temp/(temp+237.3))

    sat = (es(low)+es(high))/2
    actual = sat * rh / 100
    relative_solar = np.divide(solar, rso, out=np.full_like(solar, .3), where=rso>.01)
    rnl = (4.903e-9 * ((high+273.16)**4+(low+273.16)**4)/2
           * (.34-.14*np.sqrt(actual)) * (1.35*np.clip(relative_solar,.3,1)-.35))
    net = .77*solar-rnl
    slope = 4098*es(t)/(t+237.3)**2
    gamma = .000665*(101.3*((293-.0065*elevation)/293)**5.26)
    calculated = (.408*slope*net+gamma*900/(t+273)*wind*(sat-actual))/(slope+gamma*(1+.34*wind))
    return np.where(valid, np.maximum(calculated,0), np.nan)

def water_day(storage, depth, fc, wp, p, rain, irrigation_limit, demand, runoff_fraction=.10):
    taw = (fc-wp)*depth*1000
    raw = p*taw
    runoff = runoff_fraction*rain
    infiltrated = rain-runoff
    irrigation = min(irrigation_limit, max(0, taw-raw-storage-infiltrated))
    available = storage+infiltrated+irrigation
    drainage = max(0, available-taw)
    usable = min(taw, available)
    stress = min(1, usable/max(taw-raw, .000001))
    actual = min(usable, demand*stress)
    return usable-actual, actual, irrigation, drainage, runoff, taw, raw

def monthly(rows):
    groups = {}
    for row in rows:
        key = (row["date"].year,row["date"].month)
        groups.setdefault(key,[]).append(row)
    table = []
    for month in range(1,13):
        rains, temps = [], []
        for (year, key), data in groups.items():
            if key != month or len(data) != calendar.monthrange(year,key)[1]:
                continue
            r = [x["precip_mm_day"] for x in data]
            t = [x["tmean_c"] for x in data]
            if None not in r:
                rains.append(sum(r))
            if None not in t:
                temps.append(float(np.mean(t)))
        table.append(dict(month=month,rain=round(float(np.mean(rains)),2) if rains else None,
                          temp=round(float(np.mean(temps)),2) if temps else None,
                          rain_years=len(rains), temp_years=len(temps)))
    return table

def sequences(inputs):
    viable = {}
    excluded = {}
    for code, crop in CROPS.items():
        if inputs.get("allowed_crops") is not None and code not in inputs["allowed_crops"]:
            continue
        reasons = []
        if not any(month in crop["window"] for month in planting_months(inputs)):
            reasons.append("Meses de siembra fuera de la ventana orientativa.")
        if inputs["soil_ph"] is not None and crop["ph"] and not crop["ph"][0] <= inputs["soil_ph"] <= crop["ph"][1]:
            reasons.append("pH declarado fuera del intervalo ilustrativo.")
        if inputs["soil_ec"] is not None and crop["ec"] is not None and inputs["soil_ec"] > crop["ec"]:
            reasons.append("La conductividad declarada supera el umbral de referencia del catálogo.")
        if reasons:
            excluded[crop["name"]] = reasons
        else:
            viable[code] = crop
    # Three distinct crops, with a demonstration restriction against consecutive
    # soybeans on the transition from the previous crop.
    months = planting_months(inputs)
    slots = [[code for code,crop in viable.items() if month in crop["window"]] for month in months]
    dates = planting_dates(2021, inputs)
    patterns = [p for p in product(*slots) if len(set(p)) == 3
                and (p[0], inputs["previous"]) != ("soy","soy")
                and all(sum(CROPS[p[i]]["days"]) <= (dates[i+1]-dates[i]).days for i in range(2))]
    base = [inputs["previous"]]*3 if inputs["previous"] in CROPS else None
    if base and any(sum(CROPS[base[i]]["days"]) > (dates[i+1]-dates[i]).days for i in range(2)):
        base = None
    return patterns, excluded, base

def growth(crop, day):
    initial, development, middle, late = crop["days"]
    lo, peak, end = crop["kc"]
    if day < initial:
        return lo, .15, .15
    if day < initial+development:
        f = (day-initial)/development
        return lo+(peak-lo)*f, .15+(crop["root"]-.15)*f, .15+(crop["cover"]-.15)*f
    if day < initial+development+middle:
        return peak, crop["root"], crop["cover"]
    f = min(1,(day-initial-development-middle)/late)
    return peak+(end-peak)*f, crop["root"], crop["cover"]*(1-.45*f)

def project(rows, planting_year, seq, inputs, profile, scenario, trace=False):
    planting = planting_dates(planting_year,inputs)
    full_depth = profile["depth_m"]
    fc, wp = profile["theta_fc"], profile["theta_wp"]
    monthly_coverage, total_deficit, stressed, irrigation_sum = [], 0., 0, 0.
    last_depth, root_water, outside_water = full_depth,.5*(fc-wp)*full_depth*1000,0.
    season = 0
    frost_days = hot_days = bare_days = 0
    warming = inputs["warming_c"] if scenario == "sensitivity" else 0
    daily = []
    for row, demand0, rain0 in rows:
        day = row["date"]
        if season < 2 and day >= planting[season+1]:
            season += 1
        crop = CROPS[seq[season]]
        age = (day-planting[season]).days
        growing = 0 <= age < sum(crop["days"])
        frost_days += growing and row["tmin_c"] + warming <= 0
        hot_days += growing and row["tmax_c"] + warming >= 35
        bare_days += not growing
        kc, root, canopy = growth(crop, age) if growing else (.20, .20, .0)
        depth = min(root,full_depth)
        if depth > last_depth and full_depth > last_depth:
            transferred = outside_water * (depth-last_depth)/(full_depth-last_depth)
            root_water += transferred
            outside_water -= transferred
        if depth < last_depth:
            transferred = root_water * (last_depth-depth)/last_depth
            root_water -= transferred
            outside_water += transferred
        top, actual, irrigation, drain, runoff, taw, raw = water_day(
            root_water,depth,fc,wp,crop["p"],rain0,
            (inputs["irrigation_mm"] or 0) if growing and inputs["irrigation"]=="confirmed" else 0, demand0*kc)
        deep_capacity = (fc-wp)*(full_depth-depth)*1000
        retained = min(max(0,deep_capacity-outside_water),drain)
        outside_water += retained
        root_water,last_depth = top,depth
        deficit = max(0,demand0*kc-actual) if growing else 0
        monthly_coverage.append(canopy)
        total_deficit += deficit
        stressed += deficit > .1
        irrigation_sum += irrigation
        if trace:
            daily.append([day.isoformat(),seq[season] if growing else "fallow",round(rain0,3),round(demand0,3),
                          round(demand0*kc,3),round(actual,3),round(deficit,3),round(taw-top,3),
                          round(irrigation,3),round(drain-retained,3),round(runoff,3),round(raw,3)])
    return dict(scenario=scenario,year=planting_year, deficit_mm=round(total_deficit,2),
                stress_days=stressed, cover_pct=round(100*float(np.mean(monthly_coverage)),2),
                frost_days=frost_days, hot_days=hot_days, fallow_days=bare_days,
                irrigation_mm=round(irrigation_sum,2)), daily

def windows(rows, inputs, elevation, latitude):
    mapping = {r["date"]: n for n,r in enumerate(rows)}
    span = range(rows[0]["date"].year, rows[-1]["date"].year-1)
    for scenario, rain_shift, warming in [
        ("historical",0,0), ("sensitivity", inputs["rainfall_shift_pct"], inputs["warming_c"])
    ]:
        demands = et0(rows, latitude, elevation, warming)
        for year in span:
            months = planting_months(inputs)
            first = date(year,months[0],1)
            end = date(year+3,months[2],1)
            selected = [mapping.get(first+timedelta(days=i)) for i in range((end-first).days)]
            if any(i is None or not np.isfinite(demands[i]) or rows[i]["precip_mm_day"] is None for i in selected):
                continue
            yield scenario, year, [(rows[i],float(demands[i]), rows[i]["precip_mm_day"]*(1+rain_shift/100))
                                   for i in selected]


def simulate_window(rows, year, choices, inputs, profile, scenario):
    """Evaluate the daily recurrence for all rotations in parallel within one window."""
    planting = planting_dates(year,inputs)
    codes = list(CROPS)
    index = {code:i for i,code in enumerate(codes)}
    paths = np.array([[index[code] for code in seq] for _,seq in choices])
    max_duration = max(sum(c["days"]) for c in CROPS.values())
    growth_table = np.array([[growth(c,d) if d < sum(c["days"]) else (.20,.20,0.)
                              for d in range(max_duration+1)] for c in CROPS.values()])
    depletion = np.array([c["p"] for c in CROPS.values()])
    duration = np.array([sum(c["days"]) for c in CROPS.values()])
    full_depth = profile["depth_m"]
    capacity = (profile["theta_fc"]-profile["theta_wp"])*1000
    root_water = np.full(len(choices), .5*capacity*full_depth)
    deep_water = np.zeros(len(choices))
    prev_depth = np.full(len(choices), full_depth)
    deficit, cover, irrigation, stress, frost, heat, fallow = np.zeros((7,len(choices)))
    max_irrigation = (inputs["irrigation_mm"] or 0) if inputs["irrigation"] == "confirmed" else 0
    warming = inputs["warming_c"] if scenario == "sensitivity" else 0
    season = 0
    for row, reference, rain in rows:
        day = row["date"]
        if season < 2 and day >= planting[season+1]:
            season += 1
        crops = paths[:,season]
        age = (day-planting[season]).days
        growing = age < duration[crops]
        kc, root, canopy = growth_table[crops,min(age,max_duration)].T
        depth = np.minimum(root,full_depth)
        delta = depth-prev_depth
        gained = np.divide(deep_water*delta,full_depth-prev_depth,out=np.zeros_like(root_water),where=delta>0)
        transfer = np.where(delta < 0, root_water*delta/prev_depth, gained)
        root_water += transfer
        deep_water -= transfer
        taw = capacity*depth
        remaining = taw - depletion[crops]*taw
        infiltrated = rain - .10*rain
        applied = np.minimum(max_irrigation*growing,np.maximum(0,remaining-root_water-infiltrated))
        available = root_water+infiltrated+applied
        drainage = np.maximum(0,available-taw)
        usable = np.minimum(taw,available)
        demand = reference*kc
        actual = np.minimum(usable,demand*np.minimum(1,usable/np.maximum(remaining,.000001)))
        deep_water += np.minimum(np.maximum(0,capacity*(full_depth-depth)-deep_water),drainage)
        root_water,prev_depth = usable-actual,depth
        gap = np.where(growing,np.maximum(0,demand-actual),0.)
        deficit += gap
        stress += gap > .1
        irrigation += applied
        cover += canopy
        frost += growing & (row["tmin_c"]+warming <= 0)
        heat += growing & (row["tmax_c"]+warming >= 35)
        fallow += ~growing
    return [dict(scenario=scenario,year=year,deficit_mm=round(float(d),2),stress_days=int(s),
                 cover_pct=round(float(c)*100/len(rows),2),irrigation_mm=round(float(i),2),
                 frost_days=int(f),hot_days=int(h),fallow_days=int(b))
            for d,s,c,i,f,h,b in zip(deficit,stress,cover,irrigation,frost,heat,fallow)]


def run_model(rows, source, site, inputs, soil_profile=None):
    patterns, excluded, baseline = sequences(inputs)
    profile = {k: inputs[k] for k in ["theta_fc","theta_wp","depth_m"]}
    from .soil import retention_at_depth
    regional = retention_at_depth(soil_profile, profile["depth_m"]) if inputs.get("use_regional_soil") else None
    soil_used = bool(regional and profile["theta_fc"] is None and profile["theta_wp"] is None)
    if soil_used:
        profile.update(regional)
    missing = [label for key,label in [("theta_fc","capacidad de campo"),("theta_wp","punto de marchitez"),
                                       ("depth_m","profundidad útil"),("soil_ph","pH"),("soil_ec","conductividad eléctrica")]
               if inputs[key] is None and not (soil_used and key in ("theta_fc", "theta_wp"))]
    if inputs["previous"] == "unknown":
        missing.append("cultivo anterior")
    if inputs["irrigation"] == "unknown":
        missing.append("disponibilidad de riego")
    assumed = []
    if inputs["trial"]:
        defaults = {"theta_fc":.29,"theta_wp":.14,"depth_m":.85}
        assumed.extend(k for k,v in profile.items() if v is None)
        profile = {k: defaults[k] if v is None else v for k,v in profile.items()}
    elevation = inputs["elevation_m"] if inputs["elevation_m"] is not None else source.get("elevation_m")
    if elevation is None:
        missing.append("elevación")
        if inputs["trial"]:
            elevation = 250.
            assumed.append("elevation_m")
    if inputs["irrigation"] == "unknown" and inputs["trial"]:
        assumed.append("irrigation")
    if elevation is None or None in profile.values() or (inputs["irrigation"] == "unknown" and not inputs["trial"]):
        candidates = []
    else:
        if profile["theta_wp"] >= profile["theta_fc"]:
            raise JobError("La retención de prueba combinada con tus valores es incompatible. Completa la capacidad y la marchitez.")
        candidates = list(windows(rows,inputs,elevation,site["lat"]))
    if not candidates:
        missing.append("ventanas aptas para balance hídrico")
    weights = WEIGHTS[inputs["priority"]]
    records = []
    choices = [(f"rotation-{'-'.join(seq)}", seq) for seq in patterns]
    if baseline:
        choices.append(("reference",baseline))
    samples = {case:[] for case in ("historical","sensitivity")}
    if choices:
        for case,year,data in candidates:
            samples[case].append(simulate_window(data,year,choices,inputs,profile,case))
    for order,(rotation_id,seq) in enumerate(choices):
        families = [CROPS[x]["family"] for x in seq]
        diversity = sum(a!=b for a,b in zip(families,families[1:]))/2
        metrics = {}
        for scenario in ("historical","sensitivity"):
            values = [window[order] for window in samples[scenario]]
            metrics[scenario] = {k:round(float(np.mean([v[k] for v in values])),2) if values else None
                                 for k in ("deficit_mm","stress_days","cover_pct","irrigation_mm","frost_days","hot_days","fallow_days")}
            metrics[scenario]["windows"] = [v["year"] for v in values]
            metrics[scenario]["window_results"] = values
            metrics[scenario]["deficit_range"] = [min(v["deficit_mm"] for v in values),
                max(v["deficit_mm"] for v in values)] if values else None
        historic = metrics["historical"]
        if historic["cover_pct"] is None:
            schematic = [growth(CROPS[c], day)[2] for c in seq for day in range(sum(CROPS[c]["days"]))]
            dates = planting_dates(2021,inputs)
            period = (date(2024,planting_months(inputs)[2],1)-dates[0]).days
            historic["cover_pct"] = round(100*sum(schematic)/period,2)
        # Fixed anchors allow preferences to change the ordering without changing
        # the score of an option when a competing option is removed.
        terms = [None if historic["deficit_mm"] is None else max(0,1-historic["deficit_mm"]/1200),
                 min(1,historic["cover_pct"]/40), diversity]
        active = sum(w for w,x in zip(weights,terms) if x is not None)
        score = round(100*sum(w*x for w,x in zip(weights,terms) if x is not None)/active,1)
        records.append(dict(id=rotation_id, crops=list(seq), names=[CROPS[c]["name"] for c in seq],
                            families=families, diversity=diversity, score=score, metrics=metrics,
                            criteria=dict(zip(["water","cover","diversity"],terms)),
                            calendar=[dict(crop=CROPS[c]["name"], month=month,
                                           duration=sum(CROPS[c]["days"])) for c,month in zip(seq,planting_months(inputs))]))
    reference = next((r for r in records if r["id"]=="reference"),None)
    ranked = sorted((r for r in records if r["id"]!="reference"),key=lambda r:(-r["score"],r["id"]))[:3]
    for case in ("historical", "sensitivity"):
        for record in ranked:
            metrics = record["metrics"][case]
            wins = 0
            for outcome in metrics["window_results"]:
                best = min(sample["deficit_mm"] for candidate in ranked
                           for sample in candidate["metrics"][case]["window_results"]
                           if sample["year"] == outcome["year"])
                wins += outcome["deficit_mm"] == best
            metrics["lowest_deficit_windows"] = wins
    from .evidence import climate_indicators, recommendation
    values = dict(version=VERSION,catalog_version=CATALOG_VERSION,catalog_source=FAO,
                  alternatives=ranked,reference=reference,excluded=excluded,monthly=monthly(rows),
                  candidate_count=len(patterns),missing=missing,source=source,weights=weights,trial=inputs["trial"],
                  status="Exploratorio",profile=profile,elevation_m=elevation,
                  regional_soil=soil_profile, regional_retention=soil_used, assumed=assumed,
                  climate_indicators=climate_indicators(rows,latitude=site["lat"],elevation=elevation),
                  catalog_parameters=CROPS,
                  limitations=["Coeficientes y raíces de referencia FAO 56. Calendario, cobertura y cultivares requieren validación local.",
                    "Tres campañas anuales en años sucesivos. Confirma aptitud térmica, altitud y manejo por zona. La simulación prioriza el agua y la cobertura.",
                    "Balance con humedad inicial al 50 %, escorrentía ilustrativa de 10 % y suelo uniforme.",
                    "La humedad relativa media aproxima la presión real de vapor. El clima es regional.",
                    "El escenario de sensibilidad aplica factores uniformes a la secuencia diaria histórica.",
                    "Los pesos sin dato hídrico se renormalizan sobre cobertura y diversidad.",
                    "La referencia, si existe, repite el cultivo anterior como supuesto explícito."],
                  actions=[{"item":"Muestreo de suelo por profundidad","reason":"Confirmar retención, pH, CE, textura y profundidad útil."},
                    {"item":"Revisar calendario y disponibilidad hídrica","reason":"Confirmar con el productor y un agrónomo las ventanas, cultivares, historial sanitario y caudal."}])
    first_windows = {}
    for case,year,data in candidates:
        first_windows.setdefault(case,(year,data))
    daily = {}
    for record in ranked + ([reference] if reference else []):
        daily[record["id"]] = {case:project(first_windows[case][1],first_windows[case][0],record["crops"],
            inputs,profile,case,trace=True)[1] if case in first_windows else [] for case in ("historical","sensitivity")}
        if record is not reference:
            record["recommendation"] = recommendation(record, reference, assumed, soil_used, inputs["priority"])
    return values, daily
