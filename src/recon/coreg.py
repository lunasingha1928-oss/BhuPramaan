"""Co-registration: remove the systematic, spatially varying shift between two footprint layers.

Independent building datasets traced from different imagery are offset from each other by a few metres,
and the offset drifts across a ward. Matching without correcting it makes every building look like a
disagreement. This module estimates a local shift field from confident one-to-one anchors and moves
layer B onto layer A before matching. The shift is reported, never hidden.

Steps:
  1. mutual nearest centroids within `max_d` m  -> rough anchors; global median shift
  2. apply global shift, keep anchors whose footprints overlap well (IoU >= iou_min)
  3. per building in B: median shift of the k nearest anchors (within `radius` m), else the global shift
"""
from __future__ import annotations

import numpy as np
import shapely
from scipy.spatial import cKDTree


def _mutual_nn(ca, cb, max_d):
    ib = cKDTree(cb).query(ca)[1]
    ia = cKDTree(ca).query(cb)[1]
    d = np.linalg.norm(cb[ib] - ca, axis=1)
    ok = (ia[ib] == np.arange(len(ca))) & (d < max_d)
    return np.flatnonzero(ok), ib[ok]


def estimate(A, B, max_d: float = 15.0, iou_min: float = 0.4, k: int = 25, radius: float = 250.0, iters: int = 2):
    """Return (shift per B row as an (n,2) array, report dict). A and B are GeoDataFrames in a metric CRS."""
    ca = np.c_[A.geometry.centroid.x, A.geometry.centroid.y]
    cb = np.c_[B.geometry.centroid.x, B.geometry.centroid.y]
    ia, ib = _mutual_nn(ca, cb, max_d)
    if len(ia) < 10:
        return np.zeros((len(B), 2)), {"anchors": int(len(ia)), "applied": False}
    glob = np.median(cb[ib] - ca[ia], axis=0)
    shift = np.tile(glob, (len(B), 1))
    ga, gb = A.geometry.values, B.geometry.values
    for _ in range(iters):
        moved = _translate(gb, -shift)
        cm = shapely.centroid(moved)
        ia, ib = _mutual_nn(ca, np.c_[shapely.get_x(cm), shapely.get_y(cm)], max_d)
        inter = shapely.area(shapely.intersection(ga[ia], moved[ib]))
        iou = inter / (shapely.area(ga[ia]) + shapely.area(moved[ib]) - inter)
        good = iou >= iou_min
        ia, ib = ia[good], ib[good]
        if len(ia) < 10:
            break
        vec = cb[ib] - ca[ia]                       # raw shift of each good anchor (B relative to A)
        tree = cKDTree(ca[ia])
        d, nb = tree.query(cb - shift, k=min(k, len(ia)), distance_upper_bound=radius)
        d, nb = np.atleast_2d(d), np.atleast_2d(nb)
        new = np.empty_like(shift)
        glob = np.median(vec, axis=0)
        for r in range(len(B)):
            idx = nb[r][np.isfinite(d[r])]
            new[r] = np.median(vec[idx], axis=0) if len(idx) >= 5 else glob
        shift = new
    resid_before = np.linalg.norm(cb[ib] - ca[ia], axis=1)
    resid_after = np.linalg.norm(cb[ib] - shift[ib] - ca[ia], axis=1)
    mag = np.linalg.norm(shift, axis=1)
    rep = {"applied": True, "anchors": int(len(ia)), "global_shift_m": [round(float(glob[0]), 2), round(float(glob[1]), 2)],
           "shift_magnitude_m": {"min": round(float(mag.min()), 2), "median": round(float(np.median(mag)), 2),
                                 "max": round(float(mag.max()), 2)},
           "anchor_offset_median_m": {"before": round(float(np.median(resid_before)), 2),
                                      "after": round(float(np.median(resid_after)), 2)}}
    return shift, rep


def _translate(geoms, d):
    """Translate each geometry by its own (dx, dy)."""
    out = np.empty(len(geoms), dtype=object)
    for i, (g, (dx, dy)) in enumerate(zip(geoms, d)):
        out[i] = shapely.transform(g, lambda xy, dx=dx, dy=dy: xy + np.array([dx, dy]))
    return out


def apply(B, shift):
    B = B.copy()
    B["geometry"] = _translate(B.geometry.values, -shift)
    return B
