"""Topology checks and repair for parcel layers.

Detects invalid (self-intersecting) geometry, overlaps between parcels, slivers and near-miss gaps,
and repairs what can be repaired automatically. When two parcels overlap, the contested area goes to
the parcel with the higher priority (for example the better-supported link); the other is trimmed.
Near-miss gaps are flagged for field checking rather than snapped, because between building
footprints a small gap is usually real.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon

DEFAULTS = {"overlap_min_m2": 0.5, "sliver_max_m2": 2.0, "sliver_thinness": 0.08, "gap_max_m": 0.3}


def _polygonal(g):
    """Keep only the polygon parts of a geometry (make_valid can return collections)."""
    if g is None or g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    if not parts:
        return Polygon()
    u = shapely.union_all(parts)
    return u if isinstance(u, (Polygon, MultiPolygon)) else Polygon()


def _thinness(geoms) -> np.ndarray:
    """Polsby-Popper compactness: 1 for a circle, near 0 for a sliver."""
    a, p = shapely.area(geoms), shapely.length(geoms)
    return np.where(p > 0, 4 * np.pi * a / np.maximum(p * p, 1e-12), 0.0)


def check(gdf: gpd.GeoDataFrame, cfg: dict | None = None) -> dict:
    c = {**DEFAULTS, **(cfg or {})}
    geoms = gdf.geometry.values
    invalid = ~shapely.is_valid(geoms)
    valid = shapely.make_valid(geoms)
    valid = np.array([_polygonal(g) for g in valid], dtype=object)
    tree = shapely.STRtree(valid)
    i, j = tree.query(valid, predicate="intersects")
    m = i < j
    i, j = i[m], j[m]
    inter = shapely.area(shapely.intersection(valid[i], valid[j])) if len(i) else np.array([])
    ov = inter > c["overlap_min_m2"]
    gi, gj = tree.query(valid, predicate="dwithin", distance=c["gap_max_m"])
    gm = gi < gj
    gi, gj = gi[gm], gj[gm]
    d = shapely.distance(valid[gi], valid[gj]) if len(gi) else np.array([])
    gaps = (d > 0) & (d <= c["gap_max_m"])
    area = shapely.area(valid)
    sliver = (area > 0) & ((area < c["sliver_max_m2"]) | (_thinness(valid) < c["sliver_thinness"]))
    return {
        "parcels": int(len(gdf)),
        "invalid": int(invalid.sum()),
        "overlaps": int(ov.sum()),
        "overlap_area_m2": float(inter[ov].sum()) if len(inter) else 0.0,
        "slivers": int(sliver.sum()),
        "near_miss_gaps": int(gaps.sum()),
        "_overlap_pairs": list(zip(i[ov].tolist(), j[ov].tolist(), inter[ov].tolist())),
        "_invalid_idx": np.flatnonzero(invalid).tolist(),
        "_sliver_idx": np.flatnonzero(sliver).tolist(),
    }


def repair(gdf: gpd.GeoDataFrame, priority: np.ndarray | None = None, cfg: dict | None = None):
    """Return (repaired copy, list of actions, report before, report after)."""
    c = {**DEFAULTS, **(cfg or {})}
    before = check(gdf, c)
    out = gdf.copy()
    geoms = np.array([_polygonal(g) for g in shapely.make_valid(out.geometry.values)], dtype=object)
    pr = np.zeros(len(out)) if priority is None else np.asarray(priority, dtype=float)
    actions: list[dict] = [{"action": "fixed invalid geometry", "index": int(k)} for k in before["_invalid_idx"]]

    # overlaps: largest first; the lower-priority parcel gives up the shared area
    for a, b, area in sorted(before["_overlap_pairs"], key=lambda t: -t[2]):
        win, lose = (a, b) if pr[a] >= pr[b] else (b, a)
        trimmed = _polygonal(shapely.difference(geoms[lose], geoms[win]))
        if trimmed is not None and not trimmed.is_empty:
            geoms[lose] = trimmed
            actions.append({"action": "trimmed overlap", "index": int(lose), "kept_by": int(win), "area_m2": round(area, 2)})

    # remove sliver fragments left behind (keep the main body of each parcel)
    for k, g in enumerate(geoms):
        if isinstance(g, MultiPolygon):
            parts = sorted(g.geoms, key=lambda p: -p.area)
            keep = [p for p in parts if p.area >= c["sliver_max_m2"]] or parts[:1]
            if len(keep) < len(parts):
                geoms[k] = keep[0] if len(keep) == 1 else MultiPolygon(keep)
                actions.append({"action": "removed sliver fragments", "index": k, "parts": len(parts) - len(keep)})
    out["geometry"] = list(geoms)
    out = out.set_geometry("geometry")
    after = check(out, c)
    out["topology_repaired"] = False
    touched = {a["index"] for a in actions}
    out.iloc[list(touched), out.columns.get_loc("topology_repaired")] = True
    return out, actions, public(before), public(after)


def public(rep: dict) -> dict:
    return {k: v for k, v in rep.items() if not k.startswith("_")}


def add_digitisation_defects(gdf: gpd.GeoDataFrame, rate: float, seed: int) -> tuple[gpd.GeoDataFrame, int]:
    """Simulate as-received digitisation faults: self-intersecting rings (bow-ties) and spikes."""
    rng = np.random.default_rng(seed + 31)
    out = gdf.copy()
    geoms = list(out.geometry.values)
    n = 0
    for k in rng.choice(len(geoms), size=int(rate * len(geoms)), replace=False):
        g = geoms[k]
        if not isinstance(g, Polygon) or len(g.exterior.coords) < 5:
            continue
        pts = list(g.exterior.coords)[:-1]
        if rng.random() < 0.6:                      # bow-tie: swap two neighbouring vertices
            pts[1], pts[2] = pts[2], pts[1]
        else:                                       # spike: a thin excursion from one vertex
            x, y = pts[0]
            pts.insert(1, (x + rng.uniform(4, 8), y + 0.05))
            pts.insert(2, (x, y + 0.1))
        geoms[k] = Polygon(pts)
        n += 1
    out["geometry"] = geoms
    return out, n
