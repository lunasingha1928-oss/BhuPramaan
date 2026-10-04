"""End-to-end benchmark: inject errors -> candidates -> features -> baseline vs calibrated ML -> metrics."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .evaluate import evaluate, to_markdown
from .features import FEATURES, candidate_pairs, pair_features
from .inject import build_benchmark
from .ml import assign_roles, bucket, choose_thresholds, fit_calibrator, fit_model

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"


def load_policy(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_POLICY) as fh:
        return yaml.safe_load(fh)


def run_benchmark(truth_gdf, policy: dict | None = None, seed: int | None = None,
                  features: list[str] | None = None) -> dict:
    pol = policy or load_policy()
    cols = features or FEATURES
    seed = pol["seed"] if seed is None else seed
    bm = pol["benchmark"]
    bench = build_benchmark(truth_gdf, seed=seed, error_mix=bm["error_mix"],
                            spurious_fraction=bm["spurious_fraction"], name_variant_rate=bm["name_variant_rate"])
    A, B, truth = bench.A, bench.B, bench.truth

    pairs = candidate_pairs(A, B, pol["candidates"]["search_radius_m"])
    feats = pair_features(A, B, pairs)
    true_set = set(zip(truth.a_id, truth.b_id))
    feats["label"] = [int((a, b) in true_set) for a, b in zip(feats.a_id, feats.b_id)]

    cent = np.c_[A.geometry.centroid.x.values, A.geometry.centroid.y.values]
    mlp = pol["ml"]
    role_a = assign_roles(cent, mlp["block_size_m"], mlp["block_fractions"], seed)
    feats["role"] = role_a[feats.a_idx.values]
    tr, ca, te = (feats[feats.role == r] for r in ("train", "calib", "test"))

    # --- baseline: classic IoU thresholds
    base = pol["baseline"]
    feats["bucket_baseline"] = np.where(feats.iou >= base["accept_iou"], "accept",
                                        np.where(feats.iou >= base["review_iou"], "review", "reject"))

    # --- calibrated ML
    model = fit_model(tr, tr.label.values, seed, cols)
    cal = fit_calibrator(model.predict_proba(ca[cols])[:, 1], ca.label.values)
    p_ca = cal.predict(model.predict_proba(ca[cols])[:, 1])
    t_lo, t_hi = choose_thresholds(p_ca, ca.label.values, mlp["target_auto_precision"], mlp["max_missed_true_pairs"])
    feats["p_match"] = cal.predict(model.predict_proba(feats[cols])[:, 1])
    feats["bucket_ml"] = bucket(feats.p_match.values, t_lo, t_hi)

    test_ids = set(A.a_id[role_a == "test"])
    res = {}
    for name, col in (("IoU baseline", "bucket_baseline"), ("Calibrated XGBoost", "bucket_ml")):
        res[name] = evaluate(feats[["a_id", "b_id"]].assign(bucket=feats[col]), truth, A, B, test_ids)

    # calibration quality on held-out test pairs
    tp = feats[feats.role == "test"]
    bins = pd.cut(tp.p_match, [0, .1, .3, .5, .7, .9, 1.0], include_lowest=True)
    calib_table = (tp.groupby(bins, observed=True).agg(n=("label", "size"), mean_pred=("p_match", "mean"),
                                                         observed=("label", "mean")).round(3))
    return {
        "source": bench.source,
        "n_parcels": len(A), "n_revenue_parcels": len(B), "n_candidate_pairs": len(feats),
        "thresholds": {"auto_reject_below": t_lo, "auto_accept_at_or_above": t_hi},
        "results": res,
        "calibration_table": calib_table.reset_index().astype(str).to_dict("records"),
        "markdown": to_markdown(res),
        "_feats": feats, "_bench": bench, "_model": model, "_calibrator": cal,
    }


def save(result: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in result.items() if not k.startswith("_")}
    (out / "benchmark.json").write_text(json.dumps(clean, indent=2, default=float))
    (out / "benchmark.md").write_text(
        f"Source: {clean['source']}\n\nParcels: {clean['n_parcels']} cadastral, "
        f"{clean['n_revenue_parcels']} revenue\n\n{clean['markdown']}\n")
