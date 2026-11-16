"""NASA POWER daily weather for one point, cached on disk."""
import json
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent / "cache"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,GWETROOT"


def fetch_daily(lat, lon, start="19950101", end="20241231"):
    """Daily data as {parameter: {"YYYYMMDD": value}}. Missing days are -999.

    T2M_MAX, T2M_MIN in deg C; PRECTOTCORR in mm/day; ALLSKY_SFC_SW_DWN in
    MJ/m^2/day; GWETROOT (root-zone soil wetness) from 0 to 1.
    """
    lat, lon = round(float(lat), 2), round(float(lon), 2)
    path = CACHE_DIR / f"power5_{lat}_{lon}_{start}_{end}.json"
    if not path.exists():
        r = requests.get(URL, timeout=120, params={
            "parameters": PARAMS, "community": "AG",
            "longitude": lon, "latitude": lat,
            "start": start, "end": end, "format": "JSON",
        })
        r.raise_for_status()
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text(r.text)
    return json.loads(path.read_text())["properties"]["parameter"]
