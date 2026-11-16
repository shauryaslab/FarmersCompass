"""NASA NEX-GDDP-CMIP6 projections -> change in growing-season climate.

Slow, so run once per location:  python nex.py 45.08 -64.5
The result is saved in climate/ and the API only reads that file.
"""
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SERVER = "https://ds.nccs.nasa.gov/thredds"
DATASET = "AMES/NEX/GDDP-CMIP6"
MODELS = ["ACCESS-CM2", "CanESM5", "MPI-ESM1-2-HR"]
BASELINE = ("historical", range(1995, 2015))   # 1995-2014
FUTURE = ("ssp245", range(2041, 2061))         # 2041-2060, middle-of-the-road emissions
OUT_DIR = Path(__file__).parent / "climate"


def cell(lat, lon):
    """The 0.25 degree grid cell that contains a point."""
    return math.floor(lat * 4) / 4, math.floor(lon * 4) / 4


def delta_path(lat, lon):
    """Saved climate change file for a point's grid cell."""
    c = cell(lat, lon)
    return OUT_DIR / f"nex_{c[0]}_{c[1]}.json"


def _files(model, scenario, var):
    """{year: file name} for one model, scenario and variable."""
    url = f"{SERVER}/catalog/{DATASET}/{model}/{scenario}/r1i1p1f1/{var}/catalog.xml"
    names = re.findall(rf'name="({var}_day_[^"]+\.nc)"', requests.get(url, timeout=120).text)
    return {int(re.search(r"_(\d{4})(_v[\d.]+)?\.nc$", n).group(1)): n for n in names}


def _season_mean(model, scenario, var, name, year, lat, lon):
    """Mean of one variable over May to September of one year at one point."""
    url = f"{SERVER}/ncss/grid/{DATASET}/{model}/{scenario}/r1i1p1f1/{var}/{name}"
    r = requests.get(url, timeout=180, params={
        "var": var, "latitude": lat, "longitude": lon % 360, "accept": "csv",
        "time_start": f"{year}-05-01T00:00:00Z", "time_end": f"{year}-09-30T23:59:59Z"})
    r.raise_for_status()
    values = [float(line.rsplit(",", 1)[1]) for line in r.text.strip().splitlines()[1:]]
    return sum(values) / len(values)


def _period_mean(model, period, var, lat, lon):
    """Mean of the season means over all years of a period."""
    scenario, years = period
    files = _files(model, scenario, var)
    with ThreadPoolExecutor(4) as pool:
        means = list(pool.map(lambda y: _season_mean(model, scenario, var, files[y], y, lat, lon), years))
    return sum(means) / len(means)


def build(lat, lon):
    """Save dT (deg C, future minus baseline) and rain_ratio (future / baseline),
    averaged over the climate models that answered."""
    models = {}
    for m in MODELS:
        try:
            t0, t1 = (_period_mean(m, p, "tas", lat, lon) for p in (BASELINE, FUTURE))
            p0, p1 = (_period_mean(m, p, "pr", lat, lon) for p in (BASELINE, FUTURE))
            models[m] = {"dT": round(t1 - t0, 2), "rain_ratio": round(p1 / p0, 3)}
            print(m, models[m], flush=True)
        except Exception as e:
            print(m, "skipped:", e, flush=True)
    if not models:
        raise SystemExit("no climate model answered")
    out = {
        "source": "NASA NEX-GDDP-CMIP6, growing season (May-Sep), 0.25 degree grid cell",
        "cell": cell(lat, lon),
        "baseline": "1995-2014 (historical)", "future": "2041-2060 (SSP2-4.5)",
        "models": models,
        "dT": round(sum(v["dT"] for v in models.values()) / len(models), 2),
        "rain_ratio": round(sum(v["rain_ratio"] for v in models.values()) / len(models), 3),
    }
    OUT_DIR.mkdir(exist_ok=True)
    delta_path(lat, lon).write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(build(float(sys.argv[1]), float(sys.argv[2])))
