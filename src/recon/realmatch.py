"""Matching two real footprint/parcel layers: shared by scripts/build_real.py and the upload page.

    load_layer(path)             read GeoJSON / GeoPackage / zipped Shapefile, clean, project to metres
    save_matcher / load_matcher  persist the trained XGBoost + isotonic calibrator + thresholds
    match_layers(A, B, matcher)  co-register B onto A, score candidate pairs, describe the result
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import coreg
from .features import candidate_pairs, pair_features

PART_SHARE, PART_RATIO = 0.6, 1.8      # share of the small shape inside the big one; size ratio
MIN_AREA, MAX_AREA = 8, 20000          # m²: drop specks and whole blocks


class LayerError(ValueError):
    """A layer that can't be used, with a message fit to show the user."""


# ------------------------------------------------------------------ reading
def _read_any(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            if any(n.startswith("/") or ".." in Path(n).parts for n in names):
                raise LayerError("The zip contains unsafe paths.")
            if sum(z.getinfo(n).file_size for n in names) > 200 * 1024 * 1024:
                raise LayerError("The zip expands to more than 200 MB.")
            shp = [n for n in names if n.lower().endswith(".shp")]
            if len(shp) != 1:
                raise LayerError("A zipped Shapefile must contain exactly one .shp (with its .shx, .dbf and .prj).")
            out = path.parent / (path.stem + "_unzipped")
            z.extractall(out)
            return gpd.read_file(out / shp[0])
    return gpd.read_file(path)


def load_layer(path, label: str, crs=None, prefix: str | None = None, max_features: int | None = None) -> gpd.GeoDataFrame:
    """Polygons only, made valid, projected to metres (UTM of the data unless `crs` is given), sensible sizes."""
    path = Path(path)
    try:
        g = _read_any(path)
    except LayerError:
        raise
    except Exception as e:                                   # driver errors: say what we accept
        raise LayerError(f"{label}: could not read the file ({type(e).__name__}). Use GeoJSON, GeoPackage or a zipped Shapefile.") from e
    if g.crs is None:
        b = g.total_bounds if len(g) else [0, 0, 0, 0]
        if -180 <= b[0] <= 180 and -90 <= b[1] <= 90:
            g = g.set_crs(4326)                              # GeoJSON default
        else:
            raise LayerError(f"{label}: the file has no coordinate system and its coordinates are not longitude/latitude.")
    g = g[g.geometry.notna()].copy()
    g["geometry"] = g.geometry.make_valid()
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]
    g = g.explode(index_parts=False, ignore_index=True)
    g = g[g.geom_type == "Polygon"]
    if not len(g):
        raise LayerError(f"{label}: no polygons found. Upload building or parcel outlines, not points or lines.")
    if max_features and len(g) > max_features:
        raise LayerError(f"{label}: {len(g):,} polygons; the upload limit is {max_features:,}. Clip to a smaller area.")
    g = g.to_crs(crs or g.estimate_utm_crs())
    g = g[(g.area >= MIN_AREA) & (g.area <= MAX_AREA)].reset_index(drop=True)
    if not len(g):
        raise LayerError(f"{label}: every polygon is smaller than {MIN_AREA} m² or larger than {MAX_AREA:,} m².")
    out = g[["geometry"]].copy()
    out["id"] = [f"{prefix or label[0]}{i:05d}" for i in range(len(out))]
    out["owner"] = ""
    return out


# ------------------------------------------------------------------ model persistence
def save_matcher(path, model, cal, cols, t_lo, t_hi, radius_m) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    model.save_model(path / "xgb.json")
    (path / "matcher.json").write_text(json.dumps({
        "cols": list(cols), "t_lo": float(t_lo), "t_hi": float(t_hi), "radius_m": float(radius_m),
        "cal_x": [float(x) for x in cal.X_thresholds_], "cal_y": [float(y) for y in cal.y_thresholds_]}))


class Matcher:
    def __init__(self, model, meta: dict):
        self.model, self.cols = model, meta["cols"]
        self.t_lo, self.t_hi, self.radius = meta["t_lo"], meta["t_hi"], meta["radius_m"]
        self._x, self._y = np.array(meta["cal_x"]), np.array(meta["cal_y"])

    def prob(self, feats: pd.DataFrame) -> np.ndarray:
        raw = self.model.predict_proba(feats[self.cols])[:, 1]
        return np.interp(raw, self._x, self._y)              # isotonic calibrator, clipped at the ends


def load_matcher(path) -> Matcher:
    from xgboost import XGBClassifier
    path = Path(path)
    if not (path / "matcher.json").exists():
        raise FileNotFoundError(str(path / "matcher.json"))
    m = XGBClassifier()
    m.load_model(path / "xgb.json")
    return Matcher(m, json.loads((path / "matcher.json").read_text()))


# ------------------------------------------------------------------ relations and description
def part_of(small, big, skip):
    """Shapes in `small` (not already linked) lying mostly inside one much larger shape of `big`:
    one source traced a terrace or block as one polygon, the other as several."""
    small = small[~small.id.isin(skip)]
    if not len(small) or not len(big):
        return {}
    tree = shapely.STRtree(big.geometry.values)
    si, bi = tree.query(small.geometry.values, predicate="intersects")
    sg, bg = small.geometry.values[si], big.geometry.values[bi]
    inter = shapely.area(shapely.intersection(sg, bg))
    ok = (inter / shapely.area(sg) >= PART_SHARE) & (shapely.area(bg) >= PART_RATIO * shapely.area(sg))
    return dict(zip(small.id.values[si[ok]], big.id.values[bi[ok]]))


def describe(f, A, B, la, lb):
    acc = f[f.bucket == "accept"]
    one = acc[acc.groupby("a_id").b_id.transform("nunique").eq(1) & acc.groupby("b_id").a_id.transform("nunique").eq(1)]
    a_hit = set(f.a_id[f.bucket != "reject"]); b_hit = set(f.b_id[f.bucket != "reject"])
    a_in_b = part_of(A, B, a_hit)
    b_in_a = part_of(B, A, b_hit)
    a_any = a_hit | set(a_in_b) | set(b_in_a.values())
    b_any = b_hit | set(b_in_a) | set(a_in_b.values())
    groups_b = pd.Series(list(a_in_b.values())).value_counts() if a_in_b else pd.Series(dtype=int)
    groups_a = pd.Series(list(b_in_a.values())).value_counts() if b_in_a else pd.Series(dtype=int)
    return {
        "pair": f"{la} ↔ {lb}", "n_a": len(A), "n_b": len(B), "candidates": len(f),
        "auto_links": int(len(acc)), "review_links": int((f.bucket == "review").sum()),
        "a_with_counterpart": len(a_any) / max(len(A), 1), "b_with_counterpart": len(b_any) / max(len(B), 1),
        "a_only": len(A) - len(a_any), "b_only": len(B) - len(b_any),
        "one_to_one": int(len(one)),
        "a_inside_larger_b": len(a_in_b), "b_polygons_covering_several_a": int((groups_b >= 2).sum()),
        "b_inside_larger_a": len(b_in_a), "a_polygons_covering_several_b": int((groups_a >= 2).sum()),
        "b_covering_several_a": int((groups_b >= 2).sum()),
        "median_offset_m": float(one.centroid_dist.median()) if len(one) else None,
        "p90_offset_m": float(one.centroid_dist.quantile(0.9)) if len(one) else None,
        "median_iou": float(one.iou.median()) if len(one) else None,
        "median_area_ratio": float(one.area_ratio.median()) if len(one) else None,
    }, {"a_in_b": a_in_b, "b_in_a": b_in_a}


# ------------------------------------------------------------------ the whole thing
def match_layers(A, B, matcher: Matcher, la="Layer A", lb="Layer B", do_coreg=True, iou_accept=0.5):
    """A, B: outputs of load_layer in the same metric CRS. Returns (pairs, B moved onto A, report, relations)."""
    A = A.rename(columns={"id": "a_id"}); B = B.rename(columns={"id": "b_id"})
    rep = {"applied": False}
    if do_coreg:
        shift, rep = coreg.estimate(A, B)
        if rep.get("applied"):
            B = coreg.apply(B, shift)
    f = pair_features(A, B, candidate_pairs(A, B, matcher.radius))
    if len(f):
        f["p"] = matcher.prob(f)
        # validated on 300 hand-checked real pairs: confident model OR good overlap after co-registration
        auto = (f.p >= matcher.t_hi) | (f.iou >= iou_accept)
        f["bucket"] = np.where(auto, "accept", np.where(f.p < matcher.t_lo, "reject", "review"))
        f["why"] = np.where(f.p >= matcher.t_hi, "model", np.where(f.iou >= iou_accept, "overlap", ""))
    else:
        f = f.assign(p=[], bucket=[], why=[])
    A2, B2 = A.rename(columns={"a_id": "id"}), B.rename(columns={"b_id": "id"})
    desc, rel = describe(f, A2, B2, la, lb)
    return f, B2, rep, desc, rel
