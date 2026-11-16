"""Monte Carlo crop rotation simulator. Runs on CuPy if a GPU works, else NumPy."""
import itertools
import json
import time
from pathlib import Path

import numpy as np

from weather import ET0, RAIN, SPRING_WET

try:
    import cupy as xp
    xp.zeros(1).sum()  # fails here if the GPU is not usable
    GPU = True
except Exception:
    import numpy as xp
    GPU = False

HERE = Path(__file__).parent
_table = json.loads((HERE / "crops.json").read_text())
CROPS = _table["crops"]
COVER = _table["cover_crop"]
SOILS = json.loads((HERE / "soils.json").read_text())["soils"]
NAMES = list(CROPS)
HORIZON = 20  # years simulated


def _passes_rules(seq):
    """Rotation rules, checked on the repeating cycle: an annual crop at most
    2 years in a row, a perennial at least 3."""
    n = len(seq)
    if len(set(seq)) == 1:
        return CROPS[seq[0]]["perennial"]
    start = next(i for i in range(n) if seq[i] != seq[i - 1])  # where a run of one crop begins
    cycle = seq[start:] + seq[:start]
    for crop, run in itertools.groupby(cycle):
        length = len(list(run))
        if CROPS[crop]["perennial"] and length < 3:
            return False
        if not CROPS[crop]["perennial"] and length > 2:
            return False
    return True


def candidate_rotations():
    """Every rotation of 4 to 6 years that passes the rules, as (sequence, cover_crop).

    The same cycle started in a different year is counted once.
    """
    seen, out = set(), []
    for n in (4, 5, 6):
        for seq in itertools.product(NAMES, repeat=n):
            key = min(seq[i:] + seq[:i] for i in range(n))
            if key in seen or not _passes_rules(seq):
                continue
            if any(seq == seq[:p] * (n // p) for p in range(1, n) if n % p == 0):
                continue  # a shorter rotation repeated
            seen.add(key)
            out.append((key, False))
            if any(not CROPS[c]["perennial"] for c in key):
                out.append((key, True))
    return out


def simulate(features, scen_idx, soil, current_rotation, priorities, top=10):
    """Run every rotation through every weather future; returns the POST /simulate response.

    features is (n_years, 6) from weather.yearly_features and scen_idx is
    (scenarios, HORIZON) from weather.sample_scenarios.
    """
    t0 = time.perf_counter()
    rotations = candidate_rotations() + [(tuple(current_rotation), False)]
    R, S = len(rotations), scen_idx.shape[0]
    f32 = xp.float32

    # Crop grown by each rotation in each year. Column 0 is the year before year 1.
    crop_idx = np.array([[NAMES.index(seq[(t - 1) % len(seq)]) for t in range(HORIZON + 1)]
                         for seq, _ in rotations])
    cover = xp.asarray([c for _, c in rotations], dtype=f32)[:, None]      # (R, 1)

    def per_year(field):
        """One crop number for every rotation and year, (R, HORIZON + 1)."""
        values = np.array([CROPS[n][field] for n in NAMES], dtype=np.float32)
        return xp.asarray(values[crop_idx])

    kc = per_year("kc")
    ky = per_year("ky")
    root_depth = per_year("root_depth_m")
    n_effect = per_year("n_effect")
    carbon_effect = per_year("carbon_effect")
    base_yield = per_year("base_yield")
    annual = 1 - per_year("perennial")
    repeat_loss = per_year("repeat_penalty")
    repeat_loss[:, 1:] *= xp.asarray(crop_idx[:, 1:] == crop_idx[:, :-1])  # only when a crop follows itself

    # Weather for each scenario and year, (S, HORIZON).
    w = xp.asarray(features[scen_idx])
    rain = w[:, :, RAIN]              # mm
    et0 = w[:, :, ET0]                # mm
    spring_wet = w[:, :, SPRING_WET]  # 0 to 1
    awc = f32(SOILS[soil]["awc_mm_per_m"])

    # Running results, (R, S).
    soil_carbon = xp.zeros((R, S), dtype=f32)   # t C/ha gained
    water_used = xp.zeros((R, S), dtype=f32)    # mm, total
    yield_sum = xp.zeros((R, S), dtype=f32)     # yield index, total
    yield_worst = xp.full((R, S), xp.inf, dtype=f32)

    # TODO(Shaurya): this loop body is the yearly update to move into cupy.RawKernel.
    for t in range(1, HORIZON + 1):
        d = kc[:, t, None] * et0[None, :, t - 1]                                # mm the crop wants
        soil_water = awc * root_depth[:, t, None] * spring_wet[None, :, t - 1]  # mm in the root zone on May 1
        supply = rain[None, :, t - 1] + soil_water                              # mm available
        use = xp.minimum(d, supply)                                             # mm the crop gets
        water_factor = xp.maximum(0, 1 - ky[:, t, None] * (1 - use / d))        # FAO-56 eq. 90
        # Boost from last year's crop (and its cover crop), for annual crops only.
        soil_n = n_effect[:, t - 1, None] + cover * annual[:, t - 1, None] * f32(COVER["n_effect"])
        soil_n = soil_n * annual[:, t, None]
        y = base_yield[:, t, None] * water_factor * (1 + soil_n) * (1 - repeat_loss[:, t, None])

        soil_carbon += carbon_effect[:, t, None] + cover * annual[:, t, None] * f32(COVER["carbon_effect"])
        water_used += use
        yield_sum += y
        yield_worst = xp.minimum(yield_worst, y)

    water_mean = water_used / HORIZON    # mm per year
    yield_mean = yield_sum / HORIZON     # yield index per year

    def scale(a):
        """Rescale to 0 to 1 across all rotations and scenarios."""
        lo, hi = a.min(), a.max()
        return (a - lo) / (hi - lo) if hi > lo else xp.zeros_like(a)

    p = {k: float(priorities.get(k, 0)) for k in ("soil", "water", "yield", "risk")}
    total = sum(p.values()) or 1.0
    score = (p["soil"] * scale(soil_carbon)
             + p["water"] * (1 - scale(water_mean))  # less water is better
             + p["yield"] * scale(yield_mean)
             + p["risk"] * scale(yield_worst)
             ) / total
    win_rate = (score > score[-1:, :]).mean(axis=1)  # last row is the current rotation

    def stats(a):
        """Mean, 10th and 90th percentile over scenarios, as numpy (R, 3)."""
        out = xp.stack([a.mean(axis=1), xp.percentile(a, 10, axis=1), xp.percentile(a, 90, axis=1)], axis=1)
        return out.get() if GPU else out

    to_np = (lambda a: a.get()) if GPU else (lambda a: a)
    carbon_s, water_s, yield_s = stats(soil_carbon), stats(water_mean), stats(yield_mean)
    score_m, win = to_np(score.mean(axis=1)), to_np(win_rate)  # .get() waits for the GPU
    runtime_ms = (time.perf_counter() - t0) * 1000

    def row(i):
        seq, cov = rotations[i]
        trio = lambda s: {"mean": round(float(s[i, 0]), 3), "p10": round(float(s[i, 1]), 3), "p90": round(float(s[i, 2]), 3)}
        return {
            "sequence": list(seq), "cover_crop": cov,
            "score": round(float(score_m[i]), 3),
            "soil_carbon_change": trio(carbon_s),
            "water_use": trio(water_s),
            "yield_index": trio(yield_s),
            "win_rate": round(float(win[i]), 3),
        }

    best = np.argsort(-score_m[:-1])[:top]
    return {
        "device": "gpu" if GPU else "cpu",
        "runtime_ms": round(runtime_ms, 1),
        "n_rotations": R - 1, "n_scenarios": S,
        "current": row(R - 1),
        "rotations": [row(int(i)) for i in best],
    }
