"""NASA POWER average growing-season rain on a grid around Nova Scotia, cached on disk.

Drawn as a heat map on the page. Shown for context, not used in the ranking.
"""
import json
from pathlib import Path

import requests

CACHE = Path(__file__).parent / "cache" / "rainmap.json"
URL = "https://power.larc.nasa.gov/api/temporal/climatology/regional"
BOX = {"latitude-min": 43, "latitude-max": 47.5, "longitude-min": -66.5, "longitude-max": -59.5}
DAYS = {"MAY": 31, "JUN": 30, "JUL": 31, "AUG": 31, "SEP": 30}   # days in each growing-season month
CELL_LAT, CELL_LON = 0.5, 0.625   # size of one grid cell, degrees


def fetch():
    """Average May to September rain (mm) for each grid cell, as GeoJSON squares."""
    if not CACHE.exists():
        r = requests.get(URL, timeout=120, params={
            "parameters": "PRECTOTCORR", "community": "AG", "format": "JSON", **BOX})
        r.raise_for_status()
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(r.text)
    data = json.loads(CACHE.read_text())

    cells = []
    for f in data["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        monthly = f["properties"]["parameter"]["PRECTOTCORR"]   # mm/day, average for each month
        if min(monthly[m] for m in DAYS) < 0:
            continue   # missing
        rain = round(sum(monthly[m] * days for m, days in DAYS.items()))
        w, h = CELL_LON / 2, CELL_LAT / 2
        square = [[lon - w, lat - h], [lon + w, lat - h], [lon + w, lat + h], [lon - w, lat + h], [lon - w, lat - h]]
        cells.append({"type": "Feature", "properties": {"rain_mm": rain},
                      "geometry": {"type": "Polygon", "coordinates": [square]}})
    values = [c["properties"]["rain_mm"] for c in cells]
    period = data["header"]["start"][:4] + " to " + data["header"]["end"][:4]
    return {"type": "FeatureCollection", "features": cells,
            "min": min(values), "max": max(values),
            "source": f"NASA POWER, {period} average, about 50 km grid"}
