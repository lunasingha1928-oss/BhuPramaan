"""Load real building footprints, or generate clearly-labelled synthetic ones for development."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon, box

from .names import random_name


def load_footprints(path: str | Path, seed: int = 7, max_parcels: int | None = None) -> gpd.GeoDataFrame:
    """Read GeoJSON/Shapefile footprints (OSM / Google Open Buildings), reproject to metric UTM.

    Keeps valid polygons of a sensible size. Adds a synthetic owner name per parcel because
    open footprint data has no owner field (the owner attribute is benchmark-only).
    """
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf = gdf.explode(index_parts=False, ignore_index=True)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs(gdf.estimate_utm_crs())
    gdf = gdf[(gdf.area >= 15) & (gdf.area <= 2000)].reset_index(drop=True)
    if max_parcels and len(gdf) > max_parcels:
        gdf = gdf.sample(max_parcels, random_state=seed).reset_index(drop=True)
    rng = np.random.default_rng(seed)
    gdf = gdf[["geometry"]].copy()
    gdf["owner"] = [random_name(rng) for _ in range(len(gdf))]
    gdf.attrs["source"] = f"real:{Path(path).name}"
    return gdf


def synthetic_footprints(n: int = 1500, seed: int = 7, crs: str = "EPSG:32644") -> gpd.GeoDataFrame:
    """Plot-grid style footprints: rotated street blocks, mixed rectangles and L-shapes.

    DEVELOPMENT ONLY. Headline numbers must come from real footprints (scripts/fetch_osm.py).
    """
    rng = np.random.default_rng(seed)
    side = int(np.ceil(np.sqrt(n)))
    pitch, street, block = 30.0, 14.0, 10
    origin_x, origin_y = 350000.0, 1445000.0
    block_angle: dict[tuple[int, int], float] = {}
    geoms: list[Polygon] = []
    for i in range(side):
        for j in range(side):
            if len(geoms) >= n:
                break
            bi, bj = i // block, j // block
            ang = block_angle.setdefault((bi, bj), float(rng.uniform(-25, 25)))
            x = i * pitch + bi * street
            y = j * pitch + bj * street
            w, d = rng.uniform(10, 22), rng.uniform(10, 22)
            px, py = x + rng.uniform(1, pitch - w - 1), y + rng.uniform(1, pitch - d - 1)
            g: Polygon = box(px, py, px + w, py + d)
            if rng.random() < 0.25:  # L-shape: remove a corner
                cut = box(px + w * 0.55, py + d * 0.55, px + w, py + d)
                g = g.difference(cut)
            centre = ((bi * block * pitch) + (bi * street) + block * pitch / 2,
                      (bj * block * pitch) + (bj * street) + block * pitch / 2)
            g = affinity.rotate(g, ang, origin=centre)
            geoms.append(affinity.translate(g, origin_x, origin_y))
    gdf = gpd.GeoDataFrame({"geometry": geoms[:n]}, crs=crs)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    gdf["owner"] = [random_name(rng) for _ in range(len(gdf))]
    gdf.attrs["source"] = "SYNTHETIC (development only)"
    return gdf
