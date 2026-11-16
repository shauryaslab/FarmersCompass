"""Daily NASA weather -> yearly growing-season features -> sampled scenarios."""
import numpy as np

FILL = -900.0        # NASA marks missing days as -999
HOT_DAY_C = 27.0     # deg C, a daily max above this is a hot day
DRY_DAY_MM = 1.0     # mm, less rain than this is a dry day
GDD_BASE_C = 10.0    # deg C, growing degree day base
SEASON = ("0501", "0930")  # May 1 to Sep 30
SPRING = ("0401", "0430")  # April

# Columns of the features table.
RAIN, GDD, HOT_DAYS, DRY_SPELL, ET0, SPRING_WET = range(6)


def yearly_features(daily, dT=0.0, rain_ratio=1.0):
    """One row per year: rain (mm), growing degree days, hot days, longest dry
    spell (days), ET0 (mm) and April soil wetness (0 to 1).

    dT (deg C) and rain_ratio shift the weather for the 2050 option.
    """
    season, spring = {}, {}
    for day, tmax in daily["T2M_MAX"].items():
        if SEASON[0] <= day[4:] <= SEASON[1]:
            season.setdefault(day[:4], []).append((
                tmax, daily["T2M_MIN"][day], daily["PRECTOTCORR"][day], daily["ALLSKY_SFC_SW_DWN"][day]))
        elif SPRING[0] <= day[4:] <= SPRING[1] and daily["GWETROOT"][day] > FILL:
            spring.setdefault(day[:4], []).append(daily["GWETROOT"][day])

    years, rows = [], []
    for year in sorted(season):
        rain = gdd = hot = spell = longest = et0 = 0.0
        for tmax, tmin, pr, sun in season[year]:
            if tmax > FILL and tmin > FILL:
                tmax, tmin = tmax + dT, tmin + dT
                tmean = (tmax + tmin) / 2
                gdd += max(0.0, tmean - GDD_BASE_C)
                hot += tmax > HOT_DAY_C
                if sun > FILL:
                    # Hargreaves formula; 2.45 MJ evaporates 1 mm of water.
                    et0 += max(0.0, 0.0135 * (tmean + 17.8) * sun / 2.45)
            if pr > FILL:
                pr = pr * rain_ratio
                rain += pr
                spell = spell + 1 if pr < DRY_DAY_MM else 0
                longest = max(longest, spell)
        wet = spring.get(year, [1.0])
        years.append(int(year))
        rows.append((rain, gdd, hot, longest, et0, sum(wet) / len(wet)))
    return years, np.array(rows, dtype=np.float32)


def sample_scenarios(n_years, n_scenarios=1000, horizon=20, seed=0):
    """Weather futures: (n_scenarios, horizon) row numbers of the features table, picked at random."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_years, size=(n_scenarios, horizon))
