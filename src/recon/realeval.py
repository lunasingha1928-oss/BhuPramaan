"""Accuracy on real data, estimated from a stratified hand-labelled sample.

The sample was drawn in probability strata (more pairs from the uncertain middle than the population
has), so each labelled pair is weighted by population / sampled for its stratum. Results are reported
with 95% Wilson intervals on the number of labelled pairs, and compared with plain IoU matching on the
same pairs.
"""
from __future__ import annotations

import math


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def latest_labels(labels: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for x in labels:
        out[x["pair_id"]] = x
    return out


def evaluate(sample: dict, labels: list[dict], iou_accept: float = 0.5) -> dict:
    pairs = {p["pair_id"]: p for p in sample["pairs"]}
    strata = sample["strata"]
    w = [s["population"] / s["sampled"] if s["sampled"] else 0 for s in strata]
    t_hi, t_lo = sample["thresholds"]["accept"], sample["thresholds"]["reject"]
    lab = latest_labels(labels)
    rows = [(pairs[k], v["label"]) for k, v in lab.items() if k in pairs and v["label"] in ("same", "different")]
    n_unsure = sum(1 for k, v in lab.items() if k in pairs and v["label"] == "unsure")

    def rule_stats(pred):
        tp = fp = fn = 0.0
        ktp = kpos = 0
        for p, y in rows:
            wt = w[p["stratum"]]
            pos = pred(p)
            if pos and y == "same":
                tp += wt; ktp += 1; kpos += 1
            elif pos:
                fp += wt; kpos += 1
            elif y == "same":
                fn += wt
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        lo, hi = wilson(ktp, kpos) if kpos else (None, None)
        return {"precision": prec, "recall": rec, "precision_ci": [lo, hi], "n_predicted": kpos}

    by_stratum = []
    for i, s in enumerate(strata):
        r = [(p, y) for p, y in rows if p["stratum"] == i]
        k = sum(1 for _, y in r if y == "same")
        by_stratum.append({"lo": s["lo"], "hi": s["hi"], "population": s["population"], "labelled": len(r),
                           "mean_p": sum(p["p"] for p, _ in r) / len(r) if r else None,
                           "share_same": k / len(r) if r else None, "ci": list(wilson(k, len(r))) if r else None})
    users = {}
    multi = {}
    for x in labels:
        users[x.get("user", "?")] = users.get(x.get("user", "?"), 0) + 1
        multi.setdefault(x["pair_id"], {})[x.get("user", "?")] = x["label"]
    both = [v for v in multi.values() if len(v) >= 2]
    agree = sum(1 for v in both if len(set(v.values())) == 1)
    return {
        "labelled": len(rows), "unsure": n_unsure, "sample_size": len(pairs),
        "model": {**rule_stats(lambda p: p["p"] >= t_hi), "rule": f"auto-accept at p ≥ {t_hi:.2f}"},
        "model_or_review": {**rule_stats(lambda p: p["p"] >= t_lo), "rule": f"auto-accept or review at p ≥ {t_lo:.2f}"},
        "iou_baseline": {**rule_stats(lambda p: p["iou"] >= iou_accept), "rule": f"IoU ≥ {iou_accept} after co-registration"},
        "combined": {**rule_stats(lambda p: p["p"] >= t_hi or p["iou"] >= iou_accept),
                     "rule": f"p ≥ {t_hi:.2f} or IoU ≥ {iou_accept} (rule picked after the first 102 labels)"},
        **({"iou_no_coreg": {**rule_stats(lambda p: p["iou_raw"] >= iou_accept), "rule": f"IoU ≥ {iou_accept}, maps not co-registered"}}
           if all("iou_raw" in p for p in pairs.values()) else {}),
        "by_stratum": by_stratum, "labellers": users,
        "double_labelled": len(both), "agreement": agree / len(both) if both else None,
        "median_seconds": (sorted(x["secs"] for x in labels if x.get("secs") is not None) or [None])[len([x for x in labels if x.get("secs") is not None]) // 2],
        "note": "Recall is over candidate pairs with model probability ≥ 0.02 (the sampled range).",
    }
