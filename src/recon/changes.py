"""Change detection between two dates of the same area.

A later epoch is matched to the earlier one with the same calibrated matcher used for
reconciliation. Unmatched earlier parcels are demolished, unmatched later parcels are new, and
matched parcels whose footprint grew or shrank markedly are flagged as altered (extensions).
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import affinity
from shapely.geometry import box

CHANGE_TYPES = ["new", "demolished", "altered", "unchanged"]


def make_later_epoch(earlier: gpd.GeoDataFrame, seed: int, demolish=0.04, new=0.05, alter=0.06):
    """Synthetic later survey with known changes. Returns (later layer, truth table).

    Made deliberately not-easy: some extensions are small (+25%), every building carries resurvey
    jitter, one in ten is offset 1.5-3 m by a different georeference, and new buildings may sit
    within 1.5 m of existing ones."""
    rng = np.random.default_rng(seed + 77)
    n = len(earlier)
    order = rng.permutation(n)
    n_d, n_a = int(demolish * n), int(alter * n)
    demolished = set(order[:n_d].tolist())
    altered = set(order[n_d:n_d + n_a].tolist())
    rows, truth = [], []
    for i in range(n):
        g = earlier.geometry.values[i]
        eid = earlier["a_id"].values[i]
        if i in demolished:
            truth.append({"earlier_id": eid, "later_id": None, "change": "demolished"})
            continue
        if i in altered:
            f = rng.uniform(1.25, 1.9)                         # extension: footprint grows 25-90%
            c = list(g.exterior.coords)[0] if hasattr(g, "exterior") else g.centroid.coords[0]
            g2 = affinity.scale(g, np.sqrt(f), np.sqrt(f), origin=c)
            kind = "altered"
        else:
            g2 = g
            kind = "unchanged"
        g2 = affinity.translate(g2, *rng.normal(0, 0.5, 2))     # resurvey jitter
        if rng.random() < 0.1:                                   # different georeference: 1.5-3 m offset
            ang, mag = rng.uniform(0, 2 * np.pi), rng.uniform(1.5, 3.0)
            g2 = affinity.translate(g2, mag * np.cos(ang), mag * np.sin(ang))
        lid = f"L{len(rows):05d}"
        rows.append({"l_id": lid, "geometry": g2})
        truth.append({"earlier_id": eid, "later_id": lid, "change": kind})
    # new buildings in open space
    minx, miny, maxx, maxy = earlier.total_bounds
    tree = shapely.STRtree(earlier.geometry.values)
    target, tries = int(new * n), 0
    added = 0
    while added < target and tries < target * 200:
        tries += 1
        w, d = rng.uniform(8, 16), rng.uniform(8, 16)
        x, y = rng.uniform(minx, maxx - w), rng.uniform(miny, maxy - d)
        g = box(x, y, x + w, y + d)
        if len(tree.query(g.buffer(1.5), predicate="intersects")):
            continue
        lid = f"L{len(rows):05d}"
        rows.append({"l_id": lid, "geometry": g})
        truth.append({"earlier_id": None, "later_id": lid, "change": "new"})
        added += 1
    later = gpd.GeoDataFrame(rows, crs=earlier.crs)
    return later, pd.DataFrame(truth)


def classify(pairs: pd.DataFrame, earlier_ids, later_ids, link_min_p: float, altered_area_ratio: float) -> pd.DataFrame:
    """pairs: earlier_id, later_id, p, area_ratio, area_e, area_l. Greedy one-to-one by probability."""
    used_e, used_l, rows = set(), set(), []
    for r in pairs[pairs.p >= link_min_p].sort_values("p", ascending=False).itertuples():
        if r.earlier_id in used_e or r.later_id in used_l:
            continue
        used_e.add(r.earlier_id); used_l.add(r.later_id)
        kind = "altered" if r.area_ratio < altered_area_ratio else "unchanged"
        rows.append({"earlier_id": r.earlier_id, "later_id": r.later_id, "change": kind, "p": float(r.p),
                     "area_change_pct": round(100 * (r.area_l - r.area_e) / max(r.area_e, 1e-9), 1)})
    rows += [{"earlier_id": e, "later_id": None, "change": "demolished", "p": None, "area_change_pct": None}
             for e in earlier_ids if e not in used_e]
    rows += [{"earlier_id": None, "later_id": l, "change": "new", "p": None, "area_change_pct": None}
             for l in later_ids if l not in used_l]
    return pd.DataFrame(rows)


def score(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    def keyset(df, kind):
        d = df[df.change == kind]
        return set(zip(d.earlier_id.fillna(""), d.later_id.fillna("")))
    out = {}
    for kind in CHANGE_TYPES:
        p, t = keyset(pred, kind), keyset(truth, kind)
        tp = len(p & t)
        out[kind] = {"true": len(t), "detected": len(p), "correct": tp,
                     "precision": tp / len(p) if p else 1.0, "recall": tp / len(t) if t else 1.0}
    return out
