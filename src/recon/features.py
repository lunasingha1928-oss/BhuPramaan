"""Candidate generation (R-tree) and pairwise features."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from rapidfuzz import fuzz

from .names import normalize

FEATURES = [
    "iou", "inter_over_a", "inter_over_b", "centroid_dist", "area_ratio", "hausdorff_norm",
    "name_sort", "name_set", "rank_a", "rank_b", "n_cand_a", "n_cand_b", "gap_a", "gap_b",
]


def candidate_pairs(A: gpd.GeoDataFrame, B: gpd.GeoDataFrame, radius: float) -> pd.DataFrame:
    tree = shapely.STRtree(B.geometry.values)
    ai, bi = tree.query(shapely.buffer(A.geometry.values, radius), predicate="intersects")
    return pd.DataFrame({"a_idx": ai, "b_idx": bi})


def pair_features(A: gpd.GeoDataFrame, B: gpd.GeoDataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    ga, gb = A.geometry.values[pairs.a_idx.values], B.geometry.values[pairs.b_idx.values]
    inter = shapely.area(shapely.intersection(ga, gb))
    aa, ab = shapely.area(ga), shapely.area(gb)
    f = pd.DataFrame({"a_idx": pairs.a_idx.values, "b_idx": pairs.b_idx.values})
    f["a_id"], f["b_id"] = A["a_id"].values[f.a_idx], B["b_id"].values[f.b_idx]
    f["iou"] = inter / np.maximum(aa + ab - inter, 1e-9)
    f["inter_over_a"], f["inter_over_b"] = inter / np.maximum(aa, 1e-9), inter / np.maximum(ab, 1e-9)
    f["centroid_dist"] = shapely.distance(shapely.centroid(ga), shapely.centroid(gb))
    f["area_ratio"] = np.minimum(aa, ab) / np.maximum(np.maximum(aa, ab), 1e-9)
    f["hausdorff_norm"] = shapely.hausdorff_distance(ga, gb) / np.sqrt(np.maximum(aa, 1e-9))

    na = [normalize(x) for x in A["owner"].values[f.a_idx]]
    nb = [normalize(x) for x in B["owner"].values[f.b_idx]]
    f["name_sort"] = [fuzz.token_sort_ratio(x, y) / 100 for x, y in zip(na, nb)]
    f["name_set"] = [fuzz.token_set_ratio(x, y) / 100 for x, y in zip(na, nb)]

    g_a, g_b = f.groupby("a_idx")["centroid_dist"], f.groupby("b_idx")["centroid_dist"]
    f["rank_a"], f["rank_b"] = g_a.rank(method="min"), g_b.rank(method="min")
    f["n_cand_a"], f["n_cand_b"] = g_a.transform("size"), g_b.transform("size")
    f["gap_a"] = f["centroid_dist"] - g_a.transform("min")
    f["gap_b"] = f["centroid_dist"] - g_b.transform("min")
    return f
