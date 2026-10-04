"""Owner-name generation and realistic spelling variation (benchmark data only)."""
from __future__ import annotations

import re

import numpy as np

FIRST = [
    "Krishnan", "Muthusamy", "Venkatesh", "Lakshmi", "Saraswathi", "Ramasamy", "Subramanian",
    "Meenakshi", "Kannan", "Thiruvengadam", "Selvaraj", "Parvathi", "Annamalai", "Vijayalakshmi",
    "Sundaram", "Rajeshwari", "Balasubramanian", "Chandrasekar", "Gopalakrishnan", "Janaki",
    "Mohammed", "Abdul", "Fathima", "Rahim", "Suresh", "Ramesh", "Anitha", "Deepak", "Priya", "Arun",
]
LAST = [
    "Iyer", "Naidu", "Pillai", "Reddy", "Chettiar", "Gounder", "Mudaliar", "Nair", "Sharma", "Kumar",
    "Rao", "Khan", "Sheikh", "Menon", "Thevar", "Babu", "Raman", "Murthy", "Shetty", "Das",
]

# (pattern, replacement): common transliteration / spelling drift in Indian records
_SPELLING = [
    ("th", "t"), ("ee", "i"), ("aa", "a"), ("v", "w"), ("sh", "s"), ("ss", "s"),
    ("u", "oo"), ("ai", "ay"), ("sw", "s"), ("kh", "k"), ("dh", "d"),
]


def random_name(rng: np.random.Generator) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _typo(s: str, rng: np.random.Generator) -> str:
    if len(s) < 4:
        return s
    i = int(rng.integers(1, len(s) - 2))
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def variant(name: str, rng: np.random.Generator) -> str:
    """Return a plausible differently-written version of the same person's name."""
    toks = name.split()
    kind = rng.choice(["spelling", "initial", "reorder", "case", "typo", "surname_first"])
    if kind == "spelling":
        rules = [r for r in _SPELLING if r[0] in name.lower()]
        if rules:
            pat, rep = rules[int(rng.integers(len(rules)))]
            return re.sub(pat, rep, name, count=1, flags=re.I)
        return _typo(name, rng)
    if kind == "initial" and len(toks) >= 2:
        return f"{toks[0][0]}. {' '.join(toks[1:])}"
    if kind == "reorder" and len(toks) >= 2:
        return f"{toks[-1]}, {' '.join(toks[:-1])}"
    if kind == "case":
        return name.upper()
    if kind == "surname_first" and len(toks) >= 2:
        return " ".join(reversed(toks))
    return _typo(name, rng)


def normalize(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()
