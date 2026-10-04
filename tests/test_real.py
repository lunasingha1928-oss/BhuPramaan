import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recon.realeval import evaluate, wilson

ROOT = Path(__file__).resolve().parents[1]


def test_wilson_interval_brackets_the_rate():
    lo, hi = wilson(45, 50)
    assert lo < 0.9 < hi and 0 <= lo and hi <= 1


def test_stratified_weighting():
    sample = {"thresholds": {"accept": 0.9, "reject": 0.3},
              "strata": [{"lo": 0.3, "hi": 0.9, "population": 100, "sampled": 2},
                         {"lo": 0.9, "hi": 1.0, "population": 900, "sampled": 2}],
              "pairs": [{"pair_id": "a", "p": 0.5, "iou": 0.2, "stratum": 0}, {"pair_id": "b", "p": 0.6, "iou": 0.6, "stratum": 0},
                        {"pair_id": "c", "p": 0.95, "iou": 0.7, "stratum": 1}, {"pair_id": "d", "p": 0.99, "iou": 0.8, "stratum": 1}]}
    labels = [{"pair_id": "a", "label": "different"}, {"pair_id": "b", "label": "same"},
              {"pair_id": "c", "label": "same"}, {"pair_id": "d", "label": "different"},
              {"pair_id": "d", "label": "same"}]                         # latest label wins
    ev = evaluate(sample, labels)
    assert ev["labelled"] == 4
    assert ev["model"]["precision"] == pytest.approx(1.0)
    assert ev["model"]["recall"] == pytest.approx(900 / 950)             # weights 450 per top pair, 50 per middle pair


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo_real")
    raw = tmp_path_factory.mktemp("raw")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo.py"), "--synthetic", "400", "--out", str(d)],
                   check=True, capture_output=True)
    # stand-in "real" sources: synthetic footprints and a perturbed copy (the real files come from fetch_real.py)
    sys.path.insert(0, str(ROOT / "src"))
    from recon.footprints import synthetic_footprints
    from recon.inject import build_benchmark
    t = synthetic_footprints(400, seed=2)
    t[["geometry"]].to_crs(4326).to_file(raw / "osm.geojson", driver="GeoJSON")
    build_benchmark(t, seed=2).B[["geometry"]].to_crs(4326).to_file(raw / "ms.geojson", driver="GeoJSON")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_real.py"), "--osm", str(raw / "osm.geojson"),
                    "--microsoft", str(raw / "ms.geojson"), "--google", str(raw / "none.geojson"),
                    "--roads", str(raw / "none.geojson"), "--temporal", "none.tif", "none.tif", "--out", str(d / "real")], check=True, capture_output=True)
    shutil.copytree(raw, d / "raw")            # the upload tests reuse these layers
    return d


def _c(demo, u, pw):
    os.environ["RECON_DEMO_DIR"] = str(demo)
    import recon.api as api
    api.MIN_LABEL_SECONDS = 0.3
    from recon.api import app
    c = TestClient(app)
    assert c.post("/api/login", json={"username": u, "password": pw}).status_code == 200
    return c


def test_real_build_and_blind_labelling(demo):
    s = json.loads((demo / "real" / "real_sample.json").read_text())
    assert len(s["pairs"]) > 50 and s["thresholds"]["accept"] >= 0.9
    off, aud = _c(demo, "officer1", "officer@123"), _c(demo, "auditor", "audit@123")
    n = off.get("/api/real/next").json()
    assert not n["done"] and "p" not in n["pair"] and "iou" not in n["pair"]     # blind
    assert aud.post("/api/real/labels", json={"pair_id": n["pair"]["pair_id"], "label": "same"}).status_code == 403
    assert off.post("/api/real/labels", json={"pair_id": "nope|nope", "label": "same"}).status_code == 404
    assert off.post("/api/real/labels", json={"pair_id": n["pair"]["pair_id"], "label": "same"}).status_code == 429   # too fast
    import time; time.sleep(0.35)
    r = off.post("/api/real/labels", json={"pair_id": n["pair"]["pair_id"], "label": "same"})
    assert r.status_code == 201 and r.json()["secs"] >= 0.3
    assert off.get("/api/real/next").json()["labelled_by_you"] == 1
    ev = aud.get("/api/real/eval").json()
    assert ev["labelled"] == 1 and "iou_baseline" in ev


def test_upload_matches_two_layers(demo, tmp_path):
    import geopandas as gpd
    import shapely
    raw = demo / "raw"
    off = _c(demo, "officer1", "officer@123")
    # a layer shifted 3 m east: the matcher should still link most shapes after removing the offset
    b = gpd.read_file(raw / "osm.geojson").to_crs(32644)
    b["geometry"] = b.geometry.translate(3, 0)
    b.to_crs(4326).to_file(tmp_path / "shifted.geojson", driver="GeoJSON")
    with open(raw / "osm.geojson", "rb") as fa, open(tmp_path / "shifted.geojson", "rb") as fb:
        r = off.post("/api/upload", files={"layer_a": ("a.geojson", fa), "layer_b": ("b.geojson", fb)},
                     data={"name_a": "Cadastre", "name_b": "Municipal"})
    assert r.status_code == 201, r.text
    job = r.json()["job"]
    assert 2.5 < sum(x ** 2 for x in r.json()["coregistration"]["global_shift_m"]) ** 0.5 < 3.5
    res = off.get(f"/api/upload/{job}").json()
    assert res["summary"]["auto_links"] >= 0.9 * res["summary"]["n_a"]
    assert {f["properties"]["status"] for f in res["layers"]["A"]["features"]} <= {"matched", "review", "part_of_larger", "covers_several", "unmatched"}
    assert off.get(f"/api/upload/{job}/links.csv").text.startswith("a,b,p,iou")
    assert [u["job"] for u in off.get("/api/uploads").json()][0] == job
    # another officer can't open it; the supervisor can; auditors can't upload at all
    assert _c(demo, "officer2", "officer@123").get(f"/api/upload/{job}").status_code == 403
    assert _c(demo, "supervisor", "super@123").get(f"/api/upload/{job}").status_code == 200
    aud = _c(demo, "auditor", "audit@123")
    with open(raw / "osm.geojson", "rb") as fa:
        assert aud.post("/api/upload", files={"layer_a": ("a.geojson", fa), "layer_b": ("b.geojson", fa)}).status_code == 403
    assert off.get("/api/upload/../../users").status_code == 404


def test_upload_rejects_bad_inputs(demo, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point, box
    off = _c(demo, "officer1", "officer@123")
    good = tmp_path / "good.geojson"
    gpd.GeoDataFrame(geometry=[box(80.23 + i * 1e-4, 13.04, 80.2301 + i * 1e-4, 13.0401) for i in range(30)], crs=4326).to_file(good, driver="GeoJSON")
    pts = tmp_path / "pts.geojson"
    gpd.GeoDataFrame(geometry=[Point(80.23, 13.04)], crs=4326).to_file(pts, driver="GeoJSON")
    far = tmp_path / "far.geojson"
    gpd.GeoDataFrame(geometry=[box(77.0 + i * 1e-4, 28.6, 77.0001 + i * 1e-4, 28.6001) for i in range(30)], crs=4326).to_file(far, driver="GeoJSON")

    def up(a, b, name_b="b.geojson"):
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return off.post("/api/upload", files={"layer_a": ("a.geojson", fa), "layer_b": (name_b, fb)})
    assert up(good, good, "b.exe").status_code == 415                       # wrong type
    r = up(good, pts); assert r.status_code == 422 and "no polygons" in r.json()["detail"]
    r = up(good, far); assert r.status_code == 422 and "don't overlap" in r.json()["detail"]
    bad = tmp_path / "bad.geojson"; bad.write_text("{not json")
    assert up(good, bad).status_code == 422


def test_review_queue_on_real_data(demo):
    sup, off = _c(demo, "supervisor", "super@123"), _c(demo, "officer1", "officer@123")
    s = sup.get("/api/summary?dataset=real").json()
    assert s["dataset"] == "real" and s["names"]["a"] == "OSM" and "metrics" in s
    pairs = off.get("/api/pairs?dataset=real").json()
    assert pairs and {p["bucket"] for p in pairs} <= {"accept", "review"} and all("t_hi" in p for p in pairs)
    layers = off.get("/api/layers?dataset=real").json()
    assert {f["properties"]["status"] for f in layers["A"]["features"]} <= {"auto", "review", "unmatched"}
    p = pairs[0]
    r = off.post("/api/decisions", json={"a_id": p["a"], "b_id": p["b"], "decision": "accept", "dataset": "real"})
    assert r.status_code == 201 and r.json()["dataset"] == "real"
    # a real pair is not a synthetic pair, and the logs stay separate per dataset (one hash chain)
    assert off.post("/api/decisions", json={"a_id": p["a"], "b_id": p["b"], "decision": "accept"}).status_code == 404
    assert [e["a_id"] for e in off.get("/api/decisions?dataset=real").json()] == [p["a"]]
    assert all(e.get("dataset", "synthetic") == "synthetic" for e in off.get("/api/decisions?dataset=synthetic").json())
    assert off.get("/api/verify").json()["valid"] is True
    assert off.get("/api/truth?dataset=real").status_code == 403
    t = sup.get("/api/truth?dataset=real").json()
    assert set(t) >= {"links", "checked"}
    assert off.get("/api/summary?dataset=bogus").status_code == 422
