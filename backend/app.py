"""Farmers Compass API. Run from this folder with: uvicorn app:app --reload"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import daymet
import forecast
import ndvi
import nex
import power
import rainmap
import simulator
import weather

app = FastAPI(title="Farmers Compass")
PAGE = Path(__file__).parent.parent / "frontend" / "index.html"


class SimRequest(BaseModel):
    lat: float
    lon: float
    soil: str
    current_rotation: list[str]
    priorities: dict[str, float]
    climate: str = "recent"   # or "2050"


@app.get("/")
def page():
    """The web page."""
    return FileResponse(PAGE)


@app.get("/options")
def options():
    """Crop and soil choices for the page's dropdowns."""
    return {"crops": {k: v["name"] for k, v in simulator.CROPS.items()},
            "soils": list(simulator.SOILS)}


@app.post("/simulate")
def simulate(req: SimRequest):
    """Rank crop rotations for one field over 1,000 weather futures."""
    if req.soil not in simulator.SOILS:
        raise HTTPException(400, f"unknown soil: {req.soil}")
    bad = [c for c in req.current_rotation if c not in simulator.CROPS]
    if bad or not req.current_rotation:
        raise HTTPException(400, f"unknown crops in current_rotation: {bad}")

    # POWER gives spring soil wetness. Daymet (1 km) replaces the rest where it has data.
    daily = power.fetch_daily(req.lat, req.lon)
    weather_source = "NASA POWER, about 50 km grid"
    try:
        daily.update(daymet.fetch_daily(req.lat, req.lon))
        weather_source = daymet.SOURCE + ", with spring soil wetness from NASA POWER"
    except Exception as e:
        print("Daymet unavailable, using POWER only:", e)
    years, recent = weather.yearly_features(daily)
    features, change = recent, None
    if req.climate == "2050":
        path = nex.delta_path(req.lat, req.lon)
        if not path.exists():
            raise HTTPException(400, "No NASA climate projection saved for this location yet. "
                                     f"Run: python nex.py {req.lat} {req.lon}")
        change = json.loads(path.read_text())
        years, features = weather.yearly_features(daily, change["dT"], change["rain_ratio"])

    scen_idx = weather.sample_scenarios(len(years))
    out = simulator.simulate(features, scen_idx, req.soil, req.current_rotation, req.priorities)
    out["weather_source"] = weather_source
    out["weather_history"] = {   # the real years, before any 2050 shift
        "years": years,
        "rain_mm": [round(float(v)) for v in recent[:, weather.RAIN]],
        "hot_days": [int(v) for v in recent[:, weather.HOT_DAYS]],
        "dry_spell_days": [int(v) for v in recent[:, weather.DRY_SPELL]],
        "hot_day_c": weather.HOT_DAY_C,
    }
    out["climate"] = req.climate
    out["climate_change"] = change
    return out


@app.get("/forecast")
def ten_day_forecast(lat: float, lon: float):
    """NASA GEOS 10-day forecast for the field."""
    try:
        return forecast.fetch(lat, lon)
    except Exception as e:
        raise HTTPException(502, f"NASA GEOS forecast is not available right now: {e}")


@app.get("/rain-map")
def rain_map():
    """NASA POWER average growing-season rain around Nova Scotia, for the map's heat layer."""
    try:
        return rainmap.fetch()
    except Exception as e:
        raise HTTPException(502, f"NASA POWER rain map is not available right now: {e}")


@app.get("/field-history")
def field_history(lat: float, lon: float):
    """NASA MODIS summer greenness (NDVI) of the field by year, if downloaded."""
    path = ndvi.history_path(lat, lon)
    if not path.exists():
        raise HTTPException(404, f"No greenness history saved for this point yet. Run: python ndvi.py {lat} {lon}")
    return json.loads(path.read_text())
