#!/usr/bin/env python
"""Run the matcher on REAL, independent building datasets for the same area.

Sources (all real, open): OSM buildings (data/ward.geojson), Microsoft footprints, and optionally
Google Open Buildings. There are no planted errors here: the sources genuinely disagree. Because nobody
supplies the right answers, accuracy is measured on a stratified, hand-labelled sample (the
"Real data" page), and every number below that is not from labels is a description, not an accuracy.

Also checks buildings against OSM road reserves (estimated from road class / width tags) and lists
possible encroachments for field verification.

    python scripts/build_real.py            # uses data/ward.geojson + data/real/*
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon import coreg  # noqa: E402
from recon.realmatch import describe, save_matcher  # noqa: E402
from recon.features import FEATURES, candidate_pairs, pair_features  # noqa: E402
from recon.footprints import load_footprints  # noqa: E402
from recon.ml import assign_roles, choose_thresholds, fit_calibrator, fit_model  # noqa: E402
from recon.pipeline import load_policy  # noqa: E402
from recon.profiles import MID_MIX, MID_RANGES, prepare  # noqa: E402

COLS = [f for f in FEATURES if not f.startswith("name_")]
ROAD_HALF_WIDTH = {"motorway": 12, "trunk": 10, "primary": 8, "secondary": 6.5, "tertiary": 5.5, "unclassified": 4,
                   "residential": 3.5, "living_street": 3, "service": 2.5, "pedestrian": 2.5, "footway": 1, "path": 1,
                   "cycleway": 1, "steps": 1}
STRATA = [(0.02, 0.2, 40), (0.2, 0.5, 50), (0.5, 0.8, 60), (0.8, 0.95, 60), (0.95, 1.01, 90)]   # p range, sample size

ap = argparse.ArgumentParser()
ap.add_argument("--osm", default="data/ward.geojson")
ap.add_argument("--microsoft", default="data/real/microsoft_buildings.geojson")
ap.add_argument("--google", default="data/real/google_open_buildings_tnagar.geojson")
ap.add_argument("--roads", default="data/real/osm_roads.geojson")
ap.add_argument("--out", default="demo/real")
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--temporal", nargs=2, default=["data/real/google_temporal_2016.tif", "data/real/google_temporal_2023.tif"],
                help="Google Open Buildings Temporal GeoTIFFs (early, late) from scripts/gee_google_buildings.js")
ap.add_argument("--no-coreg", action="store_true", help="skip co-registration (to show the before/after)")
a = ap.parse_args()
pol = load_policy()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)


def load(path, label, crs=None):
    g = gpd.read_file(path)
    g = g[g.geometry.notna()].copy()
    g["geometry"] = g.geometry.make_valid()
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])].explode(index_parts=False, ignore_index=True)
    g = g.set_crs(4326, allow_override=g.crs is None) if g.crs is None else g
    g = g.to_crs(crs or g.estimate_utm_crs())
    g = g[(g.area >= 8) & (g.area <= 20000)].reset_index(drop=True)
    g = g[["geometry"]].copy()
    g["src"] = label
    return g


osm = load(a.osm, "OSM")
crs = osm.crs
sources = {"OSM": osm}
for label, path in (("Microsoft", a.microsoft), ("Google", a.google)):
    if Path(path).exists():
        sources[label] = load(path, label, crs)
if len(sources) < 2:
    raise SystemExit(f"Need at least one more source besides OSM. Missing: {a.microsoft}")
bbox = shapely.box(*osm.total_bounds).buffer(5)
for k in list(sources):
    sources[k] = sources[k][sources[k].intersects(bbox)].reset_index(drop=True)
    sources[k]["id"] = [f"{k[0]}{i:05d}" for i in range(len(sources[k]))]
    sources[k]["owner"] = ""
print({k: len(v) for k, v in sources.items()})

# ---- matcher: trained only on the synthetic benchmark built from OSM footprints, never on these pairs
truth = load_footprints(a.osm, a.seed)
# same recipe as the console's model: train and calibrate on the default + intermediate error profiles
parts = [prepare(truth, pol, a.seed + s, mix, rng)[1] for s, mix, rng in ((0, None, None), (200, MID_MIX, MID_RANGES))]
feats_tr = pd.concat(parts, ignore_index=True)
cent = np.c_[truth.geometry.centroid.x, truth.geometry.centroid.y]
roles = assign_roles(cent, pol["ml"]["block_size_m"], [0.7, 0.3, 0.0], a.seed)   # 70% train blocks, rest calibration
r = roles[feats_tr.a_idx.values]
tr, ca = feats_tr[r == "train"], feats_tr[r != "train"]
model = fit_model(tr, tr.label.values, a.seed, COLS)
cal = fit_calibrator(model.predict_proba(ca[COLS])[:, 1], ca.label.values)
t_lo, t_hi = choose_thresholds(cal.predict(model.predict_proba(ca[COLS])[:, 1]), ca.label.values,
                               pol["ml"]["target_auto_precision"], pol["ml"]["max_missed_true_pairs"])
# real data was never seen in training, so keep a review band: never auto-accept below the policy floor
t_hi = max(t_hi, pol["real"]["accept_min"])
t_lo = min(t_lo, pol["real"]["review_min"])
# the upload page reuses exactly this matcher
save_matcher(Path(a.out) / "matcher", model, cal, COLS, t_lo, t_hi, pol["candidates"]["search_radius_m"])


coreg_report = {}
aligned = {}


def score_pairs(A, B, la, lb):
    A = A.rename(columns={"id": "a_id"}); B = B.rename(columns={"id": "b_id"})
    if not a.no_coreg:                       # remove the systematic offset between the two sources first
        shift, rep = coreg.estimate(A, B)
        coreg_report[f"{la} ↔ {lb}"] = rep
        print(f"  co-registration {la} ↔ {lb}: {rep}")
        if rep.get("applied"):
            B = coreg.apply(B, shift)
    if la == "OSM":                          # keep each source in the OSM frame (roads are OSM too)
        aligned[lb] = B.rename(columns={"b_id": "id"})
    f = pair_features(A, B, candidate_pairs(A, B, pol["candidates"]["search_radius_m"]))
    f["p"] = cal.predict(model.predict_proba(f[COLS])[:, 1]) if len(f) else []
    f["bucket"] = np.where(f.p >= t_hi, "accept", np.where(f.p < t_lo, "reject", "review"))
    return f, B.rename(columns={"b_id": "id"})


comparisons, pairs_all, relations, moved = [], {}, {}, {}
names = list(sources)
for i in range(len(names)):
    for k in range(i + 1, len(names)):
        la, lb = names[i], names[k]
        f, Bm = score_pairs(sources[la], sources[lb], la, lb)
        pairs_all[(la, lb)] = f
        d, relations[(la, lb)] = describe(f, sources[la], Bm, la, lb)
        comparisons.append(d)
        print({k_: (round(v, 3) if isinstance(v, float) else v) for k_, v in d.items()})

# ---- consensus: how many sources see each OSM building
osm_seen = {i: 1 for i in sources["OSM"].id}
for (la, lb), f in pairs_all.items():
    if la == "OSM":
        rel = relations[(la, lb)]
        for a_id in set(f.a_id[f.bucket == "accept"]) | set(rel["a_in_b"]) | set(rel["b_in_a"].values()):
            osm_seen[a_id] += 1
consensus = pd.Series(osm_seen).value_counts().sort_index().to_dict()

# ---- road reserve encroachment (approximate; for field checking only)
encroach, roads_out = [], None
if Path(a.roads).exists():
    roads = gpd.read_file(a.roads).to_crs(crs)
    def half_width(row):
        # missing tags arrive as NaN, which is truthy, so test with notna explicitly
        w, ln = row.get("width"), row.get("lanes")
        try:
            if pd.notna(w) and str(w).strip():
                v = float(str(w).replace("m", " ").split()[0]) / 2
                if 0.5 <= v <= 30:
                    return v
        except ValueError:
            pass
        try:
            if pd.notna(ln) and str(ln).strip():
                return max(1.0, float(str(ln).split(";")[0]) * 3.5 / 2)
        except ValueError:
            pass
        return ROAD_HALF_WIDTH.get(row.get("highway"), 3.0)
    roads["half_w"] = [half_width(rw) for rw in roads.to_dict("records")]
    roads = roads[~roads.highway.isin(["footway", "path", "steps", "cycleway", "corridor", "bus_stop", "platform"])]
    roads = roads[roads.geom_type.isin(["LineString", "MultiLineString"])]
    reserve = gpd.GeoDataFrame(geometry=roads.geometry.buffer(roads.half_w, cap_style="flat"), crs=crs)
    reserve_u = shapely.union_all(reserve.geometry.values)
    for label in sources:
        g = sources[label] if label == "OSM" else aligned.get(label, sources[label])
        inter = shapely.area(shapely.intersection(g.geometry.values, reserve_u))
        share = inter / g.geometry.area.values
        hit = (inter > 5) & (share > 0.10)
        for idx in np.flatnonzero(hit):
            encroach.append({"source": label, "id": g.id.values[idx], "overlap_m2": round(float(inter[idx]), 1),
                             "share": round(float(share[idx]), 3)})
    rr = gpd.GeoDataFrame(geometry=[reserve_u], crs=crs).to_crs(4326)
    roads_out = json.loads(rr.to_json(drop_id=True))
# an OSM flag is stronger when another source (moved into the OSM frame) is flagged at the same place
enc = pd.DataFrame(encroach)
if len(enc):
    osm_g = sources["OSM"].set_index("id").geometry
    other = [aligned[l].set_index("id").geometry[enc.id[enc.source == l]] for l in aligned if (enc.source == l).any()]
    other_u = shapely.union_all(np.concatenate([o.values for o in other])) if other else None
    enc["confirmed_by_two_sources"] = [bool(s_ == "OSM" and other_u is not None and
                                            shapely.intersects(osm_g[i_], other_u)) for s_, i_ in zip(enc.source, enc.id)]
    # list the reference layer only: OSM buildings and roads share one frame. Other sources only confirm.
    enc_other = enc[enc.source != "OSM"].source.value_counts().to_dict()
    enc = enc[enc.source == "OSM"].reset_index(drop=True)
else:
    enc_other = {}

# ---- stratified labelling sample from OSM ↔ Microsoft (or the first comparison)
osm_ms = pairs_all.get(("OSM", "Microsoft"))
f = osm_ms if osm_ms is not None else next(iter(pairs_all.values()))
la, lb = (("OSM", "Microsoft") if osm_ms is not None else next(iter(pairs_all)))
rng = np.random.default_rng(a.seed)
sample, strata = [], []
TARGET = sum(n for *_, n in STRATA)
pools = [f[(f.p >= lo) & (f.p < hi)] for lo, hi, _ in STRATA]
alloc = [min(n, len(pl)) for (_, _, n), pl in zip(STRATA, pools)]
spare = TARGET - sum(alloc)                      # move unused sample size to strata that have more pairs
while spare > 0 and any(a_ < len(pl) for a_, pl in zip(alloc, pools)):
    for i, pl in enumerate(pools):
        if spare and alloc[i] < len(pl):
            alloc[i] += 1; spare -= 1
for (lo, hi, _), pool, n in zip(STRATA, pools, alloc):
    take = pool.iloc[rng.permutation(len(pool))[:n]]
    strata.append({"lo": lo, "hi": min(hi, 1.0), "population": int(len(pool)), "sampled": int(len(take))})
    gA = sources[la].set_index("id").geometry; gB = sources[lb].set_index("id").geometry
    gBa = aligned[lb].set_index("id").geometry if la == "OSM" and lb in aligned else gB   # offset removed
    for r in take.itertuples():
        ga = gpd.GeoSeries([gA[r.a_id], gB[r.b_id], gBa[r.b_id]], crs=crs).to_crs(4326)
        ga_m, gb_raw = gA[r.a_id], gB[r.b_id]
        inter = ga_m.intersection(gb_raw).area
        sample.append({"pair_id": f"{r.a_id}|{r.b_id}", "a": r.a_id, "b": r.b_id, "src_a": la, "src_b": lb,
                       "p": round(float(r.p), 4), "stratum": len(strata) - 1, "iou": round(float(r.iou), 3),
                       "iou_raw": round(float(inter / (ga_m.area + gb_raw.area - inter)), 3),
                       "offset_m": round(float(r.centroid_dist), 1),
                       "geom_a": json.loads(shapely.to_geojson(shapely.set_precision(ga.iloc[0], 1e-7))),
                       "geom_b": json.loads(shapely.to_geojson(shapely.set_precision(ga.iloc[1], 1e-7))),
                       "geom_b_aligned": json.loads(shapely.to_geojson(shapely.set_precision(ga.iloc[2], 1e-7)))})
rng.shuffle(sample)


# ---- layers for the map
def fc(g, status=None):
    g4 = g.to_crs(4326)
    g4["geometry"] = shapely.set_precision(g4.geometry.values, 1e-7)
    props = g4[["id"]].copy()
    if status is not None:
        props["status"] = [status.get(i, "unmatched") for i in g4.id]
    return json.loads(gpd.GeoDataFrame(props, geometry=g4.geometry).to_json(drop_id=True))


layers = {}
for label, g in sources.items():
    st = {}
    for (x, y), pf in pairs_all.items():
        if label in (x, y):
            col = "a_id" if label == x else "b_id"
            for i in pf[col][pf.bucket == "accept"]:
                st[i] = "matched"
            for i in pf[col][pf.bucket == "review"]:
                st.setdefault(i, "uncertain")
            rel = relations[(x, y)]
            for small, big in (rel["a_in_b"].items() if label == x else rel["b_in_a"].items()):
                st.setdefault(small, "part_of_larger")
            for small, big in (rel["b_in_a"].items() if label == x else rel["a_in_b"].items()):
                st.setdefault(big, "covers_several")
    layers[label] = fc(g, st)
    if label in aligned and coreg_report.get(f"OSM ↔ {label}", {}).get("applied"):
        layers[label + "_aligned"] = fc(aligned[label], st)      # same buildings, moved into the OSM frame
if roads_out:
    layers["road_reserve"] = roads_out

# ---- the real review set (OSM ↔ Microsoft) in the same shape as the synthetic console data
if osm_ms is not None and "Microsoft" in aligned:
    import xgboost as xgb
    rv = osm_ms.copy()
    auto = (rv.p >= t_hi) | (rv.iou >= 0.5)                 # rule validated on the hand-checked pairs
    rv["bucket"] = np.where(auto, "accept", np.where(rv.p < t_lo, "reject", "review"))
    rv = rv[rv.bucket != "reject"].reset_index(drop=True)
    contrib = model.get_booster().predict(xgb.DMatrix(rv[COLS]), pred_contribs=True)[:, :-1]
    rpairs = [{"a": r.a_id, "b": r.b_id, "p": round(float(r.p), 4), "bucket": r.bucket, "iou": round(float(r.iou), 3),
               "centroid": round(float(r.centroid_dist), 1), "area_ratio": round(float(r.area_ratio), 3),
               "name_sim": None, "owner_a": "—", "owner_b": "—", "t_hi": round(float(t_hi), 4), "t_lo": round(float(t_lo), 4),
               "auto_by": "model" if r.p >= t_hi else ("overlap" if r.bucket == "accept" else None),
               "contrib": sorted(((c, round(float(v), 3)) for c, v in zip(COLS, row)), key=lambda t: -abs(t[1]))[:4]}
              for r, row in zip(rv.itertuples(), contrib)]
    st = {}
    for col in ("a_id",):
        for i in rv[col][rv.bucket == "review"]:
            st[i] = "review"
        for i in rv[col][rv.bucket == "accept"]:
            st[i] = "auto"
    og = sources["OSM"].assign(status=[st.get(i, "unmatched") for i in sources["OSM"].id], owner="—").to_crs(4326)
    og["geometry"] = shapely.set_precision(og.geometry.values, 1e-7)
    mg = aligned["Microsoft"].to_crs(4326)
    mg["geometry"] = shapely.set_precision(mg.geometry.values, 1e-7)
    rsum = {"source": "OpenStreetMap ↔ Microsoft building footprints, T. Nagar (real, co-registered)",
            "names": {"a": "OSM", "b": "Microsoft", "a_long": "OSM building", "b_long": "Microsoft footprint"},
            "n_cadastral": len(og), "n_revenue": len(mg),
            "thresholds": {"reject_below": float(t_lo), "accept_at_or_above": float(t_hi), "iou_accept": 0.5},
            "auto_rule": f"model ≥ {t_hi:.0%} or outline overlap (IoU) ≥ 0.5 after co-registration",
            "n_auto_parcels": sum(v == "auto" for v in st.values()), "n_review_parcels": sum(v == "review" for v in st.values()),
            "coregistration": coreg_report.get("OSM ↔ Microsoft"),
            "notes": ["Both layers are real and independent; nothing is planted. Microsoft is shown after co-registration.",
                      "Accuracy figures come from the hand-checked sample on the Real data page and update as more pairs are checked.",
                      "There are no owner names on building maps, so only geometry is used."]}
    (out / "review.json").write_text(json.dumps({"summary": rsum, "pairs": rpairs,
        "layers": {"A": json.loads(og[["id", "status", "owner", "geometry"]].to_json(drop_id=True)),
                   "B": json.loads(mg[["id", "geometry"]].to_json(drop_id=True))}}))
    print(f"review set: {sum(p['bucket'] == 'accept' for p in rpairs)} auto, {sum(p['bucket'] == 'review' for p in rpairs)} to review")

(out / "real_layers.json").write_text(json.dumps(layers))
(out / "real_sample.json").write_text(json.dumps({"strata": strata, "pairs": sample, "thresholds": {"accept": t_hi, "reject": t_lo}}))
(out / "real.json").write_text(json.dumps({
    "sources": {k: len(v) for k, v in sources.items()}, "crs": f"EPSG:{crs.to_epsg()}",
    "comparisons": comparisons, "consensus_osm": {int(k): int(v) for k, v in consensus.items()},
    "thresholds": {"accept": t_hi, "reject": t_lo},
    "encroachment": enc.to_dict("records") if len(enc) else [],
    "encroachment_other_sources": {k: int(v) for k, v in enc_other.items()},
    "coregistration": coreg_report,
    "consensus_rule": "an OSM building counts as seen by a source when the model auto-links it or it lies inside a larger polygon of that source",
    "notes": ["All three building datasets are real and independent; nothing was planted.",
              "The matcher was trained only on synthetic errors built from OSM footprints; these real pairs were never seen.",
              "Accuracy on real data comes only from the hand-labelled sample. Other numbers describe disagreement, not accuracy.",
              "Before matching, each pair of sources is co-registered: a local shift field from confident anchor buildings removes the few-metre offset between maps traced from different imagery.",
              "One-to-many relations (one source traces a terrace or block as one polygon, another as several) are reported separately from one-to-one links.",
              "Road reserves are estimated from OSM road class and width tags; encroachment flags are candidates for a field check."],
}, indent=1, default=float))
(out / "labels.jsonl").touch()

# ---- real change detection 2016 -> 2023 (Google Open Buildings Temporal), confirmed against independent maps
if all(Path(t).exists() for t in a.temporal):
    try:
        from recon import temporal
        import rasterio
        with rasterio.open(a.temporal[0]) as _r:
            tcrs = _r.crs
        cur = {k: (aligned.get(k, v) if k != "OSM" else v).to_crs(tcrs) for k, v in sources.items()}
        res = temporal.analyse(a.temporal[0], a.temporal[1], cur, sources["OSM"].to_crs(tcrs))
        geo = gpd.GeoDataFrame([p for _, p in res["features"]], geometry=[g for g, _ in res["features"]], crs=tcrs).to_crs(4326)
        geo["geometry"] = shapely.set_precision(geo.geometry.values, 1e-7)
        (out / "temporal.json").write_text(json.dumps({"summary": res["summary"], "features": json.loads(geo.to_json(drop_id=True))}))
        print("temporal 2016->2023:", {k: v for k, v in res["summary"].items() if k not in ("rules",)})
    except ImportError:
        print("temporal change skipped: pip install rasterio")
print(f"thresholds accept>={t_hi:.3f} reject<{t_lo:.3f}; sample {len(sample)} pairs; encroachment candidates {len(enc)}; consensus {consensus}")
print(f"wrote {out}/real.json, real_layers.json, real_sample.json")
