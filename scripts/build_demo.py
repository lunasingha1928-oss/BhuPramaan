#!/usr/bin/env python
"""Build the data behind the review console.

Out-of-fold design: the ward is cut into spatial folds. For every fold, a model is trained and
calibrated on OTHER folds (using a mix of error profiles) and then scores this fold's parcels,
which it has never seen, against a harsh error profile it was NOT trained on. So every pair shown
in the console was scored by a model that never saw that part of the map.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon.evaluate import evaluate  # noqa: E402
from recon.features import FEATURES  # noqa: E402
from recon.footprints import load_footprints, synthetic_footprints  # noqa: E402
from recon.ml import bucket, choose_thresholds, fit_calibrator, fit_model  # noqa: E402
from recon.pipeline import load_policy  # noqa: E402
from recon.profiles import (MID_MIX, MID_RANGES, SHIFT_DESCRIPTION, SHIFT_MIX, SHIFT_RANGES,  # noqa: E402
                            prepare)

COLS = [f for f in FEATURES if not f.startswith("name_")]   # geometry-only score; names shown, not scored

ap = argparse.ArgumentParser()
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--input")
g.add_argument("--synthetic", type=int)
ap.add_argument("--out", default="demo")
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--folds", type=int, default=4)
a = ap.parse_args()

pol = load_policy()
mlp = pol["ml"]
seed = a.seed
truth = load_footprints(a.input, seed) if a.input else synthetic_footprints(a.synthetic, seed)
source = truth.attrs.get("source", "")

b1, f1 = prepare(truth, pol, seed, None, None)                      # training profile 1 (policy default)
b3, f3 = prepare(truth, pol, seed + 200, MID_MIX, MID_RANGES)       # training profile 2 (intermediate)
b2, f2 = prepare(truth, pol, seed + 100, SHIFT_MIX, SHIFT_RANGES)   # the case shown to the officer (harsh, unseen)

# spatial folds by block
cent = np.c_[b1.A.geometry.centroid.x.values, b1.A.geometry.centroid.y.values]
bx = np.floor((cent[:, 0] - cent[:, 0].min()) / mlp["block_size_m"]).astype(int)
by = np.floor((cent[:, 1] - cent[:, 1].min()) / mlp["block_size_m"]).astype(int)
keys = bx * 100003 + by
uniq = np.unique(keys)
np.random.default_rng(seed).shuffle(uniq)
fold_of = {k: i % a.folds for i, k in enumerate(uniq)}
fold_a = np.array([fold_of[k] for k in keys])

out_rows, thr, models = [], [], {}
for k in range(a.folds):
    cal_fold = (k + 1) % a.folds
    def pick(f, fold_arr, want):
        return f[np.isin(fold_arr[f.a_idx.values], want)]
    train_rows = pd.concat([pick(f1, fold_a, [x for x in range(a.folds) if x not in (k, cal_fold)]),
                            pick(f3, fold_a, [x for x in range(a.folds) if x not in (k, cal_fold)])])
    cal_rows = pd.concat([pick(f1, fold_a, [cal_fold]), pick(f3, fold_a, [cal_fold])])
    model = fit_model(train_rows, train_rows.label.values, seed, COLS)
    cal = fit_calibrator(model.predict_proba(cal_rows[COLS])[:, 1], cal_rows.label.values)
    t_lo, t_hi = choose_thresholds(cal.predict(model.predict_proba(cal_rows[COLS])[:, 1]), cal_rows.label.values,
                                   mlp["target_auto_precision"], mlp["max_missed_true_pairs"])
    thr.append((t_lo, t_hi))
    models[k] = (model, cal, t_lo, t_hi)
    test = pick(f2, fold_a, [k]).copy()
    test["p"] = cal.predict(model.predict_proba(test[COLS])[:, 1])
    test["bucket"] = bucket(test.p.values, t_lo, t_hi)
    test["t_lo"], test["t_hi"] = t_lo, t_hi            # each spatial fold has its own calibrated thresholds
    contrib = model.get_booster().predict(xgb.DMatrix(test[COLS]), pred_contribs=True)[:, :-1]
    test["contrib"] = [json.dumps(sorted(((c, float(v)) for c, v in zip(COLS, row)), key=lambda t: -abs(t[1]))[:4])
                       for row in contrib]
    out_rows.append(test)

oof = pd.concat(out_rows, ignore_index=True)
all_ids = set(b2.A.a_id)
res_ml = evaluate(oof[["a_id", "b_id"]].assign(bucket=oof.bucket), b2.truth, b2.A, b2.B, all_ids)
base_b = np.where(oof.iou >= pol["baseline"]["accept_iou"], "accept",
                  np.where(oof.iou >= pol["baseline"]["review_iou"], "review", "reject"))
res_base = evaluate(oof[["a_id", "b_id"]].assign(bucket=base_b), b2.truth, b2.A, b2.B, all_ids)

# ---- statuses
def status(ids, pairs, col):
    st = {i: "unmatched" for i in ids}
    for i in pairs.loc[pairs.bucket == "accept", col]:
        st[i] = "auto"
    for i in pairs.loc[pairs.bucket == "review", col]:
        st[i] = "review"
    return st

st_a, st_b = status(b2.A.a_id, oof, "a_id"), status(b2.B.b_id, oof, "b_id")

out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)


def layer(gdf, idcol, st):
    g = gdf.to_crs(4326).copy()
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-7)
    feats = []
    for _, r in g.iterrows():
        feats.append({"type": "Feature", "properties": {"id": r[idcol], "owner": r["owner"], "status": st[r[idcol]]},
                      "geometry": json.loads(shapely.to_geojson(r.geometry))})
    return {"type": "FeatureCollection", "features": feats}


(out / "layers.json").write_text(json.dumps({"A": layer(b2.A, "a_id", st_a), "B": layer(b2.B, "b_id", st_b)}))

keep = oof[oof.bucket != "reject"].copy()
an, bn = b2.A.set_index("a_id").owner, b2.B.set_index("b_id").owner
pairs = [{"a": r.a_id, "b": r.b_id, "p": round(float(r.p), 4), "bucket": r.bucket, "iou": round(float(r.iou), 3),
          "centroid": round(float(r.centroid_dist), 1), "area_ratio": round(float(r.area_ratio), 3),
          "name_sim": round(float(r.name_sort), 2), "owner_a": an[r.a_id], "owner_b": bn[r.b_id],
          "t_lo": round(float(r.t_lo), 4), "t_hi": round(float(r.t_hi), 4), "auto_by": "model" if r.bucket == "accept" else None,
          "contrib": json.loads(r.contrib)} for r in keep.itertuples()]
(out / "pairs.json").write_text(json.dumps(pairs))

link_set = set(zip(b2.truth.a_id, b2.truth.b_id))
(out / "truth.json").write_text(json.dumps({
    "links": [f"{x}|{y}" for x, y in sorted(link_set)],
    "a_type": dict(zip(b2.A.a_id, b2.A.error_type)), "b_type": dict(zip(b2.B.b_id, b2.B.error_type))}))

t_lo = float(np.mean([t[0] for t in thr]))
t_hi = float(np.mean([t[1] for t in thr]))
edges = np.linspace(0, 1, 11)
bin_idx = np.clip(np.digitize(oof.p.values, edges) - 1, 0, 9)
calibration = []
for i in range(10):
    m = bin_idx == i
    if m.sum():
        calibration.append({"lo": float(edges[i]), "hi": float(edges[i + 1]), "n": int(m.sum()),
                            "mean_pred": float(oof.p.values[m].mean()), "observed": float(oof.label.values[m].mean())})

summary = {
    "source": source, "n_cadastral": len(b2.A), "n_revenue": len(b2.B), "n_candidates": len(oof),
    "folds": a.folds, "target_auto_precision": mlp["target_auto_precision"],
    "thresholds": {"reject_below": t_lo, "accept_at_or_above": t_hi,
                   "per_fold": [{"reject_below": float(a_), "accept_at_or_above": float(b_)} for a_, b_ in thr]},
    "n_auto_pairs": int((oof.bucket == "accept").sum()), "n_review_pairs": int((oof.bucket == "review").sum()),
    "n_review_parcels": sum(1 for v in st_a.values() if v == "review"),
    "n_auto_parcels": sum(1 for v in st_a.values() if v == "auto"),
    "n_unmatched_parcels": sum(1 for v in st_a.values() if v == "unmatched"),
    "metrics": {"model": res_ml, "baseline": res_base},
    "calibration": calibration,
    "shift_description": SHIFT_DESCRIPTION,
    "notes": ["Footprints are real; injected errors and owner names are synthetic.",
              "Every pair was scored by a model that never saw that part of the map (out-of-fold).",
              "The case shown uses a harsher error profile than the model was trained on.",
              "Owner-name similarity is shown to the officer but is not part of the score."],
}
(out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
(out / "decisions.jsonl").touch()

m, b = res_ml, res_base
print(f"{source}: {len(b2.A)} cadastral / {len(b2.B)} revenue parcels, {len(oof)} candidate pairs")
print(f"thresholds reject<{t_lo:.3f}  accept>={t_hi:.3f}")
print(f"MODEL    precision {m['auto_precision']:.1%}  recall {m['auto_recall']:.1%}  F1 {m['auto_f1']:.1%}  "
      f"no-review {m['auto_resolved_share']:.1%}")
print(f"BASELINE precision {b['auto_precision']:.1%}  recall {b['auto_recall']:.1%}  F1 {b['auto_f1']:.1%}  "
      f"no-review {b['auto_resolved_share']:.1%}")
print(f"review queue: {summary['n_review_pairs']} pairs / {summary['n_review_parcels']} parcels -> {out}/")


# ======================================================================================
# Integration modules: topology, coordinate systems, attribute mapping, harmonised layer, changes
# ======================================================================================
from recon import changes as chg  # noqa: E402
from recon import topology  # noqa: E402
from recon.attributes import infer_area_unit, match_schema  # noqa: E402
from recon.features import candidate_pairs, pair_features  # noqa: E402
from recon.integrate import (assign_land_use, harmonise, join_points, make_revenue_table,  # noqa: E402
                             make_tax_points)

tp, ip, cp = pol["topology"], pol["integration"], pol["changes"]
A, B = b2.A, b2.B

# ---- topology: revenue layer as received (with digitisation faults) and the cadastral layer
B_recv, n_defects = topology.add_digitisation_defects(B, tp["defect_rate"], seed)
best_p_b = oof.groupby("b_id").p.max().reindex(B.b_id).fillna(0).values
B_fixed, act_b, topo_b0, topo_b1 = topology.repair(B_recv, best_p_b, tp)
A_fixed, act_a, topo_a0, topo_a1 = topology.repair(A, None, tp)
topo_flags = {aid: "repaired" for aid in A_fixed.a_id[A_fixed.topology_repaired]}
def _count(actions):
    c = {}
    for x in actions:
        c[x["action"]] = c.get(x["action"], 0) + 1
    return c

# ---- departmental sources
land_use_a = dict(zip(A.a_id, assign_land_use(A, seed)))
rev, inj_rev = make_revenue_table(A, B, b2.truth, land_use_a, seed)
tax, inj_tax = make_tax_points(A, land_use_a, seed)

# ---- coordinate systems: each source is delivered in its own CRS, then read back and transformed
inp = out / "inputs"
inp.mkdir(exist_ok=True)
work_crs = A.crs
deliveries = [
    ("Cadastral survey layer", "cadastral_survey.gpkg", A_fixed[["a_id", "owner", "geometry"]].rename(columns={"a_id": "Parcel_ID", "owner": "Owner"})),
    ("Revenue record layer", "revenue_records_epsg7755.gpkg",
     B_recv.merge(rev, on="b_id").drop(columns=["owner", "error_type"]).to_crs(7755)),
    ("Municipal property-tax points", "property_tax_points_wgs84.geojson", tax.drop(columns=["a_true"])),
]
crs_report = []
for label, fname, g in deliveries:
    path = inp / fname
    if path.exists():
        path.unlink()
    g.to_file(path)
    back = __import__("geopandas").read_file(path)
    w = back.to_crs(work_crs)
    rt = w.to_crs(back.crs).to_crs(work_crs)
    err = float(np.max(shapely.hausdorff_distance(w.geometry.values, rt.geometry.values)))
    crs_report.append({"source": label, "file": fname, "features": len(back), "delivered_crs": f"EPSG:{back.crs.to_epsg()}",
                       "delivered_crs_name": back.crs.name, "working_crs": f"EPSG:{work_crs.to_epsg()}",
                       "working_crs_name": work_crs.name, "round_trip_error_m": round(err, 6)})

# ---- schema matching (columns as delivered) and unit inference
rev_cols = rev.drop(columns=["b_id"])
tax_cols = pd.DataFrame(tax.drop(columns=["a_true", "geometry"]))
rev_schema, tax_schema = match_schema(rev_cols), match_schema(tax_cols)
rev_truth = {"Patta_No": "parcel_ref", "Pattadar_Name": "owner_name", "Extent": "area", "Classfn": "land_use", "SF_No": "survey_no"}
tax_truth = {"Assessment_No": "parcel_ref", "Assessee": "owner_name", "Plinth_Area_SqFt": "area", "Usage": "land_use"}
for sch, t in ((rev_schema, rev_truth), (tax_schema, tax_truth)):
    for m in sch:
        m["correct"] = (t.get(m["column"]) == m["field"])
rev_map = {m["column"]: m["field"] for m in rev_schema if m["field"]}
tax_map = {m["column"]: m["field"] for m in tax_schema if m["field"]}
links = oof[oof.bucket == "accept"][["a_id", "b_id", "p"]]
one_to_one = links[links.groupby("a_id").b_id.transform("nunique").eq(1) & links.groupby("b_id").a_id.transform("nunique").eq(1)]
a_area = dict(zip(A_fixed.a_id, A_fixed.geometry.area))
area_col_rev = next(c for c, f in rev_map.items() if f == "area")
area_col_tax = next(c for c, f in tax_map.items() if f == "area")
revi = rev.set_index("b_id")
unit_rev = infer_area_unit(revi.loc[one_to_one.b_id, area_col_rev].astype(float).values,
                           np.array([a_area[x] for x in one_to_one.a_id]))
tax_join = join_points(A_fixed, tax)
unit_tax = infer_area_unit(tax.loc[tax_join.index, area_col_tax].astype(float).values,
                           np.array([a_area[x] for x in tax_join.values]))
unit_truth = {"revenue": "cent", "tax": "square foot"}
join_ok = float(np.mean([tax.a_true.iloc[i] == a for i, a in tax_join.items()]))

# ---- harmonised layer
harm, conflicts = harmonise(A_fixed, B, links, rev, unit_rev["unit"], rev_map, tax, tax_join, unit_tax["unit"], tax_map,
                            land_use_a, topo_flags, ip)
# conflict detection measured against what was injected
b_to_a = b2.truth.groupby("b_id").a_id.apply(list).to_dict()
true_c = {"owner": set(inj_tax["owner"]), "area": set(), "land_use": set(inj_tax["land_use"])}
for b in inj_rev["owner"]:
    true_c["owner"].update(b_to_a.get(b, []))
for b in inj_rev["land_use"]:
    true_c["land_use"].update(b_to_a.get(b, []))
checkable_area = set(harm.parcel_id[harm.link_type.eq("1:1")])
for b in inj_rev["area"]:
    true_c["area"].update(a for a in b_to_a.get(b, []) if a in checkable_area)
det = {k: {c["parcel_id"] for c in conflicts if c["type"] == k} for k in ("owner", "area", "land_use")}
conflict_metrics = {}
for k in det:
    d, t = det[k], true_c[k]
    conflict_metrics[k] = {"injected": len(t), "flagged": len(d), "correct": len(d & t),
                           "precision": len(d & t) / len(d) if d else 1.0, "recall": len(d & t) / len(t) if t else 1.0}

h4326 = harm.to_crs(4326)
h4326["geometry"] = shapely.set_precision(h4326.geometry.values, 1e-7)
(out / "harmonised.json").write_text(h4326.to_json(drop_id=True, na="drop"))
bands = harm.band.value_counts().to_dict()
hist = np.histogram(harm.confidence.values, bins=10, range=(0, 100))[0].tolist()

# ---- change detection against a later survey with known changes
later, ch_truth = chg.make_later_epoch(A_fixed, seed)
L = later.rename(columns={"l_id": "b_id"}).assign(owner="")
cpairs = candidate_pairs(A_fixed, L, pol["candidates"]["search_radius_m"])
cf = pair_features(A_fixed, L, cpairs)
cf["p"] = 0.0
for k, (model, cal, lo, hi) in models.items():
    m = fold_a[cf.a_idx.values] == k
    if m.any():
        cf.loc[m, "p"] = cal.predict(model.predict_proba(cf.loc[m, COLS])[:, 1])
cf["area_e"] = A_fixed.geometry.area.values[cf.a_idx]
cf["area_l"] = L.geometry.area.values[cf.b_idx]
pred = chg.classify(cf.rename(columns={"a_id": "earlier_id", "b_id": "later_id"}), A_fixed.a_id.tolist(), L.b_id.tolist(),
                    float(np.mean([t[0] for t in thr])), cp["altered_area_ratio"])
ch_scores = chg.score(pred, ch_truth)
gA, gL = A_fixed.set_index("a_id").geometry, L.set_index("b_id").geometry
truth_keys = {(r.earlier_id or "", r.later_id or ""): r.change for r in ch_truth.itertuples()}
feats_ch = []
for r in pred[pred.change != "unchanged"].itertuples():
    geom = gL[r.later_id] if isinstance(r.later_id, str) else gA[r.earlier_id]
    feats_ch.append({"change": r.change, "earlier_id": r.earlier_id if isinstance(r.earlier_id, str) else None,
                     "later_id": r.later_id if isinstance(r.later_id, str) else None,
                     "area_change_pct": None if pd.isna(r.area_change_pct) else r.area_change_pct,
                     "truth": truth_keys.get((r.earlier_id if isinstance(r.earlier_id, str) else "", r.later_id if isinstance(r.later_id, str) else ""), "none"),
                     "geometry": geom})
ch_gdf = __import__("geopandas").GeoDataFrame(feats_ch, crs=A.crs).to_crs(4326)
(out / "changes.json").write_text(json.dumps({
    "summary": {"earlier_parcels": len(A_fixed), "later_parcels": len(L), "scores": ch_scores,
                "counts": pred.change.value_counts().to_dict()},
    "features": json.loads(ch_gdf.to_json(drop_id=True))}, default=float))

quality = {
    "topology": {
        "revenue": {"before": topo_b0, "after": topo_b1, "defects_injected": n_defects, "actions": _count(act_b)},
        "cadastral": {"before": topo_a0, "after": topo_a1, "actions": _count(act_a)},
        "settings": tp},
    "crs": crs_report,
    "schema": {"revenue": rev_schema, "tax": tax_schema},
    "units": {"revenue": {**unit_rev, "column": area_col_rev, "truth": unit_truth["revenue"]},
              "tax": {**unit_tax, "column": area_col_tax, "truth": unit_truth["tax"]}},
    "tax_join": {"points": len(tax), "joined": int(len(tax_join)), "correct_share": join_ok},
    "conflicts": {"metrics": conflict_metrics, "by_type": {k: len(v) for k, v in det.items()},
                  "parcels_with_conflicts": int((harm.n_conflicts > 0).sum()), "list": conflicts[:500]},
    "confidence": {"bands": bands, "histogram": hist, "mean": float(harm.confidence.mean()),
                   "formula": "100 x spatial (calibrated link probability) x source reliability x topology factor x attribute factor"},
}
(out / "quality.json").write_text(json.dumps(quality, indent=1, default=float))

summary["modules"] = {
    "topology_errors": {"revenue_before": topo_b0["invalid"] + topo_b0["overlaps"] + topo_b0["slivers"],
                        "revenue_after": topo_b1["invalid"] + topo_b1["overlaps"] + topo_b1["slivers"]},
    "schema_correct": f"{sum(m['correct'] for m in rev_schema + tax_schema if m['field'])}/{len(rev_truth) + len(tax_truth)}",
    "units": f"{unit_rev['unit']}, {unit_tax['unit']}",
    "conflict_recall": float(np.mean([v["recall"] for v in conflict_metrics.values()])),
    "conflict_precision": float(np.mean([v["precision"] for v in conflict_metrics.values()])),
    "change_recall": float(np.mean([ch_scores[k]["recall"] for k in ("new", "demolished", "altered")])),
    "change_precision": float(np.mean([ch_scores[k]["precision"] for k in ("new", "demolished", "altered")])),
    "confidence_high_share": bands.get("High", 0) / len(harm),
    "sources": 3, "crs_handled": sorted({c["delivered_crs"] for c in crs_report}),
}
summary["notes"].append("Attribute values (owners, areas, land use, tax records) and the later survey are synthetic, with known injected conflicts and changes.")
(out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

print(f"topology revenue: {topo_b0} -> {topo_b1}")
print(f"crs: {[(c['source'], c['delivered_crs'], c['round_trip_error_m']) for c in crs_report]}")
print(f"schema rev: {[(m['column'], m['field'], m['confidence'], m['correct']) for m in rev_schema]}")
print(f"schema tax: {[(m['column'], m['field'], m['confidence'], m['correct']) for m in tax_schema]}")
print(f"units: rev={unit_rev}  tax={unit_tax}  tax join correct={join_ok:.3f}")
print(f"conflicts: {conflict_metrics}")
print(f"confidence bands: {bands}")
print(f"changes: {ch_scores}")
