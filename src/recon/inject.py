"""Build a two-layer reconciliation benchmark from ground-truth footprints.

Layer A ("cadastral") is the truth geometry. Layer B ("revenue") is a corrupted copy with known,
labelled error types. The true A<->B links are recorded, so every metric is exact.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import split as shp_split

from .names import random_name, variant

ERROR_TYPES = ["clean", "offset", "scale", "rotate", "split", "merge", "missing"]


@dataclass
class Benchmark:
    A: gpd.GeoDataFrame        # cadastral layer: a_id, owner, error_type, geometry
    B: gpd.GeoDataFrame        # revenue layer:   b_id, owner, error_type, geometry
    truth: pd.DataFrame        # a_id, b_id, error_type  (true links)
    source: str = ""


def _random_shift(rng: np.random.Generator, lo: float, hi: float) -> tuple[float, float]:
    ang, mag = rng.uniform(0, 2 * np.pi), rng.uniform(lo, hi)
    return float(mag * np.cos(ang)), float(mag * np.sin(ang))


def _split_polygon(g: Polygon) -> list[Polygon] | None:
    """Cut a parcel into two along its long axis. Returns None if the cut doesn't work."""
    mrr = g.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)[:4]
    e1, e2 = np.subtract(c[1], c[0]), np.subtract(c[2], c[1])
    long_axis = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    d = long_axis / np.hypot(*long_axis)
    n = np.array([-d[1], d[0]])
    ctr = np.array(g.centroid.coords[0])
    line = LineString([ctr - n * 500, ctr + n * 500])
    pieces = [p for p in shp_split(g, line).geoms if p.geom_type == "Polygon" and p.area > 0.15 * g.area]
    return pieces[:2] if len(pieces) >= 2 else None


DEFAULT_RANGES = {"offset": (3.0, 12.0), "rotate": (5.0, 20.0),
                  "scale_low": (0.65, 0.85), "scale_high": (1.15, 1.40)}


def build_benchmark(truth_gdf: gpd.GeoDataFrame, seed: int = 7, error_mix: dict | None = None,
                    spurious_fraction: float = 0.05, name_variant_rate: float = 0.35,
                    ranges: dict | None = None) -> Benchmark:
    rng = np.random.default_rng(seed + 1)
    rg = {**DEFAULT_RANGES, **(ranges or {})}
    mix = error_mix or {"clean": .38, "offset": .16, "scale": .10, "rotate": .06,
                        "split": .08, "merge": .06, "missing": .08}
    kinds = list(mix)
    probs = np.array([mix[k] for k in kinds], dtype=float)
    probs /= probs.sum()

    n = len(truth_gdf)
    geoms = truth_gdf.geometry.values
    owners = truth_gdf["owner"].tolist()
    crs = truth_gdf.crs
    a_ids = [f"A{i:05d}" for i in range(n)]
    tree = shapely.STRtree(geoms)

    a_type = ["clean"] * n
    used = np.zeros(n, dtype=bool)
    b_rows: list[dict] = []
    links: list[tuple[str, str, str]] = []

    def new_b(geom, owner, etype):
        bid = f"B{len(b_rows):05d}"
        if rng.random() < name_variant_rate:
            owner = variant(owner, rng)
        b_rows.append({"b_id": bid, "owner": owner, "error_type": etype, "geometry": geom})
        return bid

    for i in rng.permutation(n):
        if used[i]:
            continue
        used[i] = True
        g, owner = geoms[i], owners[i]
        kind = str(rng.choice(kinds, p=probs))

        if kind == "merge":
            near = [j for j in tree.query_nearest(g, exclusive=True, max_distance=40.0, all_matches=False)
                    if not used[j]]
            if not near:
                kind = "clean"
            else:
                j = int(near[0])
                used[j] = True
                merged = shapely.union(g, geoms[j]).convex_hull
                bid = new_b(merged, owner, "merge")
                for k in (i, j):
                    a_type[k] = "merge"
                    links.append((a_ids[k], bid, "merge"))
                continue

        if kind == "split":
            pieces = _split_polygon(g) if g.geom_type == "Polygon" else None
            if pieces is None:
                kind = "clean"
            else:
                a_type[i] = "split"
                for p in pieces:
                    bid = new_b(p, owner, "split")
                    links.append((a_ids[i], bid, "split"))
                continue

        if kind == "missing":
            a_type[i] = "missing"
            continue

        if kind == "offset":
            bg = affinity.translate(g, *_random_shift(rng, *rg["offset"]))
        elif kind == "scale":
            ratio = float(rng.choice([rng.uniform(*rg["scale_low"]), rng.uniform(*rg["scale_high"])]))
            f = np.sqrt(ratio)
            bg = affinity.scale(g, f, f, origin="centroid")
            bg = affinity.translate(bg, *_random_shift(rng, 0.0, 1.5))
        elif kind == "rotate":
            bg = affinity.rotate(g, float(rng.uniform(*rg["rotate"]) * rng.choice([-1, 1])), origin="centroid")
            bg = affinity.translate(bg, *_random_shift(rng, 1.0, 3.0))
        else:  # clean: only survey jitter
            kind = "clean"
            bg = affinity.translate(g, *_random_shift(rng, 0.0, 1.0))
        a_type[i] = kind
        bid = new_b(bg, owner, kind)
        links.append((a_ids[i], bid, kind))

    # Spurious revenue-layer parcels with no cadastral counterpart (near real ones, to be confusing)
    n_sp = int(round(spurious_fraction * n))
    for _ in range(n_sp):
        base = geoms[int(rng.integers(n))].centroid
        dx, dy = _random_shift(rng, 25.0, 60.0)
        w, d = rng.uniform(8, 18), rng.uniform(8, 18)
        cx, cy = base.x + dx, base.y + dy
        b_rows.append({"b_id": f"B{len(b_rows):05d}", "owner": random_name(rng), "error_type": "spurious",
                       "geometry": box(cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2)})

    A = gpd.GeoDataFrame({"a_id": a_ids, "owner": owners, "error_type": a_type, "geometry": list(geoms)}, crs=crs)
    B = gpd.GeoDataFrame(b_rows, crs=crs)
    B["geometry"] = shapely.make_valid(B.geometry.values)
    truth = pd.DataFrame(links, columns=["a_id", "b_id", "error_type"])
    return Benchmark(A=A, B=B, truth=truth, source=str(truth_gdf.attrs.get("source", "")))
