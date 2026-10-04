#!/usr/bin/env python
"""Run the benchmark on real footprints (--input) or synthetic ones (--synthetic N, dev only)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon.footprints import load_footprints, synthetic_footprints  # noqa: E402
from recon.pipeline import load_policy, run_benchmark, save  # noqa: E402

ap = argparse.ArgumentParser()
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--input", help="GeoJSON/Shapefile of building footprints (e.g. from fetch_osm.py)")
g.add_argument("--synthetic", type=int, help="generate N synthetic footprints (development only)")
ap.add_argument("--max-parcels", type=int, default=None)
ap.add_argument("--seed", type=int, default=None)
ap.add_argument("--policy", default=None)
ap.add_argument("--out", default="results")
a = ap.parse_args()

pol = load_policy(a.policy)
seed = pol["seed"] if a.seed is None else a.seed
truth = (load_footprints(a.input, seed, a.max_parcels) if a.input else synthetic_footprints(a.synthetic, seed))
res = run_benchmark(truth, pol, seed)
save(res, a.out)
print(f"Source: {res['source']}  |  {res['n_parcels']} parcels, {res['n_candidate_pairs']} candidate pairs")
print(f"Thresholds: {res['thresholds']}\n")
print(res["markdown"])
