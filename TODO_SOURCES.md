# What is sourced and what still is not

Every number in `backend/crops.json` and `backend/soils.json` carries a `source` note.
Full references are at the top of each file.

## Sourced

| Number | Source | Checked how |
|---|---|---|
| `kc` (crop water demand), all crops | FAO-56 Table 12, Kc mid | Read from the FAO page |
| `ky` (yield loss from water shortage): corn, alfalfa, soybean | FAO-56 Table 24 | Read from the FAO page |
| `root_depth_m`, all crops | FAO-56 Table 22, lower bound of each range | Read from the FAO page |
| `awc_mm_per_m`, all soils | BC Ministry of Agriculture Factsheet 619.000-1, Table 2 | Read from the PDF |
| `n_effect` for alfalfa (0.125) | OMAFRA Publication 811, Chapter 3: 10%-15% benefit to corn after alfalfa | Read from the PDF |
| `base_yield`, all crops | Statistics Canada Table 32-10-0359-01, Nova Scotia, mean of 2015-2024; corn silage dry matter from Perennia Corn Production Guide | Pulled from the StatCan API; Perennia PDF read |
| `repeat_penalty` for corn (0.075) | OMAFRA Publication 811, Chapter 8, Table 8-2: continuous corn 8.91 t/ha against 9.63 after soybean (Ridgetown, 2010-2014) | Read from the PDF |
| `carbon_effect` for alfalfa and grass (0.6) | VandenBygaart et al. 2010 | Abstract only, full paper not read |
| `carbon_effect` for cover crop (0.32) | Poeplau and Don 2015 | Co-author's summary only, paper not read |

## Stand-ins (sourced number, but for a different crop)

- Corn silage uses the FAO values for grain maize. FAO-56 has no silage entry.
- Barley `ky` uses spring wheat. FAO-56 Table 24 has no barley entry.
- Grass forage `kc` uses rye grass hay.

## Still UNVERIFIED or assumed

- `ky` for grass forage: borrowed from alfalfa.
- `repeat_penalty` for barley: set to 0, no source found. For soybean it is 0 because
  the Ontario table's difference was not statistically significant. The corn value was
  measured for grain corn in Ontario and is applied to silage corn in Nova Scotia.
- `n_effect` for corn, grass, barley, soybean and the cover crop: set to 0 because no
  source was found. Real rotations do have effects here (for example soybean before corn).

## Choices that need a justification

- `base_yield` counts tonnes of feed only. It ignores feed quality, so soybean (high
  protein) and barley (grain only, straw not counted) look weaker than they are.
- Alfalfa and grass share one `base_yield`, because Statistics Canada reports them
  together as tame hay. Perennia's Maritime cultivar trials put both near 8.5 t/ha
  (alfalfa AC Caribou 8.51, timothy Climax 8.50), against 17.6 t/ha dry matter for
  corn silage in Perennia's 2018 trial, a ratio of 0.48. Trial plots yield more than
  farm averages, so the farm figures are used.
- Hay and grain yields are used as reported, not converted to dry matter.

- `kc` is the mid-season value applied to the whole May-September season, so water
  demand is overstated for annual crops early and late in the season.
- Root depth uses the lower bound of each FAO range.
- The alfalfa benefit was measured for corn in Ontario. It is applied to any annual crop
  that follows alfalfa, in Nova Scotia.
- Soil carbon values are national (Canada) and global averages, not Nova Scotia values.
  Annual crops are the baseline (0), so the result means "relative to annual cropping".
- Soil carbon change depends only on the crop, not on the weather.
- Heat stress and dry-spell timing do not affect yield. No sourced sensitivity was found,
  so only total water shortage reduces yield. Hot days and dry spells are still shown.

## backend/weather.py

- `HOT_DAY_C = 27.0` and `DRY_DAY_MM = 1.0` are display thresholds only.
- `GDD_BASE_C = 10.0`: growing degree days are computed but not used.
- Reference evapotranspiration uses the Hargreaves radiation formula,
  `ET0 = 0.0135 * (Tmean + 17.8) * Rs / 2.45`. Written from memory: check the
  coefficients against the original paper (Hargreaves and Samani) and cite it.

## backend/daymet.py and app.py: mixing two weather sources

- Temperature, rain and sunlight come from Daymet (1 km). Spring soil wetness comes
  from POWER (about 50 km), because Daymet has no soil moisture.
- GWETROOT is a fraction of saturation, not of plant-available water, so using it to
  scale the soil's available water is approximate.
- Outside North America, or if Daymet is down, the code falls back to POWER only.

## backend/rainmap.py: rain heat map

- Average May to September rain per grid square, from the NASA POWER climatology
  (2001 to 2025). Monthly mean rain in mm/day is multiplied by the days in the month.
- The squares are 0.5 by 0.625 degrees (about 50 km), so the map shows the regional
  pattern, not field detail. It is not used in the ranking.

## Win rate: why it is usually 100% or 0%

- Every rotation is tested in the same 1,000 futures, and each future is 20 years long,
  so wet and dry years average out. At the demo field the yield index of one rotation
  moves by about 0.04 between futures (10th to 90th percentile), while rotations differ
  from each other by up to 0.39. A rotation that is ahead on average is ahead in almost
  every future.
- This is what the model gives, not an error. The page also shows how much each result
  changes against the current rotation, which is the more useful number.

## backend/nex.py: climate projection choices

- Three climate models (ACCESS-CM2, CanESM5, MPI-ESM1-2-HR), one scenario (SSP2-4.5).
- Change = 2041-2060 minus 1995-2014, growing season only, applied as one flat
  shift to every day of the weather record. Sunlight and spring soil wetness
  are left unchanged in the "2050" run.
