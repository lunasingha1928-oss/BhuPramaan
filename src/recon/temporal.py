"""Real change detection from Google Open Buildings 2.5D Temporal (2016 vs 2023).

The temporal layer is a model output from Sentinel-2 at 4 m: per pixel, a building-presence score (0-1) and a
building height (m). It is noisy, so every flag here is a candidate for field checking, and each one carries
whether an INDEPENDENT current map (Microsoft, OSM) agrees. Google's own vector footprints come from the same
producer, so they are reported but never counted as confirmation.

  new         presence rose sharply (drift-corrected) in a compact cluster; built after 2016
  demolished  presence fell sharply in a compact cluster; possibly demolished or rebuilt
  taller      an existing OSM building whose median height grew by >= TALLER_M (about two floors)
"""
from __future__ import annotations

import numpy as np
import shapely
from scipy import ndimage

DELTA = 0.40          # drift-corrected change in presence score
PRESENT = 0.55        # presence score that counts as "a building is there"
MIN_PIXELS = 8        # 8 px x 16 m2 = 128 m2: smaller clusters are noise at this resolution
TALLER_M = 6.0        # height gain flagged (2 floors at ~3 m); typical noise is about +-5 m
FLOOR_M = 3.0
CONFIRM_SHARE = 0.40  # share of a change cluster covered by a current map to count as agreement
ABSENT_SHARE = 0.10


def _read(path):
    import rasterio
    with rasterio.open(path) as r:
        return r.read(1).astype("float32"), r.read(2).astype("float32"), r.transform, r.crs


def _clusters(mask, transform):
    from rasterio.features import shapes
    mask = ndimage.binary_opening(mask, np.ones((2, 2)))
    lab, n = ndimage.label(mask)
    if not n:
        return []
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = np.isin(lab, np.flatnonzero(sizes >= MIN_PIXELS) + 1)
    by_id = {}
    for geom, v in shapes(lab.astype("int32"), mask=keep, transform=transform):
        by_id.setdefault(int(v), []).append(shapely.geometry.shape(geom))
    return [shapely.union_all(g) for g in by_id.values()]


def _cover(polys, union):
    if union is None or not len(polys):
        return np.zeros(len(polys))
    return shapely.area(shapely.intersection(np.array(polys, dtype=object), union)) / shapely.area(np.array(polys, dtype=object))


def analyse(tif_early: str, tif_late: str, current: dict, osm, years=(2016, 2023)) -> dict:
    """current: {source name: GeoDataFrame in the rasters' CRS}. osm: GeoDataFrame with an `id` column (same CRS)."""
    p0, h0, tr, crs = _read(tif_early)
    p1, h1, _, _ = _read(tif_late)
    both = (p0 > 0.2) & (p1 > 0.2)        # built in both years: their change is drift, not construction
    drift = float(np.median((p1 - p0)[both])) if both.any() else 0.0
    d = p1 - p0 - drift
    unions = {k: shapely.union_all(g.geometry.values) for k, g in current.items()}
    independent = [k for k in unions if k != "Google"]

    feats = []
    for kind, mask in (("new", (d >= DELTA) & (p1 >= PRESENT)), ("demolished", (d <= -DELTA) & (p0 >= PRESENT))):
        polys = _clusters(mask, tr)
        cover = {k: _cover(polys, u) for k, u in unions.items()}
        for i, g in enumerate(polys):
            props = {"change": kind, "area_m2": round(float(g.area), 0)}
            for k in unions:
                props[f"in_{k.lower()}_today"] = round(float(cover[k][i]), 2)
            if kind == "new":
                props["confirmed"] = any(cover[k][i] >= CONFIRM_SHARE for k in independent if k != "OSM")
                props["missing_in_osm"] = bool("OSM" in cover and cover["OSM"][i] < ABSENT_SHARE)
            else:
                props["confirmed"] = any(cover[k][i] < ABSENT_SHARE for k in independent if k != "OSM")
                props["still_in_osm"] = bool("OSM" in cover and cover["OSM"][i] >= CONFIRM_SHARE)
            feats.append((g, props))

    # height gain on existing OSM buildings
    from rasterio.features import rasterize
    lab = rasterize([(g, i + 1) for i, g in enumerate(osm.geometry.values)], out_shape=p0.shape, transform=tr)
    idx = np.arange(1, len(osm) + 1)
    n = ndimage.sum(np.ones_like(p0), lab, idx)
    m0, m1 = ndimage.mean(p0, lab, idx), ndimage.mean(p1, lab, idx)
    hh0 = ndimage.median(h0, lab, idx); hh1 = ndimage.median(h1, lab, idx)
    dh = np.asarray(hh1) - np.asarray(hh0)
    taller = (n >= 4) & (np.asarray(m0) >= 0.5) & (np.asarray(m1) >= 0.5) & (dh >= TALLER_M)
    for i in np.flatnonzero(taller):
        feats.append((osm.geometry.values[i], {"change": "taller", "osm_id": str(osm.id.values[i]),
                                               "height_before_m": round(float(hh0[i]), 1), "height_after_m": round(float(hh1[i]), 1),
                                               "gain_m": round(float(dh[i]), 1), "floors_added_approx": int(round(dh[i] / FLOOR_M)),
                                               "confirmed": False}))

    noise = float(np.subtract(*np.percentile(dh[(n >= 4) & np.isfinite(dh)], [75, 25])))
    summary = {
        "years": list(years), "pixel_m": float(abs(tr.a)), "presence_drift": round(drift, 3),
        "height_change_iqr_m": round(noise, 2),
        "new": sum(p["change"] == "new" for _, p in feats),
        "new_confirmed": sum(p["change"] == "new" and p["confirmed"] for _, p in feats),
        "new_missing_in_osm": sum(p["change"] == "new" and p.get("missing_in_osm", False) for _, p in feats),
        "new_confirmed_missing_in_osm": sum(p["change"] == "new" and p["confirmed"] and p.get("missing_in_osm", False) for _, p in feats),
        "demolished": sum(p["change"] == "demolished" for _, p in feats),
        "demolished_confirmed": sum(p["change"] == "demolished" and p["confirmed"] for _, p in feats),
        "taller": int(taller.sum()),
        "rules": {"delta": DELTA, "present": PRESENT, "min_area_m2": MIN_PIXELS * abs(tr.a) * abs(tr.e),
                  "taller_m": TALLER_M, "confirm_share": CONFIRM_SHARE, "absent_share": ABSENT_SHARE},
        "independent_sources": [k for k in independent if k != "OSM"],
    }
    return {"summary": summary, "features": feats, "crs": crs}
