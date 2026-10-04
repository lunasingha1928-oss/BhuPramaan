"""Error profiles used to train (randomised) and to stress-test (harsh, unseen) the matcher."""
from __future__ import annotations

from .features import candidate_pairs, pair_features
from .inject import build_benchmark

# Intermediate profile mixed into training so the model sees a wider range of error magnitudes.
MID_MIX = {"clean": .30, "offset": .20, "scale": .10, "rotate": .07, "split": .10, "merge": .08, "missing": .08}
MID_RANGES = {"offset": (3.0, 18.0), "rotate": (5.0, 30.0), "scale_low": (0.50, 0.85), "scale_high": (1.15, 1.70)}

# Harsh profile used as the unseen test case.
SHIFT_MIX = {"clean": .25, "offset": .25, "scale": .12, "rotate": .08, "split": .12, "merge": .10, "missing": .08}
SHIFT_RANGES = {"offset": (10.0, 25.0), "rotate": (15.0, 40.0), "scale_low": (0.40, 0.70), "scale_high": (1.40, 2.00)}

SHIFT_DESCRIPTION = ("offsets 10-25 m, rotations 15-40 deg, area x0.4-0.7 or x1.4-2.0, "
                     "about twice the split and merge share of the training profile")


def prepare(truth_gdf, pol: dict, seed: int, mix: dict | None, ranges: dict | None):
    """Inject errors, generate candidates, compute features and ground-truth labels."""
    bm = pol["benchmark"]
    bench = build_benchmark(truth_gdf, seed=seed, error_mix=mix or bm["error_mix"],
                            spurious_fraction=bm["spurious_fraction"],
                            name_variant_rate=bm["name_variant_rate"], ranges=ranges)
    feats = pair_features(bench.A, bench.B,
                          candidate_pairs(bench.A, bench.B, pol["candidates"]["search_radius_m"]))
    true_set = set(zip(bench.truth.a_id, bench.truth.b_id))
    feats["label"] = [int((a, b) in true_set) for a, b in zip(feats.a_id, feats.b_id)]
    return bench, feats
