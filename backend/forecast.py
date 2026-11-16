"""NASA GEOS 10-day forecast for one point, cached on disk. Shown for context, not used in the ranking."""
import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SERVER = "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/fcast"
TEMP = ("tavg1_2d_slv_Nx", "t2m")        # air temperature at 2 m, K, hourly
RAIN = ("tavg1_2d_flx_Nx", "prectot")    # precipitation rate, mm/s, hourly
SOURCE = "NASA GEOS forecast, about 25 km grid"   # the name shown on the page
CACHE_DIR = Path(__file__).parent / "cache"
DAYS = 10
CHUNK = 12   # hours per request


def _latest_run():
    """Newest 00 UTC forecast run, e.g. '20261114_00'. Only these runs reach 10 days."""
    text = requests.get(f"{SERVER}/{TEMP[0]}", timeout=60).text
    return max(re.findall(rf"{TEMP[0]}\.(\d{{8}}_00)", text))


def _hourly(collection, var, run, lat, lon):
    """Hourly values of one variable at one grid cell, fetched in small chunks
    because the server times out on big requests."""
    j = round((lat + 90) / 0.25)        # grid row, counted from the south pole
    i = round((lon + 180) / 0.3125)     # grid column, counted from 180 W

    def chunk(first):
        url = f"{SERVER}/{collection}/{collection}.{run}.ascii?{var}[{first}:{first + CHUNK - 1}][{j}][{i}]"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        values = [float(v) for v in re.findall(r"^\[\d+\]\[0\], (\S+)", r.text, flags=re.M)]
        if len(values) != CHUNK:
            raise ValueError(f"expected {CHUNK} hourly values, got {len(values)}")
        return values

    with ThreadPoolExecutor(6) as pool:
        parts = pool.map(chunk, range(0, DAYS * 24, CHUNK))
        return [v for part in parts for v in part]


def fetch(lat, lon):
    """Next 10 days (UTC): days, tmax_c and tmin_c (deg C), rain_mm."""
    run = _latest_run()
    lat, lon = round(float(lat), 2), round(float(lon), 2)
    path = CACHE_DIR / f"forecast_{run}_{lat}_{lon}.json"
    if path.exists():
        return json.loads(path.read_text())

    temp = _hourly(*TEMP, run, lat, lon)
    rain = _hourly(*RAIN, run, lat, lon)
    start = datetime.datetime.strptime(run[:8], "%Y%m%d").date()
    out = {"source": SOURCE, "run": run, "days": [], "tmax_c": [], "tmin_c": [], "rain_mm": []}
    for d in range(min(len(temp), len(rain)) // 24):
        t, r = temp[d * 24:(d + 1) * 24], rain[d * 24:(d + 1) * 24]
        out["days"].append(str(start + datetime.timedelta(d)))
        out["tmax_c"].append(round(max(t) - 273.15, 1))
        out["tmin_c"].append(round(min(t) - 273.15, 1))
        out["rain_mm"].append(round(sum(r) * 3600, 1))   # mm/s x 3600 s in an hour
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(out))
    return out
