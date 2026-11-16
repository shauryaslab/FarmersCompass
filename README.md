# Farmers Compass

Pick a field in Nova Scotia and see which crop rotations hold up best over 20 years of
likely weather, before committing a season to one. Built for the NASA Space Apps
Challenge 2026, "Field Shift: Adapting Farms with NASA Data".

## Run it

| Step | Command |
|---|---|
| Get the code | `git clone https://github.com/shauryaslab/FarmersCompass` |
| Install | `pip install "cupy-cuda12x[ctk]" numpy fastapi uvicorn requests` |
| Start (from `backend/`) | `python -m uvicorn app:app --reload` |
| Open | http://127.0.0.1:8000 |

No GPU is needed. Without CuPy the simulator runs on NumPy. The first run for a new
location needs internet, to download its weather from NASA.

## Use it

| Step | What to do |
|---|---|
| 1 | Click your field on the map and pick its soil |
| 2 | Type your current rotation, for example `corn, corn, barley` |
| 3 | Choose recent weather or a 2050 climate |
| 4 | Set the four sliders (soil health, water use, yield, risk) and press Simulate |

Crop names to use: `corn`, `alfalfa`, `grass`, `barley`, `soybean`.

## What it does

| Feature | What the farmer gets |
|---|---|
| Field picker | Click a map or type the coordinates |
| Rain heat map | Average May to September rain across the province, with a legend, for context only |
| Rotation ranking | Top 10 of 419 rotations, scored by the farmer's priorities |
| Change against yours | For each rotation: soil carbon, water use and yield compared with the current rotation |
| Win rate | How often each rotation beats the current one across 1,000 weather futures |
| Climate option | Test against recent weather or a 2050 climate |
| Weather history | Rain, hot days and dry spells for each of the last 30 seasons |
| 10-day forecast | For context only |
| Greenness history | Satellite view of the field each summer, for context only |
| Help guide | How to use the page and read the results |

## Data

| Source | Gives | Used in ranking |
|---|---|---|
| NASA Daymet (1 km) | Daily temperature, rain, sunlight, 1995 to 2024 | Yes |
| NASA POWER (about 50 km) | Spring soil wetness; weather fallback | Yes |
| NASA POWER climatology | Average rain per grid square, 2001 to 2025, for the heat map | No |
| NASA NEX-GDDP-CMIP6 | Climate change by 2041 to 2060 | Yes, in 2050 mode |
| NASA MODIS | Summer greenness (NDVI), 2000 to 2024 | No |
| NASA GEOS | 10-day forecast | No |
| `crops.json`, `soils.json` | Crop and soil numbers, each with a source | Yes |

Full dataset names: Daymet V4 R1 (doi:10.3334/ORNLDAAC/2129), POWER daily and climatology
(MERRA-2), NEX-GDDP-CMIP6 (SSP2-4.5, three models), MODIS Terra MOD13Q1 (250 m, 16-day NDVI,
via ORNL DAAC) and GEOS forward processing forecast (GMAO). The page shows short names only.

## How it works

| Step | File | What happens |
|---|---|---|
| 1 | `daymet.py`, `power.py` | Fetch and cache daily weather for the field |
| 2 | `weather.py` | Reduce each year to rain, ET0 and spring wetness |
| 3 | `weather.py` | Shuffle the 30 years into 1,000 twenty-year futures |
| 4 | `simulator.py` | Build every rotation of 4 to 6 years that passes the rules |
| 5 | `simulator.py` | Grow every rotation through every future, year by year |
| 6 | `simulator.py` | Score, rank and return the top 10 |

Rotation rules: an annual crop at most 2 years in a row; alfalfa or grass at least 3 years.

## The math

Symbols:

| Symbol | Meaning | Unit | From |
|---|---|---|---|
| $P$ | Rain, May to September | mm | NASA Daymet |
| $T$ | Daily mean temperature | °C | NASA Daymet |
| $R_s$ | Daily sunlight | MJ/m²/day | NASA Daymet |
| $\theta$ | Spring soil wetness | 0 to 1 | NASA POWER |
| $k_c$ | Crop water coefficient | none | `crops.json` |
| $k_y$ | Yield response to water | none | `crops.json` |
| $z$ | Root depth | m | `crops.json` |
| $Y_b$ | Base yield | index | `crops.json` |
| $n$ | Boost from last year's crop | fraction | `crops.json` |
| $r$ | Loss when a crop follows itself | fraction | `crops.json` |
| $c$ | Soil carbon effect | t C/ha/yr | `crops.json` |
| $A$ | Soil water held per metre | mm/m | `soils.json` |
| $w$ | Slider weights | none | farmer |

The steps below run once per year, for each rotation in each weather future.

Reference evapotranspiration (how much water the weather pulls from a well-watered
field), summed over the growing season (Hargreaves):

```math
ET_0 = \sum_{\text{May 1}}^{\text{Sep 30}} 0.0135 \, (T + 17.8) \, \frac{R_s}{2.45}
```

Water the crop wants, and water it can get:

```math
D = k_c \, ET_0 \qquad S = P + A \, z \, \theta \qquad U = \min(D, \, S)
```

Yield response to water shortage (FAO-56):

```math
f_w = \max\left(0, \; 1 - k_y \left(1 - \frac{U}{D}\right)\right)
```

Yield and soil carbon for the year:

```math
Y = Y_b \, f_w \, (1 + n) \, (1 - r) \qquad C_t = C_{t-1} + c
```

After 20 years, each rotation in each future has four goals: soil carbon gained $C$,
mean water used $\bar{U}$, mean yield $\bar{Y}$ and worst-year yield $Y_{\min}$.
Each goal $g$ is rescaled to 0 to 1 across all rotations and futures:

```math
\tilde{g} = \frac{g - g_{\min}}{g_{\max} - g_{\min}}
```

The score weights the four goals by the sliders (less water is better, so it is flipped):

```math
\text{score} = \frac{w_s \, \tilde{C} + w_w \, (1 - \tilde{U}) + w_y \, \tilde{Y} + w_r \, \tilde{Y}_{\min}}{w_s + w_w + w_y + w_r}
```

The win rate is the share of the $N = 1000$ futures in which a rotation outscores the current one:

```math
\text{win rate} = \frac{1}{N} \sum_{i=1}^{N} \left[ \text{score}_i > \text{score}_i^{\text{current}} \right]
```

Crop numbers:

| Crop | $k_c$ | $k_y$ | $z$, m | $n$ | $r$ | $c$, t C/ha/yr | $Y_b$ |
|---|---|---|---|---|---|---|---|
| Corn silage | 1.20 | 1.25 | 1.0 | 0 | 0.075 | 0 | 1.00 |
| Alfalfa | 0.95 | 1.10 | 1.0 | 0.125 | 0 | 0.6 | 0.42 |
| Grass forage | 1.05 | 1.10 | 0.5 | 0 | 0 | 0.6 | 0.42 |
| Barley | 1.15 | 1.15 | 1.0 | 0 | 0 | 0 | 0.28 |
| Soybean | 1.15 | 0.85 | 0.6 | 0 | 0 | 0 | 0.28 |
| Winter cover crop | | | | 0 | | 0.32 | |

$n$ applies to the annual crop grown the year after. $r$ applies in a year when the crop follows itself.

Soil water held $A$, mm per metre: sand 83, sandy loam 125, loam 175, clay loam 200, clay 200.

## Limits

| Limit | Effect |
|---|---|
| Water shortage is the only weather effect on yield | Heat and frost are ignored |
| Pests and disease are one average penalty, for corn after corn only | No outbreaks, no other crops |
| Yield counts tonnes, not quality or money | Soybean and barley are undersold |
| Soil carbon ignores the weather | No spread in the carbon result |
| Each future is a 20-year average, and all rotations get the same weather | The win rate is usually 100% or 0%; the size of the gain is the useful number |
| The rain heat map uses squares of about 50 km | It shows the region's pattern, not one field, and colours the sea too |
| Soil is one number from a dropdown | Not the field's real soil |
| Projections and greenness are saved for the demo field only | Other fields need `python nex.py LAT LON` and `python ndvi.py LAT LON` |
| Any point can be picked | Cities and water are not rejected |

Sources for every number are in `backend/crops.json`, `backend/soils.json` and `TODO_SOURCES.md`.
AI assistance was used in building this project.
