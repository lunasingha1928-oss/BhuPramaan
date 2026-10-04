import numpy as np

from recon.features import FEATURES
from recon.footprints import synthetic_footprints
from recon.ml import assign_roles
from recon.pipeline import run_benchmark


def test_features_contain_no_identifiers_or_labels():
    assert not {"a_id", "b_id", "label", "role", "a_idx", "b_idx"} & set(FEATURES)


def test_spatial_blocks_never_straddle_roles():
    gdf = synthetic_footprints(600, seed=2)
    cent = np.c_[gdf.geometry.centroid.x, gdf.geometry.centroid.y]
    roles = assign_roles(cent, 150.0, [0.5, 0.2, 0.3], seed=2)
    assert set(roles) == {"train", "calib", "test"}
    bx = np.floor((cent[:, 0] - cent[:, 0].min()) / 150.0).astype(int)
    by = np.floor((cent[:, 1] - cent[:, 1].min()) / 150.0).astype(int)
    for key in set(zip(bx, by)):
        mask = (bx == key[0]) & (by == key[1])
        assert len(set(roles[mask])) == 1


def test_end_to_end_ml_beats_iou_baseline_with_high_precision():
    res = run_benchmark(synthetic_footprints(700, seed=4), seed=4)["results"]
    base, ml = res["IoU baseline"], res["Calibrated XGBoost"]
    assert ml["auto_f1"] > base["auto_f1"]
    assert ml["auto_precision"] >= 0.95
    assert ml["assisted_recall"] >= base["assisted_recall"] - 0.02


def test_real_data_loader_roundtrip(tmp_path):
    from recon.footprints import load_footprints
    src = synthetic_footprints(300, seed=1)[["geometry"]].to_crs(4326)
    p = tmp_path / "f.geojson"
    src.to_file(p, driver="GeoJSON")
    gdf = load_footprints(p)
    assert len(gdf) > 250 and gdf.crs.is_projected and "owner" in gdf
