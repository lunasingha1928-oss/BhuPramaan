"""FastAPI service behind the review console.

Serves precomputed reconciliation results and records officer decisions in an append-only,
hash-chained log (each entry commits to the one before it, so edits or deletions are detectable).

Every data endpoint needs a signed-in user, and each role may only do what `auth.ROLES` allows:
officers make first decisions, only supervisors change a recorded decision, auditors read,
administrators manage accounts. Roles are enforced here, not just hidden in the interface.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

import shapely
import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "ui"
GENESIS = "0" * 64
MAX_ENTRIES_PER_PAIR = 4   # the first decision plus up to three revisions
COOKIE = "recon_session"
MAX_FAILS, FAIL_WINDOW_S = 5, 300
_lock = threading.Lock()
_fails: dict[str, list[float]] = defaultdict(list)

app = FastAPI(title="Parcel Reconciliation Console API", version="0.2")


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Make browsers re-check pages and scripts on every load, so an update is never hidden by the cache."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def demo_dir() -> Path:
    return Path(os.environ.get("RECON_DEMO_DIR", ROOT / "demo"))


@lru_cache(maxsize=8)
def _read(path: str, mtime: float):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load(name: str):
    p = demo_dir() / name
    if not p.exists():
        raise HTTPException(503, f"{name} not found. Run scripts/build_demo.py first.")
    return _read(str(p), p.stat().st_mtime)


def _log_path() -> Path:
    return demo_dir() / "decisions.jsonl"


def _entry_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def _read_log() -> list[dict]:
    p = _log_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- auth dependencies
def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    username = auth.read_token(demo_dir(), token) if token else None
    if not username:
        raise HTTPException(401, "Please sign in.")
    user = auth.load_users(demo_dir()).get(username)
    if not user or not user.get("active", True):
        raise HTTPException(401, "This account is disabled or no longer exists.")
    return auth.public(user)


def require(*roles: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, f"A {user['role_label'].lower()} cannot do this.")
        return user
    return dep


# ---------------------------------------------------------------- sign in / out
class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(body: LoginIn, response: Response):
    uname = body.username.strip().lower()
    now = time.time()
    _fails[uname] = [t for t in _fails[uname] if now - t < FAIL_WINDOW_S]
    if len(_fails[uname]) >= MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Wait five minutes and try again.")
    user = auth.load_users(demo_dir()).get(uname)
    if not user or not user.get("active", True) or not auth.verify_password(body.password, user["password"]):
        _fails[uname].append(now)
        auth.log_access(demo_dir(), "login_failed", uname)
        raise HTTPException(401, "Wrong username or password.")
    _fails.pop(uname, None)
    response.set_cookie(COOKIE, auth.make_token(demo_dir(), uname), httponly=True, samesite="lax",
                        max_age=auth.TOKEN_TTL_S, path="/")
    response.headers["Clear-Site-Data"] = '"cache"'   # drop pages cached by an older version or another role
    auth.log_access(demo_dir(), "login", uname, user["role"])
    return auth.public(user)


@app.post("/api/logout")
def logout(request: Request, response: Response):
    username = auth.read_token(demo_dir(), request.cookies.get(COOKIE, "")) if request.cookies.get(COOKIE) else None
    if username:
        auth.log_access(demo_dir(), "logout", username)
    response.delete_cookie(COOKIE, path="/")
    response.headers["Clear-Site-Data"] = '"cache"'
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/api/session")
def session(request: Request):
    """Like /api/me but never 401: lets the sign-in page check quietly whether someone is signed in."""
    try:
        return {"user": current_user(request)}
    except HTTPException:
        return {"user": None}


@app.get("/api/roles")
def roles():
    """Public: what each role is for (shown on the sign-in page)."""
    return {k: {"label": v["label"], "about": v["about"]} for k, v in auth.ROLES.items()}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- data (any signed-in user)
Dataset = Literal["synthetic", "real"]


def _real_review() -> dict:
    p = demo_dir() / "real" / "review.json"
    if not p.exists():
        raise HTTPException(503, "Real review data not built yet. Run scripts/build_real.py.")
    return _read(str(p), p.stat().st_mtime)


def _real_metrics() -> dict:
    """Live accuracy of the real-data rule from the hand-checked sample (updates as officers check pairs)."""
    from .realeval import evaluate as real_evaluate
    rv = _real_review()["summary"]
    try:
        ev = real_evaluate(_real("real_sample.json"), _labels(), pol_iou())
    except HTTPException:
        ev = None

    def pack(m, auto_share):
        if not m or m.get("precision") is None:
            return {"auto_precision": None, "auto_recall": None, "auto_f1": None, "auto_resolved_share": auto_share}
        pr, rc = m["precision"], m["recall"]
        return {"auto_precision": pr, "auto_recall": rc, "auto_f1": 2 * pr * rc / (pr + rc) if pr + rc else None,
                "auto_resolved_share": auto_share, "precision_ci": m.get("precision_ci")}
    share = rv["n_auto_parcels"] / max(rv["n_cadastral"], 1)
    return {"model": pack(ev and ev.get("combined"), share),
            "baseline": pack(ev and (ev.get("iou_no_coreg") or ev.get("iou_baseline")), None),
            "labelled": ev["labelled"] if ev else 0}


@app.get("/api/summary")
def summary(dataset: Dataset = "synthetic", user: dict = Depends(current_user)):
    if dataset == "real":
        rv = _real_review()["summary"]
        return {**rv, "dataset": "real", "metrics": _real_metrics(), "target_auto_precision": None,
                "shift_description": "real data: no planted errors"}
    return {**_load("summary.json"), "dataset": "synthetic",
            "names": {"a": "Cadastral", "b": "Revenue", "a_long": "cadastral parcel", "b_long": "revenue parcel"}}


@app.get("/api/layers")
def layers(dataset: Dataset = "synthetic", user: dict = Depends(current_user)):
    return _real_review()["layers"] if dataset == "real" else _load("layers.json")


@app.get("/api/pairs")
def pairs(bucket: str | None = None, dataset: Dataset = "synthetic", user: dict = Depends(current_user)):
    data = _real_review()["pairs"] if dataset == "real" else _load("pairs.json")
    return [p for p in data if p["bucket"] == bucket] if bucket else data


@app.get("/api/methodology")
def methodology(user: dict = Depends(current_user)):
    """Multi-seed robustness and distribution-shift results, if the scripts were run with --save."""
    out = {}
    for k, name in (("robustness", "robustness.json"), ("shift", "shift.json")):
        p = demo_dir() / name
        out[k] = _read(str(p), p.stat().st_mtime) if p.exists() else None
    return out


@app.get("/api/truth")
def truth(dataset: Dataset = "synthetic", user: dict = Depends(require("supervisor", "admin"))):
    """Synthetic: the injected ground truth. Real: the hand-checked labels (only sampled pairs have one)."""
    if dataset == "real":
        from .realeval import latest_labels
        lab = latest_labels(_labels())
        return {"links": [k for k, v in lab.items() if v["label"] == "same"],
                "checked": [k for k, v in lab.items() if v["label"] in ("same", "different")], "a_type": {}}
    return _load("truth.json")


@app.get("/api/decisions")
def decisions(dataset: Dataset | None = None, user: dict = Depends(current_user)):
    log = _read_log()
    return log if dataset is None else [e for e in log if e.get("dataset", "synthetic") == dataset]


@app.get("/api/verify")
def verify(user: dict = Depends(current_user)):
    prev, log = GENESIS, _read_log()
    for i, e in enumerate(log):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("prev") != prev or e.get("seq") != i + 1 or _entry_hash(prev, body) != e.get("hash"):
            return {"valid": False, "entries": len(log), "first_bad_seq": i + 1}
        prev = e["hash"]
    return {"valid": True, "entries": len(log), "head": prev if log else None}


# ---------------------------------------------------------------- integration outputs
def _harmonised_with_decisions() -> dict:
    """The harmonised layer, with each parcel's latest officer decisions attached."""
    fc = _load("harmonised.json")
    latest: dict[str, list[dict]] = {}
    for e in _read_log():
        latest.setdefault(e["a_id"], [])
        latest[e["a_id"]] = [x for x in latest[e["a_id"]] if x["b_id"] != e["b_id"]] + [e]
    feats = []
    for f in fc["features"]:
        p = dict(f["properties"])
        ds = latest.get(p["parcel_id"], [])
        p["officer_decisions"] = "; ".join(f"{d['b_id']} {d['decision']}ed by {d['officer']}" for d in ds)
        feats.append({**f, "properties": p})
    return {**fc, "features": feats}


@app.get("/api/harmonised")
def harmonised(user: dict = Depends(current_user)):
    return _harmonised_with_decisions()


@app.get("/api/quality")
def quality(user: dict = Depends(require("supervisor", "auditor", "admin"))):
    return _load("quality.json")


@app.get("/api/changes")
def changes(user: dict = Depends(require("officer", "supervisor", "auditor"))):
    return _load("changes.json")


def _csv(rows: list[dict], cols: list[str]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


def _attach(body: str, name: str, media: str) -> Response:
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


HARM_COLS = ["parcel_id", "confidence", "band", "owner", "patta_no", "survey_no", "assessment_no", "land_use",
             "surveyed_area_m2", "recorded_area_m2", "area_diff_pct", "plinth_area_m2", "link_type", "revenue_ids",
             "sources", "n_conflicts", "conflicts", "officer_decisions", "spatial", "source", "topology", "attributes"]


@app.get("/api/export/{name}")
def export(name: str, user: dict = Depends(require("supervisor", "auditor", "admin"))):
    if name == "harmonised.geojson":
        return _attach(json.dumps(_harmonised_with_decisions()), name, "application/geo+json")
    if name == "harmonised.csv":
        rows = [f["properties"] for f in _harmonised_with_decisions()["features"]]
        return _attach(_csv(rows, HARM_COLS), name, "text/csv")
    if name == "conflicts.csv":
        return _attach(_csv(_load("quality.json")["conflicts"]["list"], ["parcel_id", "type", "detail"]), name, "text/csv")
    if name == "changes.geojson":
        fc = _load("changes.json")["features"]
        return _attach(json.dumps(fc), name, "application/geo+json")
    raise HTTPException(404, "Unknown export.")


# ---------------------------------------------------------------- real data + hand labelling
def _real_dir() -> Path:
    return demo_dir() / "real"


def _real(name: str):
    p = _real_dir() / name
    if not p.exists():
        raise HTTPException(503, "Real-data results not built yet. Run scripts/fetch_real.py, then scripts/build_real.py.")
    return _read(str(p), p.stat().st_mtime)


def _labels() -> list[dict]:
    p = _real_dir() / "labels.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


class LabelIn(BaseModel):
    pair_id: str = Field(max_length=40)
    label: Literal["same", "different", "unsure"]


MIN_LABEL_SECONDS = float(os.environ.get("RECON_MIN_LABEL_SECONDS", "3"))
_served: dict[tuple[str, str], float] = {}     # (user, pair_id) -> when the pair was shown


@app.get("/api/real/summary")
def real_summary(user: dict = Depends(current_user)):
    return _real("real.json")


@app.get("/api/real/temporal")
def real_temporal(user: dict = Depends(require("officer", "supervisor", "auditor"))):
    return _real("temporal.json")


@app.get("/api/real/layers")
def real_layers(user: dict = Depends(current_user)):
    return _real("real_layers.json")


@app.get("/api/real/next")
def real_next(user: dict = Depends(require("officer", "supervisor"))):
    """Next pair this user has not labelled. The model's probability is withheld so labels stay blind."""
    sample = _real("real_sample.json")
    mine = {x["pair_id"] for x in _labels() if x.get("user") == user["username"]}
    todo = [p for p in sample["pairs"] if p["pair_id"] not in mine]
    if not todo:
        return {"done": True, "labelled_by_you": len(mine), "total": len(sample["pairs"])}
    p = todo[0]
    _served[(user["username"], p["pair_id"])] = time.monotonic()
    return {"done": False, "min_seconds": MIN_LABEL_SECONDS, "labelled_by_you": len(mine), "total": len(sample["pairs"]),
            "pair": {k: p[k] for k in ("pair_id", "src_a", "src_b", "geom_a", "geom_b", "geom_b_aligned") if k in p}}


@app.post("/api/real/labels", status_code=201)
def real_label(body: LabelIn, user: dict = Depends(require("officer", "supervisor"))):
    sample = _real("real_sample.json")
    if body.pair_id not in {p["pair_id"] for p in sample["pairs"]}:
        raise HTTPException(404, "Not a sampled pair.")
    shown = _served.get((user["username"], body.pair_id))
    secs = None if shown is None else time.monotonic() - shown
    if secs is None or secs < MIN_LABEL_SECONDS:      # a label needs a real look at the imagery
        raise HTTPException(429, f"Too fast: look at the imagery for at least {MIN_LABEL_SECONDS:.0f} seconds per pair.")
    _served.pop((user["username"], body.pair_id), None)
    entry = {"pair_id": body.pair_id, "label": body.label, "user": user["username"], "role": user["role"], "secs": round(secs, 1),
             "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _lock:
        with (_real_dir() / "labels.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    return entry


@app.get("/api/real/eval")
def real_eval(user: dict = Depends(current_user)):
    from .realeval import evaluate as real_evaluate
    return real_evaluate(_real("real_sample.json"), _labels(), pol_iou())


def pol_iou() -> float:
    try:
        return float(yaml.safe_load((ROOT / "config" / "policy.yaml").read_text())["baseline"]["accept_iou"])
    except Exception:  # noqa: BLE001
        return 0.5


# ---------------------------------------------------------------- decisions
class DecisionIn(BaseModel):
    a_id: str
    b_id: str
    decision: Literal["accept", "reject"]
    note: str = Field(default="", max_length=500)
    dataset: Dataset = "synthetic"


@app.post("/api/decisions", status_code=201)
def add_decision(d: DecisionIn, response: Response, user: dict = Depends(require("officer", "supervisor"))):
    """Record a decision on a candidate link.

    - The decision is signed with the logged-in user's name and role (never taken from the request).
    - Repeating the current decision is a no-op (nothing is appended).
    - Changing a recorded decision is supervisor-only, needs a written reason, is linked to the entry it
      replaces, and is capped, so every change stays explainable.
    """
    pool = _real_review()["pairs"] if d.dataset == "real" else _load("pairs.json")
    match = next((p for p in pool if p["a"] == d.a_id and p["b"] == d.b_id), None)
    if match is None:
        raise HTTPException(404, "No such candidate pair")
    with _lock:
        log = _read_log()
        mine = [e for e in log if e["a_id"] == d.a_id and e["b_id"] == d.b_id]
        last = mine[-1] if mine else None
        if last and last["decision"] == d.decision:
            response.status_code = 200
            return {**last, "unchanged": True}
        if last and not user["can"]["override"]:
            raise HTTPException(403, "This link already has a recorded decision. Only a supervisor can change it.")
        if last and not d.note.strip():
            raise HTTPException(400, "A reason is required to change an earlier decision.")
        if len(mine) >= MAX_ENTRIES_PER_PAIR:
            raise HTTPException(409, f"This link has already been revised {MAX_ENTRIES_PER_PAIR - 1} times; "
                                     "it needs an offline review.")
        prev = log[-1]["hash"] if log else GENESIS
        body = {"seq": len(log) + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "a_id": d.a_id, "b_id": d.b_id, "decision": d.decision,
                "officer": user["name"], "user": user["username"], "role": user["role"], "note": d.note,
                "model_p": match["p"], "model_bucket": match["bucket"], "dataset": d.dataset,
                "supersedes": last["seq"] if last else None, "prev": prev}
        entry = {**body, "hash": _entry_hash(prev, body)}
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    return entry


# ---------------------------------------------------------------- administration
class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-z0-9._-]+$")
    name: str = Field(min_length=2, max_length=60)
    role: Literal["officer", "supervisor", "auditor", "admin"]
    password: str = Field(min_length=8, max_length=200)


class UserPatch(BaseModel):
    active: bool


@app.get("/api/admin/users")
def list_users(user: dict = Depends(require("admin"))):
    return [auth.public(u) for u in auth.load_users(demo_dir()).values()]


@app.post("/api/admin/users", status_code=201)
def create_user(body: NewUser, user: dict = Depends(require("admin"))):
    users = auth.load_users(demo_dir())
    if body.username in users:
        raise HTTPException(409, "That username is taken.")
    users[body.username] = {"username": body.username, "name": body.name.strip(), "role": body.role, "active": True,
                            "created": auth.now_iso(), "password": auth.hash_password(body.password)}
    auth.save_users(demo_dir(), users)
    auth.log_access(demo_dir(), f"user_created:{body.username}", user["username"], user["role"])
    return auth.public(users[body.username])


@app.patch("/api/admin/users/{username}")
def update_user(username: str, body: UserPatch, user: dict = Depends(require("admin"))):
    users = auth.load_users(demo_dir())
    if username not in users:
        raise HTTPException(404, "No such user.")
    if username == user["username"] and not body.active:
        raise HTTPException(400, "You cannot disable your own account.")
    users[username]["active"] = body.active
    auth.save_users(demo_dir(), users)
    auth.log_access(demo_dir(), f"user_{'enabled' if body.active else 'disabled'}:{username}", user["username"], user["role"])
    return auth.public(users[username])


# ---------------------------------------------------------------- upload your own layers
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
UPLOAD_MAX_FEATURES = 20_000
UPLOAD_TYPES = (".geojson", ".json", ".gpkg", ".zip")


def _uploads_dir() -> Path:
    d = demo_dir() / "uploads"
    d.mkdir(exist_ok=True)
    return d


def _job_dir(job: str) -> Path:
    if not job.isalnum() or len(job) > 32:
        raise HTTPException(404, "No such upload.")
    d = _uploads_dir() / job
    if not (d / "result.json").exists():
        raise HTTPException(404, "No such upload.")
    return d


async def _save_upload(f: UploadFile, dest_dir: Path, stem: str) -> Path:
    name = (f.filename or "").lower()
    ext = next((e for e in UPLOAD_TYPES if name.endswith(e)), None)
    if not ext:
        raise HTTPException(415, f"{f.filename}: use .geojson, .gpkg or a .zip with a Shapefile.")
    data = await f.read(UPLOAD_MAX_BYTES + 1)
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(413, f"{f.filename}: larger than {UPLOAD_MAX_BYTES // 2**20} MB.")
    if not data:
        raise HTTPException(400, f"{f.filename}: empty file.")
    out = dest_dir / (stem + (".geojson" if ext == ".json" else ext))
    out.write_bytes(data)
    return out


def _fc(g, props=None):
    g4 = g.to_crs(4326)
    g4 = g4.assign(geometry=shapely.set_precision(g4.geometry.values, 1e-7))
    cols = ["id"] + list(props or [])
    return json.loads(g4[cols + ["geometry"]].to_json(drop_id=True))


def _run_upload(dir_: Path, pa: Path, pb: Path, name_a: str, name_b: str, do_coreg: bool, user: dict) -> dict:
    from . import realmatch
    try:
        matcher = realmatch.load_matcher(_real_dir() / "matcher")
    except FileNotFoundError:
        raise HTTPException(503, "The matcher is not built yet. Run scripts/build_real.py once.")
    try:
        A = realmatch.load_layer(pa, name_a, prefix="A", max_features=UPLOAD_MAX_FEATURES)
        B = realmatch.load_layer(pb, name_b, crs=A.crs, prefix="B", max_features=UPLOAD_MAX_FEATURES)
    except realmatch.LayerError as e:
        raise HTTPException(422, str(e))
    if not shapely.box(*A.total_bounds).buffer(50).intersects(shapely.box(*B.total_bounds)):
        raise HTTPException(422, "The two layers don't overlap. Check that they cover the same area (and their coordinate systems).")
    f, Bm, rep, desc, rel = realmatch.match_layers(A, B, matcher, name_a, name_b, do_coreg=do_coreg)
    status_a, status_b = {}, {}
    for col, st in (("a_id", status_a), ("b_id", status_b)):
        for i in f[col][f.bucket == "review"]:
            st[i] = "review"
        for i in f[col][f.bucket == "accept"]:
            st[i] = "matched"
    for small, big in rel["a_in_b"].items():
        status_a.setdefault(small, "part_of_larger"); status_b.setdefault(big, "covers_several")
    for small, big in rel["b_in_a"].items():
        status_b.setdefault(small, "part_of_larger"); status_a.setdefault(big, "covers_several")
    A = A.assign(status=[status_a.get(i, "unmatched") for i in A.id])
    B = B.assign(status=[status_b.get(i, "unmatched") for i in B.id])
    Bm = Bm.assign(status=B.status.values)
    links = f[f.bucket != "reject"].sort_values("p", ascending=False)
    result = {
        "job": dir_.name, "created": auth.now_iso(), "user": user["username"],
        "names": {"a": name_a, "b": name_b}, "crs": f"EPSG:{A.crs.to_epsg()}", "coregistration": rep,
        "summary": desc, "why": {k: int(v) for k, v in f.why[f.bucket == "accept"].value_counts().items()},
        "thresholds": {"accept": matcher.t_hi, "review": matcher.t_lo, "iou_accept": 0.5},
        "layers": {"A": _fc(A, ["status"]), "B": _fc(B, ["status"]), "B_aligned": _fc(Bm, ["status"])},
        "links": [{"a": r.a_id, "b": r.b_id, "p": round(float(r.p), 3), "iou": round(float(r.iou), 3),
                   "offset_m": round(float(r.centroid_dist), 2), "bucket": r.bucket, "why": r.why} for r in links.itertuples()],
        "note": "Matched with the model and rules validated on 300 hand-checked real building pairs (T. Nagar). "
                "Accuracy on other areas and on parcel boundaries (rather than buildings) is not yet measured.",
    }
    (dir_ / "result.json").write_text(json.dumps(result))
    return result


@app.post("/api/upload", status_code=201)
async def upload(request: Request, layer_a: UploadFile = File(...), layer_b: UploadFile = File(...),
                 name_a: str = Form("Layer A", max_length=40), name_b: str = Form("Layer B", max_length=40),
                 coregister: bool = Form(True), user: dict = Depends(require("officer", "supervisor"))):
    import secrets
    from starlette.concurrency import run_in_threadpool
    job = secrets.token_hex(6)
    d = _uploads_dir() / job
    d.mkdir()
    pa = await _save_upload(layer_a, d, "a")
    pb = await _save_upload(layer_b, d, "b")
    res = await run_in_threadpool(_run_upload, d, pa, pb, name_a.strip() or "Layer A", name_b.strip() or "Layer B", coregister, user)
    auth.log_access(demo_dir(), f"upload:{job}", user["username"], user["role"])
    return {k: v for k, v in res.items() if k != "layers"} | {"links": len(res["links"])}


@app.get("/api/uploads")
def uploads(user: dict = Depends(require("officer", "supervisor"))):
    out = []
    for d in sorted(_uploads_dir().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        r = d / "result.json"
        if not r.exists():
            continue
        res = _read(str(r), r.stat().st_mtime)
        if user["role"] == "supervisor" or res["user"] == user["username"]:
            out.append({k: res[k] for k in ("job", "created", "user", "names")} |
                       {"auto_links": res["summary"]["auto_links"], "review_links": res["summary"]["review_links"]})
    return out[:50]


@app.get("/api/upload/{job}")
def upload_result(job: str, user: dict = Depends(require("officer", "supervisor"))):
    r = _job_dir(job) / "result.json"
    res = _read(str(r), r.stat().st_mtime)
    if user["role"] != "supervisor" and res["user"] != user["username"]:
        raise HTTPException(403, "This upload belongs to another user.")
    return res


@app.get("/api/upload/{job}/links.csv")
def upload_links_csv(job: str, user: dict = Depends(require("officer", "supervisor"))):
    res = upload_result(job, user)
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["a", "b", "p", "iou", "offset_m", "bucket", "why"])
    w.writeheader(); w.writerows(res["links"])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="links_{job}.csv"'})


@app.get("/api/admin/access")
def access_log(user: dict = Depends(require("admin"))):
    return auth.read_access(demo_dir())


@app.get("/api/admin/system")
def system(user: dict = Depends(require("admin"))):
    policy_path = ROOT / "config" / "policy.yaml"
    files = {}
    for name in ("summary.json", "layers.json", "pairs.json", "harmonised.json", "quality.json", "changes.json",
                 "robustness.json", "shift.json", "decisions.jsonl"):
        p = demo_dir() / name
        files[name] = {"present": p.exists(),
                       "updated": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds") if p.exists() else None,
                       "bytes": p.stat().st_size if p.exists() else 0}
    return {"policy": yaml.safe_load(policy_path.read_text()) if policy_path.exists() else None, "files": files}


if UI_DIR.exists():
    @app.get("/", include_in_schema=False)
    def index(request: Request):
        token = request.cookies.get(COOKIE)
        username = auth.read_token(demo_dir(), token) if token else None
        user = auth.load_users(demo_dir()).get(username) if username else None
        if not user or not user.get("active", True):
            return RedirectResponse("/login.html?v=9")
        return RedirectResponse("/" + auth.ROLES[user["role"]]["home"] + "?v=9")

    app.mount("/", StaticFiles(directory=UI_DIR), name="ui")
