import json
import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box

from recon import changes as chg
from recon import topology
from recon.attributes import infer_area_unit, match_schema, owner_similarity

ROOT = Path(__file__).resolve().parents[1]


def test_topology_finds_and_repairs_overlaps_and_bowties():
    g = gpd.GeoDataFrame({"id": [1, 2, 3]}, geometry=[
        box(0, 0, 10, 10), box(8, 0, 18, 10),                              # 2 m overlap strip
        Polygon([(30, 0), (40, 10), (40, 0), (30, 10)])], crs=32644)      # bow-tie
    rep = topology.check(g)
    assert rep["overlaps"] == 1 and rep["invalid"] == 1
    fixed, actions, before, after = topology.repair(g, priority=np.array([1.0, 0.5, 0.5]))
    assert after["overlaps"] == 0 and after["invalid"] == 0
    assert fixed.geometry.iloc[0].area == pytest.approx(100)              # the higher-priority parcel keeps its area
    assert fixed.geometry.iloc[1].area == pytest.approx(80)
    assert {a["action"] for a in actions} >= {"trimmed overlap", "fixed invalid geometry"}


def test_schema_matching_and_units():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"Pattadar_Name": ["Krishnan Iyer", "Abdul Khan", "Priya Rao", "Arun Das"] * 25,
                       "Extent": rng.uniform(2, 20, 100).round(2), "Classfn": ["RES", "COM"] * 50,
                       "Patta_No": [f"PT/{i}" for i in range(100)], "SF_No": [f"{i}/2A" for i in range(100)]})
    got = {m["column"]: m["field"] for m in match_schema(df)}
    assert got == {"Pattadar_Name": "owner_name", "Extent": "area", "Classfn": "land_use",
                   "Patta_No": "parcel_ref", "SF_No": "survey_no"}
    surveyed = rng.uniform(100, 600, 200)
    assert infer_area_unit(surveyed / 40.468564, surveyed)["unit"] == "cent"
    assert infer_area_unit(surveyed / 0.09290304, surveyed)["unit"] == "square foot"


@pytest.mark.parametrize("a,b,same", [("Krishnan Iyer", "K. Iyer", True), ("Krishnan Iyer", "Iyer, Krishnan", True),
                                      ("Janaki Reddy", "JanakiR eddy", True), ("Krishnan Iyer", "Abdul Khan", False),
                                      ("Abdul Sheikh", "Meenakshi Sheikh", False)])
def test_owner_similarity(a, b, same):
    assert (owner_similarity(a, b) >= 0.8) == same


def test_change_classification():
    pairs = pd.DataFrame({"earlier_id": ["A1", "A2", "A3"], "later_id": ["L1", "L2", "L9"], "p": [0.99, 0.97, 0.2],
                          "area_ratio": [0.98, 0.6, 0.9], "area_e": [100, 100, 100], "area_l": [101, 166, 100]})
    pred = chg.classify(pairs, ["A1", "A2", "A3"], ["L1", "L2", "L3"], 0.5, 0.8)
    kinds = dict(zip(pred.earlier_id.fillna(pred.later_id), pred.change))
    assert kinds == {"A1": "unchanged", "A2": "altered", "A3": "demolished", "L3": "new"}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo_mod")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo.py"), "--synthetic", "600", "--out", str(d)],
                   check=True, capture_output=True)
    return d


def test_demo_build_produces_measured_modules(demo):
    q = json.loads((demo / "quality.json").read_text())
    assert all(m["correct"] for m in q["schema"]["revenue"] + q["schema"]["tax"] if m["field"])
    assert q["units"]["revenue"]["unit"] == "cent" and q["units"]["tax"]["unit"] == "square foot"
    assert q["topology"]["revenue"]["after"]["invalid"] == 0
    assert q["topology"]["revenue"]["after"]["overlaps"] < q["topology"]["revenue"]["before"]["overlaps"]
    assert {c["delivered_crs"] for c in q["crs"]} == {"EPSG:7755", "EPSG:4326", "EPSG:32644"}
    for k, v in q["conflicts"]["metrics"].items():
        assert v["recall"] > 0.7, k
    ch = json.loads((demo / "changes.json").read_text())["summary"]["scores"]
    for k in ("new", "demolished", "altered"):
        assert ch[k]["recall"] > 0.8 and ch[k]["precision"] > 0.8, k
    h = json.loads((demo / "harmonised.json").read_text())
    assert len(h["features"]) == 600 and all(0 <= f["properties"]["confidence"] <= 100 for f in h["features"])


def _client(demo, user, pw):
    os.environ["RECON_DEMO_DIR"] = str(demo)
    from recon.api import app
    c = TestClient(app)
    assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
    return c


def test_module_endpoints_respect_roles(demo):
    off = _client(demo, "officer1", "officer@123")
    aud = _client(demo, "auditor", "audit@123")
    adm = _client(demo, "admin", "admin@123")
    assert off.get("/api/quality").status_code == 403
    assert off.get("/api/changes").status_code == 200
    assert off.get("/api/export/harmonised.csv").status_code == 403
    assert adm.get("/api/changes").status_code == 403
    r = aud.get("/api/export/harmonised.csv")
    assert r.status_code == 200 and r.text.startswith("parcel_id,confidence,band")
    assert aud.get("/api/export/changes.geojson").json()["type"] == "FeatureCollection"
    assert len(off.get("/api/harmonised").json()["features"]) == 600


def test_coregistration_removes_a_known_shift():
    import numpy as np
    from recon import coreg
    from recon.footprints import synthetic_footprints
    A = synthetic_footprints(400, seed=3)[["geometry"]].copy()
    A["id"] = [f"A{i}" for i in range(len(A))]
    B = A.copy()
    B["geometry"] = B.geometry.translate(3.0, -2.0)        # a whole layer traced 3.6 m off
    B["id"] = [f"B{i}" for i in range(len(B))]
    shift, rep = coreg.estimate(A, B)
    assert rep["applied"] and rep["anchors"] > 100
    assert np.allclose(np.median(shift, axis=0), [3.0, -2.0], atol=0.2)
    moved = coreg.apply(B, shift)
    assert np.median(moved.geometry.centroid.distance(A.geometry.centroid)) < 0.3


def test_temporal_change_flags_a_new_building_and_ignores_drift(tmp_path):
    import numpy as np
    import pytest
    rasterio = pytest.importorskip("rasterio")
    import geopandas as gpd
    from rasterio.transform import from_origin
    from shapely.geometry import box
    from recon import temporal
    tr = from_origin(0, 400, 4, 4)
    def write(path, pres, h):
        with rasterio.open(path, "w", driver="GTiff", width=100, height=100, count=2, dtype="float32", crs="EPSG:32644", transform=tr) as r:
            r.write(pres.astype("float32"), 1); r.write(h.astype("float32"), 2)
    p0 = np.full((100, 100), 0.05); p0[10:20, 10:20] = 0.8                 # an old building
    p1 = p0 + 0.05                                                         # whole-image drift, not change
    p1[50:60, 50:60] = 0.85                                                # a new building
    h = np.where(p0 > 0.5, 6.0, 0.0)
    write(tmp_path / "a.tif", p0, h); write(tmp_path / "b.tif", p1, h)
    new_box = box(200, 160, 240, 200)                                      # pixels 50-60 in map units
    ms = gpd.GeoDataFrame(geometry=[new_box], crs="EPSG:32644")
    osm = gpd.GeoDataFrame({"id": ["O1"]}, geometry=[box(40, 320, 80, 360)], crs="EPSG:32644")
    res = temporal.analyse(str(tmp_path / "a.tif"), str(tmp_path / "b.tif"), {"Microsoft": ms, "OSM": osm}, osm)
    s = res["summary"]
    assert s["new"] == 1 and s["new_confirmed"] == 1 and s["new_missing_in_osm"] == 1
    assert s["demolished"] == 0 and s["taller"] == 0
