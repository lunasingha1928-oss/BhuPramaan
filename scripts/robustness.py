#!/usr/bin/env python
"""Robustness checks: multiple seeds, and an ablation that removes the owner-name features."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon.features import FEATURES  # noqa: E402
from recon.footprints import load_footprints  # noqa: E402
from recon.pipeline import load_policy, run_benchmark  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--seeds", type=int, default=5)
ap.add_argument("--save", default=None, help="write results as JSON (e.g. demo/robustness.json) for the console")
a = ap.parse_args()

NO_NAME = [f for f in FEATURES if not f.startswith("name_")]
pol = load_policy()
rows = {"all features": [], "geometry only (no owner names)": []}
for seed in range(1, a.seeds + 1):
    truth = load_footprints(a.input, seed)
    for label, cols in (("all features", None), ("geometry only (no owner names)", NO_NAME)):
        r = run_benchmark(truth, pol, seed, cols)["results"]
        ml, base = r["Calibrated XGBoost"], r["IoU baseline"]
        rows[label].append([ml["auto_precision"], ml["auto_recall"], ml["auto_f1"], ml["auto_resolved_share"],
                            ml["assisted_recall"], base["auto_f1"], base["auto_resolved_share"]])
hdr = ["auto precision", "auto recall", "auto F1", "no-review share", "recall incl. review",
       "baseline F1", "baseline no-review"]
print(f"{a.seeds} seeds (mean ± sd). Footprints fixed, errors re-injected and splits re-drawn each seed.\n")
print("| Setting | " + " | ".join(hdr) + " |")
print("|---|" + "---|" * len(hdr))
for label, v in rows.items():
    v = np.array(v)
    print(f"| {label} | " + " | ".join(f"{m:.1%} ± {s:.1%}" for m, s in zip(v.mean(0), v.std(0))) + " |")

if a.save:
    out = {"seeds": a.seeds, "headers": hdr,
           "rows": [{"setting": k, "mean": np.array(v).mean(0).tolist(), "sd": np.array(v).std(0).tolist()}
                    for k, v in rows.items()]}
    Path(a.save).write_text(json.dumps(out, indent=2))
    print(f"\nSaved {a.save}")
