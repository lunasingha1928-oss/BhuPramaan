"""Spatially-blocked training, probability calibration and threshold selection."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from .features import FEATURES


def assign_roles(centroids_xy: np.ndarray, block_size: float, fracs: list[float], seed: int) -> np.ndarray:
    """Assign each parcel to train/calib/test by *spatial block*, so neighbours never straddle splits."""
    x, y = centroids_xy[:, 0], centroids_xy[:, 1]
    bx = np.floor((x - x.min()) / block_size).astype(int)
    by = np.floor((y - y.min()) / block_size).astype(int)
    keys = bx * 100003 + by
    uniq = np.unique(keys)
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    n = len(uniq)
    n_train = max(1, int(round(fracs[0] * n)))
    n_calib = max(1, int(round(fracs[1] * n)))
    role_of = {}
    for i, k in enumerate(uniq):
        role_of[k] = "train" if i < n_train else ("calib" if i < n_train + n_calib else "test")
    if "test" not in role_of.values():  # tiny datasets
        role_of[uniq[-1]] = "test"
    return np.array([role_of[k] for k in keys])


def fit_model(X: pd.DataFrame, y: np.ndarray, seed: int, cols: list[str] | None = None) -> XGBClassifier:
    model = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08, subsample=0.9,
                          colsample_bytree=0.9, eval_metric="logloss", random_state=seed, n_jobs=2)
    model.fit(X[cols or FEATURES], y)
    return model


def fit_calibrator(p_raw: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    return IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p_raw, y)


def choose_thresholds(p: np.ndarray, y: np.ndarray, target_precision: float, max_missed_true: float) -> tuple[float, float]:
    """t_hi: lowest probability cut whose auto-accepted precision >= target (on calibration data).
    t_lo: highest cut below which we lose at most `max_missed_true` of true links."""
    t_hi = 1.01
    for t in np.unique(p)[::-1]:
        sel = p >= t
        if sel.sum() >= 20 and y[sel].mean() >= target_precision:
            t_hi = float(t)
    pos = p[y == 1]
    t_lo = float(min(np.quantile(pos, max_missed_true), 0.5, t_hi)) if len(pos) else 0.0
    return t_lo, t_hi


def bucket(p: np.ndarray, t_lo: float, t_hi: float) -> np.ndarray:
    return np.where(p >= t_hi, "accept", np.where(p < t_lo, "reject", "review"))
