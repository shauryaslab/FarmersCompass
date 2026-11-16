"""NASA Daymet daily weather for one point (1 km grid, North America), cached on disk.

Dataset: Daymet V4 R1, doi:10.3334/ORNLDAAC/2129
"""
import datetime
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent / "cache"
URL = "https://daymet.ornl.gov/single-pixel/api/data"
SOURCE = "NASA Daymet, 1 km grid"   # the name shown on the page


def fetch_daily(lat, lon, start="1995-01-01", end="2024-12-31"):
    """Daily data with the same keys and units as power.fetch_daily (no GWETROOT).

    Raises an error outside North America.
    """
    lat, lon = round(float(lat), 2), round(float(lon), 2)
    path = CACHE_DIR / f"daymet_{lat}_{lon}_{start}_{end}.csv"
    if not path.exists():
        r = requests.get(URL, timeout=120, params={
            "lat": lat, "lon": lon, "vars": "tmax,tmin,prcp,srad,dayl", "start": start, "end": end})
        r.raise_for_status()
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text(r.text)

    lines = path.read_text().splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("year,yday"))
    col = {name.split(" ")[0]: i for i, name in enumerate(lines[head].split(","))}
    out = {"T2M_MAX": {}, "T2M_MIN": {}, "PRECTOTCORR": {}, "ALLSKY_SFC_SW_DWN": {}}
    for line in lines[head + 1:]:
        v = line.split(",")
        if len(v) < len(col):
            continue
        date = datetime.date(int(v[col["year"]]), 1, 1) + datetime.timedelta(int(v[col["yday"]]) - 1)
        day = date.strftime("%Y%m%d")
        out["T2M_MAX"][day] = float(v[col["tmax"]])
        out["T2M_MIN"][day] = float(v[col["tmin"]])
        out["PRECTOTCORR"][day] = float(v[col["prcp"]])
        # srad (W/m^2 over daylight) x dayl (daylight seconds) = J/m^2; /1e6 = MJ/m^2.
        out["ALLSKY_SFC_SW_DWN"][day] = float(v[col["srad"]]) * float(v[col["dayl"]]) / 1e6
    return out
