#!/usr/bin/env python
"""Distribution-shift test: train+calibrate on one error profile, test on a harsher, different one.

Answers: does the matcher only memorise the errors we injected, and does the precision guarantee hold?
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon.evaluate import evaluate  # noqa: E402
from recon.features import FEATURES, candidate_pairs, pair_features  # noqa: E402
from recon.footprints import load_footprints  # noqa: E402
from recon.inject import build_benchmark  # noqa: E402
from recon.ml import assign_roles, bucket, choose_thresholds, fit_calibrator, fit_model  # noqa: E402
from recon.pipeline import load_policy  # noqa: E402
from recon.profiles import MID_MIX, MID_RANGES, SHIFT_MIX, SHIFT_RANGES  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--seeds", type=int, default=5)
ap.add_argument("--save", default=None, help="write results as JSON (e.g. demo/shift.json) for the console")
a = ap.parse_args()
pol = load_policy()
bm, mlp = pol["benchmark"], pol["ml"]
NO_NAME = [f for f in FEATURES if not f.startswith("name_")]


def prep(truth, seed, mix, ranges):
    from recon.profiles import prepare
    return prepare(truth, pol, seed, mix, ranges)


def train(f, roles_pairs, cols, seed):
    tr, ca = f[roles_pairs == "train"], f[roles_pairs == "calib"]
    m = fit_model(tr, tr.label.values, seed, cols)
    cal = fit_calibrator(m.predict_proba(ca[cols])[:, 1], ca.label.values)
    t_lo, t_hi = choose_thresholds(cal.predict(m.predict_proba(ca[cols])[:, 1]), ca.label.values,
                                   mlp["target_auto_precision"], mlp["max_missed_true_pairs"])
    return m, cal, t_lo, t_hi


def score(f, b, m, cal, t_lo, t_hi, cols, test_ids):
    p = cal.predict(m.predict_proba(f[cols])[:, 1])
    pred = f[["a_id", "b_id"]].assign(bucket=bucket(p, t_lo, t_hi))
    return evaluate(pred, b.truth, b.A, b.B, test_ids)


rows = []
for seed in range(1, a.seeds + 1):
    truth = load_footprints(a.input, seed)
    b1, f1 = prep(truth, seed, bm["error_mix"], None)
    b2, f2 = prep(truth, seed + 100, SHIFT_MIX, SHIFT_RANGES)
    cent = np.c_[b1.A.geometry.centroid.x.values, b1.A.geometry.centroid.y.values]
    role_a = assign_roles(cent, mlp["block_size_m"], mlp["block_fractions"], seed)
    r1, r2 = role_a[f1.a_idx.values], role_a[f2.a_idx.values]
    test_ids = set(b1.A.a_id[role_a == "test"])
    cols = NO_NAME
    m, cal, lo, hi = train(f1, r1, cols, seed)
    same = score(f1, b1, m, cal, lo, hi, cols, test_ids)
    shifted = score(f2, b2, m, cal, lo, hi, cols, test_ids)
    m2, cal2, lo2, hi2 = train(f2, r2, cols, seed)
    oracle = score(f2, b2, m2, cal2, lo2, hi2, cols, test_ids)
    # E. domain randomisation: train+calibrate on a MIX of default and a different, intermediate profile
    b3, f3 = prep(truth, seed + 200, MID_MIX, MID_RANGES)
    r3 = role_a[f3.a_idx.values]
    fm = pd.concat([f1, f3], ignore_index=True)
    rm = np.concatenate([r1, r3])
    m3, cal3, lo3, hi3 = train(fm, rm, cols, seed)
    robust = score(f2, b2, m3, cal3, lo3, hi3, cols, test_ids)
    base_pred = f2[["a_id", "b_id"]].assign(bucket=np.where(f2.iou >= .5, "accept", np.where(f2.iou >= .2, "review", "reject")))
    base = evaluate(base_pred, b2.truth, b2.A, b2.B, test_ids)
    for name, r in (("A. trained default, tested default", same), ("B. trained default, tested SHIFTED", shifted),
                    ("C. trained+calibrated on shifted (oracle)", oracle), ("D. IoU baseline on shifted", base),
                    ("E. trained on mixed profiles, tested SHIFTED", robust)):
        rows.append({"setting": name, "prec": r["auto_precision"], "recall": r["auto_recall"], "f1": r["auto_f1"],
                     "noreview": r["auto_resolved_share"], "assisted": r["assisted_recall"]})

df = pd.DataFrame(rows)
print(f"Geometry-only features, {a.seeds} seeds. Shifted profile: offsets 10-25 m, rotations 15-40 deg, "
      "area x0.4-0.7 / x1.4-2.0, 2x split & merge share.\n")
print("| Setting | Auto precision | Auto recall | Auto F1 | No-review share | Recall incl. review |")
print("|---|---|---|---|---|---|")
for name, g in df.groupby("setting", sort=True):
    cells = [f"{g[c].mean():.1%} ± {g[c].std(ddof=0):.1%}" for c in ("prec", "recall", "f1", "noreview", "assisted")]
    print(f"| {name} | " + " | ".join(cells) + " |")

if a.save:
    from recon.profiles import SHIFT_DESCRIPTION
    out = {"seeds": a.seeds, "description": SHIFT_DESCRIPTION, "rows": [
        {"setting": name, **{c: [float(g[c].mean()), float(g[c].std(ddof=0))]
                             for c in ("prec", "recall", "f1", "noreview", "assisted")}}
        for name, g in df.groupby("setting", sort=True)]}
    Path(a.save).write_text(json.dumps(out, indent=2))
    print(f"\nSaved {a.save}")
