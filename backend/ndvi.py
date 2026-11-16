"""NASA MODIS greenness (NDVI) history for one field.

Slow (15 to 20 minutes), so run once per field:  python ndvi.py 45.08 -64.5
The result is saved in field_history/ and the API only reads that file.
"""
import json
import sys
from pathlib import Path

import requests

URL = "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset"
BAND = "250m_16_days_NDVI"
YEARS = range(2000, 2025)
OUT_DIR = Path(__file__).parent / "field_history"


def history_path(lat, lon):
    """Saved NDVI file for a point (rounded to about 100 m)."""
    return OUT_DIR / f"ndvi_{round(lat, 3)}_{round(lon, 3)}.json"


def _summer_ndvi(year, lat, lon):
    """Mean NDVI of the 250 m pixel, June 10 to Aug 29: about 0 (bare soil) to 0.9 (dense crop).

    None if there were no valid readings.
    """
    r = requests.get(URL, timeout=300, headers={"Accept": "application/json"}, params={
        "latitude": lat, "longitude": lon, "band": BAND,
        "startDate": f"A{year}161", "endDate": f"A{year}241",
        "kmAboveBelow": 0, "kmLeftRight": 0})
    r.raise_for_status()
    body = r.json()
    values = [v * float(body["scale"]) for s in body["subset"] for v in s["data"] if v > -3000]
    return round(sum(values) / len(values), 3) if values else None


def build(lat, lon):
    """Save summer NDVI for 2000 to 2024. The service often fails, so each year
    gets 3 tries, and running it again only fetches the missing years."""
    path = history_path(lat, lon)
    done = {}
    if path.exists():
        old = json.loads(path.read_text())
        done = {y: v for y, v in zip(old["years"], old["ndvi"]) if v is not None}
    OUT_DIR.mkdir(exist_ok=True)
    for year in YEARS:
        for attempt in range(3):
            if year in done:
                break
            try:
                done[year] = _summer_ndvi(year, lat, lon)
            except requests.RequestException as e:
                print(year, "attempt", attempt + 1, "failed:", e, flush=True)
        print(year, done.get(year), flush=True)
        out = {
            "source": "NASA MODIS Terra MOD13Q1 (250 m, 16-day NDVI) via ORNL DAAC, mean of June 10 - Aug 29",
            "lat": lat, "lon": lon,
            "years": list(YEARS), "ndvi": [done.get(y) for y in YEARS],
        }
        path.write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(build(float(sys.argv[1]), float(sys.argv[2])))
