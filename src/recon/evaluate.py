"""Exact metrics against the injected ground truth."""
from __future__ import annotations

import pandas as pd

LINK_TYPES = ["clean", "offset", "scale", "rotate", "split", "merge"]


def evaluate(pred: pd.DataFrame, truth: pd.DataFrame, a_meta: pd.DataFrame, b_meta: pd.DataFrame,
             test_a_ids: set[str]) -> dict:
    """pred: a_id, b_id, bucket in {accept, review, reject}. Evaluated on `test_a_ids` only."""
    pred = pred[pred.a_id.isin(test_a_ids)]
    truth = truth[truth.a_id.isin(test_a_ids)]
    true_set = set(zip(truth.a_id, truth.b_id))
    acc = pred[pred.bucket == "accept"]
    rev = pred[pred.bucket == "review"]
    acc_set, rev_set = set(zip(acc.a_id, acc.b_id)), set(zip(rev.a_id, rev.b_id))

    tp = len(acc_set & true_set)
    out: dict = {
        "n_test_parcels": len(test_a_ids),
        "n_true_links": len(true_set),
        "auto_precision": tp / max(len(acc_set), 1),
        "auto_recall": tp / max(len(true_set), 1),
        "assisted_recall": len((acc_set | rev_set) & true_set) / max(len(true_set), 1),
    }
    p, r = out["auto_precision"], out["auto_recall"]
    out["auto_f1"] = 2 * p * r / max(p + r, 1e-9)

    # share of parcels an officer must look at (any candidate link in the review bucket)
    need_review = set(rev.a_id)
    out["review_load"] = len(need_review) / max(len(test_a_ids), 1)
    out["auto_resolved_share"] = 1 - out["review_load"]

    per_type = {}
    for t in LINK_TYPES:
        tt = truth[truth.error_type == t]
        s = set(zip(tt.a_id, tt.b_id))
        if not s:
            continue
        per_type[t] = {
            "n": len(s),
            "auto_recall": len(acc_set & s) / len(s),
            "assisted_recall": len((acc_set | rev_set) & s) / len(s),
        }
    out["per_type"] = per_type

    # false-link rates: links accepted for parcels that have no true counterpart
    missing_a = set(a_meta[(a_meta.error_type == "missing") & a_meta.a_id.isin(test_a_ids)].a_id)
    out["missing_false_link_rate"] = (
        len({a for a, _ in acc_set if a in missing_a}) / len(missing_a) if missing_a else 0.0)
    spurious_b = set(b_meta[b_meta.error_type == "spurious"].b_id)
    seen_sp = {b for b in pred.b_id if b in spurious_b}
    out["spurious_false_link_rate"] = (
        len({b for _, b in acc_set if b in spurious_b}) / len(seen_sp) if seen_sp else 0.0)
    return out


def to_markdown(results: dict[str, dict]) -> str:
    names = list(results)
    lines = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key, label in [("auto_precision", "Auto-accept precision"), ("auto_recall", "Auto-accept recall"),
                       ("auto_f1", "Auto-accept F1"), ("assisted_recall", "Recall incl. review queue"),
                       ("auto_resolved_share", "Parcels needing no human review"),
                       ("missing_false_link_rate", "False links on missing parcels"),
                       ("spurious_false_link_rate", "False links on spurious parcels")]:
        lines.append(f"| {label} | " + " | ".join(f"{results[n][key]:.1%}" for n in names) + " |")
    lines += ["", "Recall by injected error type (auto-accepted / incl. review):", "",
              "| Error type | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for t in LINK_TYPES:
        if t in results[names[0]]["per_type"]:
            n = results[names[0]]["per_type"][t]["n"]
            cells = [f"{results[m]['per_type'][t]['auto_recall']:.0%} / {results[m]['per_type'][t]['assisted_recall']:.0%}"
                     for m in names]
            lines.append(f"| {t} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
