from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

from jupiter.climate import PILOT, PILOT_CSV, PILOT_SHA, check_power, daily_rows, inspect, sha, source_key
from jupiter.geometry import validate_geometry
from jupiter.jobs import JobError
from jupiter.model import CROPS, et0, project, sequences, simulate_window, water_day
from jupiter.report import clean
from jupiter.soil import retention_at_depth, texture
from jupiter.signals import environmental_signals, simulation_timeline, trend


def test_verified_pilot_csv_across_chunks():
    assert sha(PILOT_CSV) == PILOT_SHA
    header, _ = inspect(PILOT_CSV,"climate")
    start,end,factor,elevation = check_power(header,*PILOT)
    rows = list(daily_rows(PILOT_CSV,header,factor,size=617))
    assert (start,end,len(rows)) == (date(2015,1,1),date(2025,12,31),4018)
    assert len({r[0] for r in rows}) == 4018
    assert all(r[-1] == "ok" for r in rows)
    assert sum(r[7] for r in rows)/11 == pytest.approx(1174.83,abs=.01)
    assert sum(r[1] for r in rows)/len(rows) == pytest.approx(26.13,abs=.01)
    assert elevation == 251.15
    with pytest.raises(JobError,match="coordenadas"):
        check_power(header,-68,-16)
    assert source_key(*PILOT) != source_key(-68,-16)


def test_dates_and_missing_rain(tmp_path: Path):
    p=tmp_path/"data.csv"
    p.write_text("date,tmean_c,tmin_c,tmax_c,rh_pct,wind2m_ms,solar_mj_m2_day,precip_mm_day\n"
                 "2024-02-28,25,20,30,80,1,20,-999\n"
                 "2024-02-29,25,20,30,80,1,20,0\n",encoding="utf-8")
    rows=list(daily_rows(p,[],1,size=1))
    assert rows[0][-2:] == (None,"incomplete")
    assert rows[1][-2:] == (0,"ok")
    p.write_text(p.read_text().replace("2024-02-29","2023-02-29"))
    with pytest.raises(JobError,match="Fila 3"):
        list(daily_rows(p,[],1,size=1))


def test_water_day_manual_balance():
    # TAW 100, RAW 50, 20 mm rain loses 2 mm to runoff.
    storage,actual,irrigation,drain,runoff,taw,raw=water_day(36,1,.25,.15,.5,20,0,6)
    assert [storage,actual,irrigation,drain,runoff,taw,raw] == pytest.approx([48,6,0,0,2,100,50])
    storage,actual,*_=water_day(25,1,.25,.15,.5,0,0,6)
    assert [storage,actual] == pytest.approx([22,3])
    storage,actual,irrigation,*_=water_day(25,1,.25,.15,.5,0,20,6)
    assert [storage,actual,irrigation] == pytest.approx([39.6,5.4,20])


def test_et0_and_calendar_constraints():
    row=dict(date=date(2025,1,14),tmean_c=26,tmin_c=20,tmax_c=32,rh_pct=70,
             wind2m_ms=2,solar_mj_m2_day=20,precip_mm_day=0)
    assert et0([row],-17.18,251)[0] == pytest.approx(4.74,abs=.2)
    row["wind2m_ms"]=None
    import numpy as np
    assert np.isnan(et0([row],-17.18,251)[0])
    variants,excluded,_=sequences(dict(plant_month=3,soil_ph=None,soil_ec=None,previous="unknown"))
    assert set(excluded)=={c['name'] for c in CROPS.values()} and not variants


def test_geometry_and_safe_csv_cells():
    assert '"type": "Point"' in validate_geometry(dict(type="Point",coordinates=PILOT))
    with pytest.raises(HTTPException):
        validate_geometry(dict(type="Point",coordinates=[-17,-103]))
    with pytest.raises(HTTPException):
        validate_geometry(dict(type="Polygon",coordinates=[[[-63,-17],[-63.01,-17],[-63.01,-17.01],[-62,-18]]]))
    assert clean("  =1+1") == "'  =1+1"
    assert clean(-3.4) == -3.4


def test_soil_texture_and_depth_weighted_retention():
    assert texture(50.1,18.5,31.3) == "Franco arcillo arenosa"
    assert texture(10,10,10) is None
    profile = {"retention":[{"from_cm":0,"to_cm":5,"fc":.23,"wp":.11},
                            {"from_cm":5,"to_cm":15,"fc":.35,"wp":.17}]}
    assert retention_at_depth(profile,.10) == pytest.approx({"theta_fc":.29,"theta_wp":.14})
    assert retention_at_depth(profile,.2) is None
    profile["retention"][1]["wp"] = None
    assert retention_at_depth(profile,.10) is None


@pytest.mark.parametrize("months",[None,[11,5,11]])
def test_batched_balance_matches_individual_traces(months):
    from datetime import timedelta

    start = date(2020,11,1)
    rows = [(dict(date=start+timedelta(days=d),tmin_c=-1 if d%4 else 14,tmax_c=36),4.6,(d%9)*1.9)
            for d in range(1095)]
    choices = [("a",("bean","maize","sesame")),("b",("maize","cover","sorghum"))]
    inputs = dict(plant_month=11,plant_months=months,irrigation="confirmed",irrigation_mm=2,warming_c=1)
    profile = dict(theta_fc=.29,theta_wp=.14,depth_m=.85)
    expected = [project(rows,2020,seq,inputs,profile,"sensitivity",trace=True)[0] for _,seq in choices]
    assert simulate_window(rows,2020,choices,inputs,profile,"sensitivity") == expected


def test_campaign_calendars_filter_windows_and_overlap():
    inputs=dict(plant_month=11,plant_months=[11,5,11],soil_ph=None,soil_ec=None,previous="unknown",
                allowed_crops=["soy","wheat","sesame","sunflower"])
    choices,_,_=sequences(inputs)
    assert ("soy","wheat","sesame") in choices
    assert all(seq[1] in ("wheat","sunflower") for seq in choices)
    inputs.update(plant_months=[12,1,11],allowed_crops=["cassava","soy","sesame"])
    assert sequences(inputs)[0]==[]


def test_monthly_alignment_keeps_missing_values_and_trace_totals():
    from datetime import timedelta
    rows=[dict(date=date(2020,1,1)+timedelta(days=d),tmean_c=26,tmin_c=20,tmax_c=32,rh_pct=70,
               wind2m_ms=2,solar_mj_m2_day=20,precip_mm_day=2) for d in range(31)]
    result=environmental_signals(rows,{"support":"test"},{"lat":-17},250,None)
    assert result["monthly"][0]["rain_mm"]==62
    assert result["monthly"][0]["anomaly"] is None
    rows[2]["precip_mm_day"]=None
    assert environmental_signals(rows,{"support":"test"},{"lat":-17},None,None)["monthly"][0]["rain_mm"] is None
    daily={"historical":[["2020-01-01","soy",2,3,4,2,2,0,1],
                          ["2020-01-02","fallow",0,3,1,1,0,0,0]]}
    timeline=simulation_timeline(daily)["historical"][0]
    assert timeline["deficit_mm"]==2 and timeline["fallow_days"]==1 and timeline["stress_days"]==1
    slopes=trend([(year,2*(year-2010)) for year in range(2010,2020)],"test","unit")
    assert slopes["ols_decade"]==slopes["sen_decade"]==20 and slopes["r2"]==1
