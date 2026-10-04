"""Multi-source integration: build the extra departmental sources, then fuse everything into one
harmonised parcel layer with per-attribute authority and a 0-100 confidence score.

Sources (all derived from real footprints; attribute values are synthetic and labelled so):
  * Cadastral survey layer  - geometry authority (EPSG: local UTM)
  * Revenue record layer    - ownership + recorded extent authority (delivered in EPSG:7755, area in cents)
  * Municipal property-tax points - assessment number, plinth area, usage (delivered in EPSG:4326, sq ft)
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point

from .attributes import UNITS, norm_land_use, owner_similarity
from .names import random_name, variant

LAND_USES = ["Residential", "Commercial", "Mixed"]
REV_CODES = {"Residential": ["RES", "Natham", "Residential"], "Commercial": ["COM", "Commercial"], "Mixed": ["MIX", "Res cum Com"]}
TAX_CODES = {"Residential": ["R", "Dwelling"], "Commercial": ["C", "Shop"], "Mixed": ["M", "Mixed"]}


def _other_name(name: str, rng) -> str:
    while True:
        n = random_name(rng)
        if owner_similarity(n, name) < 0.7:
            return n


def assign_land_use(A: gpd.GeoDataFrame, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 5)
    return rng.choice(LAND_USES, size=len(A), p=[0.7, 0.2, 0.1])


def make_revenue_table(A, B, truth_links: pd.DataFrame, land_use_a: dict, seed: int, conflict_rate=0.04):
    """Revenue records for every revenue-layer parcel, Tamil Nadu style columns, area in cents."""
    rng = np.random.default_rng(seed + 11)
    a_area = dict(zip(A.a_id, A.geometry.area))
    a_owner = dict(zip(A.a_id, A.owner))
    true_a = truth_links.groupby("b_id").a_id.apply(list).to_dict()
    rows, injected = [], {"owner": set(), "area": set(), "land_use": set()}
    for k, r in enumerate(B.itertuples()):
        a_ids = true_a.get(r.b_id, [])
        legal_area = sum(a_area[a] for a in a_ids) if a_ids else r.geometry.area
        lu = land_use_a.get(a_ids[0], "Residential") if a_ids else rng.choice(LAND_USES)
        owner = r.owner
        if a_ids and rng.random() < conflict_rate:
            owner = _other_name(a_owner[a_ids[0]], rng); injected["owner"].add(r.b_id)
        area = legal_area * rng.normal(1, 0.015)
        if a_ids and rng.random() < conflict_rate:
            area *= rng.choice([rng.uniform(0.55, 0.75), rng.uniform(1.3, 1.6)]); injected["area"].add(r.b_id)
        if a_ids and rng.random() < conflict_rate:
            lu = rng.choice([x for x in LAND_USES if x != lu]); injected["land_use"].add(r.b_id)
        rows.append({"b_id": r.b_id, "Patta_No": f"PT/{2000 + k}", "Pattadar_Name": owner,
                     "Extent": round(area / UNITS["cent"], 3), "Classfn": rng.choice(REV_CODES[lu]),
                     "SF_No": f"{rng.integers(1, 400)}/{rng.integers(1, 20)}{rng.choice(list('ABC'))}"})
    return pd.DataFrame(rows), injected


def make_tax_points(A, land_use_a: dict, seed: int, coverage=0.9, conflict_rate=0.04):
    """Municipal property-tax register as GPS points (EPSG:4326), plinth area in square feet."""
    rng = np.random.default_rng(seed + 13)
    rows, injected = [], {"owner": set(), "land_use": set()}
    for r in A.itertuples():
        if rng.random() > coverage:
            continue
        p = r.geometry.representative_point()
        lu = land_use_a[r.a_id]
        owner = variant(r.owner, rng) if rng.random() < 0.3 else r.owner
        if rng.random() < conflict_rate:
            owner = _other_name(r.owner, rng); injected["owner"].add(r.a_id)
        if rng.random() < conflict_rate:
            lu = rng.choice([x for x in LAND_USES if x != lu]); injected["land_use"].add(r.a_id)
        rows.append({"a_true": r.a_id, "Assessment_No": f"CHN/{136}/{len(rows):05d}", "Assessee": owner,
                     "Plinth_Area_SqFt": round(r.geometry.area / UNITS["square foot"] * rng.normal(1, 0.02)),
                     "Usage": rng.choice(TAX_CODES[lu]),
                     "geometry": Point(p.x + rng.normal(0, 1.5), p.y + rng.normal(0, 1.5))})
    pts = gpd.GeoDataFrame(rows, crs=A.crs).to_crs(4326)
    return pts, injected


def join_points(A: gpd.GeoDataFrame, pts: gpd.GeoDataFrame, max_dist=3.0) -> pd.Series:
    """Point-in-polygon, falling back to the nearest parcel within max_dist metres."""
    p = pts.to_crs(A.crs)
    tree = shapely.STRtree(A.geometry.values)
    idx_pt, idx_a = tree.query(p.geometry.values, predicate="within")
    hit = dict(zip(idx_pt.tolist(), idx_a.tolist()))
    miss = [i for i in range(len(p)) if i not in hit]
    if miss:
        ii, aa = tree.query_nearest(p.geometry.values[miss], max_distance=max_dist, all_matches=False)
        for i, a in zip(ii.tolist(), aa.tolist()):
            hit[miss[i]] = a
    return pd.Series({i: A.a_id.values[a] for i, a in hit.items()})


def confidence(spatial: float, sources: list[str], topo: str, n_conflicts: int, cfg: dict) -> dict:
    rel = cfg["source_reliability"]
    # geometry comes from the cadastral survey, ownership from the revenue record; a matching
    # municipal-tax record adds a small corroboration bonus
    source = (rel["cadastral"] + rel["revenue"]) / 2 if "revenue" in sources else rel["cadastral"]
    if "municipal_tax" in sources:
        source = min(1.0, source + cfg["corroboration_bonus"])
    topo_f = cfg["topology_factor"][topo]
    attr_f = max(cfg["attribute_floor"], 1 - cfg["attribute_penalty"] * n_conflicts)
    score = 100 * spatial * source * topo_f * attr_f
    band = "High" if score >= cfg["bands"]["high"] else "Medium" if score >= cfg["bands"]["medium"] else "Low"
    return {"confidence": round(score), "band": band, "spatial": round(spatial, 3), "source": round(source, 3),
            "topology": topo_f, "attributes": round(attr_f, 2)}


def harmonise(A, B, links: pd.DataFrame, rev: pd.DataFrame, rev_unit: str, rev_map: dict,
              tax: gpd.GeoDataFrame, tax_join: pd.Series, tax_unit: str, tax_map: dict,
              land_use_a: dict, topo_flags: dict, cfg: dict) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """One record per cadastral parcel. links: a_id, b_id, p (accepted links only)."""
    revf = rev.set_index("b_id")
    col = {v: k for k, v in rev_map.items()}          # canonical field -> revenue column
    tcol = {v: k for k, v in tax_map.items()}
    tax_by_a = {}
    for i, a in tax_join.items():
        tax_by_a.setdefault(a, []).append(i)
    b_links = links.groupby("b_id").a_id.nunique().to_dict()
    by_a = {a: g.sort_values("p", ascending=False) for a, g in links.groupby("a_id")}
    rows, conflicts = [], []
    for r in A.itertuples():
        surveyed = r.geometry.area
        rec = {"parcel_id": r.a_id, "geometry": r.geometry, "surveyed_area_m2": round(surveyed, 1),
               "land_use_cadastral": land_use_a[r.a_id], "owner_cadastral": r.owner}
        sources, found = ["cadastral"], []
        lk = by_a.get(r.a_id)
        spatial = 0.0
        if lk is not None:
            best = lk.iloc[0]
            spatial = float(best.p)
            rr = revf.loc[best.b_id]
            sources.append("revenue")
            rec.update({"revenue_ids": ",".join(lk.b_id), "patta_no": rr[col["parcel_ref"]],
                        "owner": rr[col["owner_name"]], "survey_no": rr[col["survey_no"]],
                        "link_type": "1:1" if len(lk) == 1 and b_links.get(best.b_id, 1) == 1 else
                                     ("split" if len(lk) > 1 else "merge")})
            if rec["link_type"] == "1:1":
                rec["recorded_area_m2"] = round(float(rr[col["area"]]) * UNITS[rev_unit], 1)
                diff = (rec["recorded_area_m2"] - surveyed) / surveyed
                rec["area_diff_pct"] = round(100 * diff, 1)
                if abs(diff) > cfg["area_tolerance"]:
                    found.append(("area", f"recorded {rec['recorded_area_m2']:.0f} m² vs surveyed {surveyed:.0f} m²", best.b_id))
            lu_rev = norm_land_use(rr[col["land_use"]])
            rec["land_use"] = lu_rev
            # a merged revenue record carries one classification for several parcels, so it is not compared
            if lu_rev and lu_rev != land_use_a[r.a_id] and rec["link_type"] != "merge":
                found.append(("land_use", f"revenue says {lu_rev}, cadastral says {land_use_a[r.a_id]}", best.b_id))
        else:
            rec.update({"owner": r.owner, "land_use": land_use_a[r.a_id], "link_type": "unmatched"})
        ti = tax_by_a.get(r.a_id, [])
        if ti:
            t = tax.iloc[ti[0]]
            sources.append("municipal_tax")
            rec.update({"assessment_no": t[tcol["parcel_ref"]], "assessee": t[tcol["owner_name"]],
                        "plinth_area_m2": round(float(t[tcol["area"]]) * UNITS[tax_unit], 1),
                        "usage_tax": norm_land_use(t[tcol["land_use"]])})
            # a merged revenue record names one owner for several parcels, so compare the tax record
            # with the cadastral owner of this parcel instead
            ref_owner, ref_label = ((r.owner, "cadastral owner") if rec.get("link_type") == "merge"
                                    else (rec["owner"], "revenue owner"))
            if owner_similarity(ref_owner, t[tcol["owner_name"]]) < cfg["owner_similarity_min"]:
                found.append(("owner", f"{ref_label} '{ref_owner}' vs tax assessee '{t[tcol['owner_name']]}'", t["a_true"]))
            if rec.get("usage_tax") and rec["usage_tax"] != land_use_a[r.a_id] and not any(f[0] == "land_use" for f in found):
                found.append(("land_use", f"tax usage {rec['usage_tax']}, cadastral says {land_use_a[r.a_id]}", t["a_true"]))
        if lk is not None and rec.get("link_type") != "merge" and rec.get("owner") \
                and owner_similarity(rec["owner"], r.owner) < cfg["owner_similarity_min"] \
                and not any(f[0] == "owner" for f in found):
            found.append(("owner", f"revenue owner '{rec['owner']}' vs cadastral '{r.owner}'", lk.iloc[0].b_id))
        topo = topo_flags.get(r.a_id, "clean")
        rec.update(confidence(spatial if lk is not None else 0.0, sources, topo, len(found), cfg))
        rec["sources"] = ",".join(sources)
        rec["conflicts"] = "; ".join(f"{k}: {m}" for k, m, _ in found)
        rec["n_conflicts"] = len(found)
        rows.append(rec)
        conflicts += [{"parcel_id": r.a_id, "type": k, "detail": m} for k, m, _ in found]
    out = gpd.GeoDataFrame(rows, crs=A.crs)
    return out, conflicts
