"""Attribute integration: schema matching, area-unit inference and attribute conflict detection.

Different departments name and measure things differently ("Pattadar_Name" vs "Assessee",
area in cents vs square feet). This module works out which column means what, which unit an
area column is in, and where the sources disagree about a parcel.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from .names import normalize

CANONICAL = {
    "parcel_ref": ["patta no", "khata no", "parcel id", "property id", "assessment no", "ulpin", "record no"],
    "owner_name": ["owner name", "pattadar name", "assessee", "holder", "khatedar", "owner", "name of owner"],
    "area": ["area", "extent", "plinth area", "size", "built up area", "area sqft", "area cents"],
    "land_use": ["land use", "classification", "usage", "use", "category", "zoning", "classfn"],
    "survey_no": ["survey no", "sf no", "s f no", "khasra no", "plot no", "survey field no"],
}

# square metres per unit
UNITS = {"square metre": 1.0, "square foot": 0.09290304, "square yard": 0.83612736, "cent": 40.468564,
         "ground": 222.967, "acre": 4046.8564, "hectare": 10000.0}

LAND_USE_MAP = {
    "residential": "Residential", "res": "Residential", "r": "Residential", "dwelling": "Residential", "natham": "Residential",
    "commercial": "Commercial", "com": "Commercial", "c": "Commercial", "shop": "Commercial", "business": "Commercial",
    "mixed": "Mixed", "mix": "Mixed", "m": "Mixed", "res cum com": "Mixed",
}


def _clean(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("_", " ")).strip()


def _value_profile(s: pd.Series) -> dict[str, float]:
    """Evidence from the values themselves, per canonical field (0..1)."""
    v = s.dropna().astype(str).head(400)
    if v.empty:
        return {k: 0.0 for k in CANONICAL}
    num = pd.to_numeric(v.str.replace(",", ""), errors="coerce")
    numeric = float(num.notna().mean())
    uniq = v.nunique() / len(v)
    alpha_words = float(v.str.fullmatch(r"[A-Za-z][A-Za-z .,']+").mean())
    multiword = float((v.str.split().str.len() >= 2).mean())
    slash = float(v.str.contains(r"\d+\s*/\s*\w+").mean())
    return {
        "parcel_ref": (1 - numeric * 0.5) * uniq if numeric < 1 else 0.3 * uniq,
        "owner_name": alpha_words * (0.5 + 0.5 * multiword) * uniq,
        "area": numeric * (1.0 if uniq > 0.5 else 0.4),
        "land_use": (1 - numeric) * (1.0 if uniq < 0.05 else 0.0),
        "survey_no": slash,
    }


def match_schema(df: pd.DataFrame) -> list[dict]:
    """Map each column to a canonical field (one-to-one), with a 0..1 confidence."""
    cols = [c for c in df.columns if c != "geometry"]
    fields = list(CANONICAL)
    score = np.zeros((len(cols), len(fields)))
    detail = {}
    for i, c in enumerate(cols):
        prof = _value_profile(df[c])
        for k, f in enumerate(fields):
            name = max(fuzz.token_set_ratio(_clean(c), syn) for syn in CANONICAL[f]) / 100
            score[i, k] = 0.55 * name + 0.45 * prof[f]
            detail[(c, f)] = (name, prof[f])
    r, k = linear_sum_assignment(-score)
    out = []
    for i, j in zip(r, k):
        nm, vp = detail[(cols[i], fields[j])]
        out.append({"column": cols[i], "field": fields[j], "confidence": round(float(score[i, j]), 3),
                    "name_evidence": round(nm, 2), "value_evidence": round(vp, 2)})
    mapped = {o["column"] for o in out}
    out += [{"column": c, "field": None, "confidence": 0.0, "name_evidence": 0, "value_evidence": 0} for c in cols if c not in mapped]
    return out


def infer_area_unit(recorded: np.ndarray, surveyed_m2: np.ndarray) -> dict:
    """Infer the unit of a recorded-area column from parcels whose surveyed area is known."""
    ok = (recorded > 0) & (surveyed_m2 > 0)
    ratio = np.median(surveyed_m2[ok] / recorded[ok])          # m² per recorded unit
    best = min(UNITS, key=lambda u: abs(np.log(UNITS[u] / ratio)))
    return {"unit": best, "m2_per_unit_observed": round(float(ratio), 4), "m2_per_unit_expected": UNITS[best],
            "relative_error": round(float(abs(UNITS[best] - ratio) / UNITS[best]), 4), "parcels_used": int(ok.sum())}


def norm_land_use(v) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return LAND_USE_MAP.get(_clean(str(v)), None)


def owner_similarity(a: str, b: str) -> float:
    """0..1 similarity of two owner names, tolerant of spelling, initials ("K. Iyer") and reordering."""
    ta, tb = normalize(a).split(), normalize(b).split()
    if not ta or not tb:
        return 0.0

    def expand(x, y):   # replace a single-letter initial in x with the matching full word from y
        return [next((w for w in y if len(w) > 1 and w[0] == t), t) if len(t) == 1 else t for t in x]

    ea, eb = " ".join(expand(ta, tb)), " ".join(expand(tb, ta))
    # also compare with spaces removed, so a slipped space ("JanakiR eddy") is not a different person
    joined = fuzz.ratio("".join(sorted(ea.split())), "".join(sorted(eb.split()))) * 0.97
    nospace = fuzz.ratio(ea.replace(" ", ""), eb.replace(" ", "")) * 0.97
    return max(fuzz.token_sort_ratio(ea, eb), fuzz.token_set_ratio(ea, eb) * 0.95, joined, nospace) / 100
