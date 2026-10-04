import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PASSWORDS = {"officer1": "officer@123", "officer2": "officer@123", "supervisor": "super@123",
             "auditor": "audit@123", "admin": "admin@123"}


def _build(tmp_path_factory, name):
    demo = tmp_path_factory.mktemp(name)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo.py"), "--synthetic", "500",
                    "--out", str(demo)], check=True, capture_output=True)
    return demo


def _client(demo, user=None):
    os.environ["RECON_DEMO_DIR"] = str(demo)
    from recon.api import app
    c = TestClient(app)
    if user:
        r = c.post("/api/login", json={"username": user, "password": PASSWORDS[user]})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return _build(tmp_path_factory, "demo")


def test_everything_needs_sign_in(demo):
    c = _client(demo)
    for url in ["/api/summary", "/api/layers", "/api/pairs", "/api/decisions", "/api/verify", "/api/me"]:
        assert c.get(url).status_code == 401, url
    assert c.post("/api/decisions", json={"a_id": "A", "b_id": "B", "decision": "accept"}).status_code == 401
    assert c.get("/api/roles").status_code == 200          # public: shown on the sign-in page


def test_wrong_password_and_lockout(demo):
    c = _client(demo)
    for _ in range(5):
        assert c.post("/api/login", json={"username": "auditor", "password": "nope"}).status_code == 401
    assert c.post("/api/login", json={"username": "auditor", "password": "audit@123"}).status_code == 429
    from recon.api import _fails
    _fails.clear()                                         # don't leak the lockout into other tests


def test_forged_cookie_rejected(demo):
    c = _client(demo)
    c.cookies.set("recon_session", "eyJ1IjoiYWRtaW4iLCJleHAiOjk5OTk5OTk5OTl9.deadbeef")
    assert c.get("/api/me").status_code == 401


def test_each_role_gets_its_own_home_and_pages(demo):
    homes = {"officer1": "review.html", "supervisor": "index.html", "admin": "admin.html"}
    for user, home in homes.items():
        me = _client(demo, user).get("/api/me").json()
        assert me["home"] == home and home in me["pages"]
    assert "review.html" not in _client(demo, "admin").get("/api/me").json()["pages"]


def test_summary_and_layers(demo):
    c = _client(demo, "supervisor")
    s = c.get("/api/summary").json()
    assert s["n_cadastral"] == 500 and "metrics" in s
    layers = c.get("/api/layers").json()
    assert len(layers["A"]["features"]) == 500
    assert {f["properties"]["status"] for f in layers["A"]["features"]} <= {"auto", "review", "unmatched"}
    assert {p["bucket"] for p in c.get("/api/pairs").json()} <= {"accept", "review"}


def test_role_permissions(demo):
    p = _client(demo, "supervisor").get("/api/pairs").json()[-1]
    ids = {"a_id": p["a"], "b_id": p["b"]}
    aud, adm, off = _client(demo, "auditor"), _client(demo, "admin"), _client(demo, "officer2")
    assert aud.post("/api/decisions", json={**ids, "decision": "accept"}).status_code == 403   # auditors read only
    assert adm.post("/api/decisions", json={**ids, "decision": "accept"}).status_code == 403   # admins don't decide
    assert off.get("/api/truth").status_code == 403
    assert off.get("/api/admin/users").status_code == 403
    assert aud.get("/api/decisions").status_code == 200
    r = off.post("/api/decisions", json={**ids, "decision": "accept", "officer": "someone else"})
    assert r.status_code == 201 and r.json()["user"] == "officer2" and r.json()["officer"] == "S. Karthik"


def test_only_supervisor_can_change_a_decision(tmp_path_factory):
    demo = _build(tmp_path_factory, "demo2")
    off, sup = _client(demo, "officer1"), _client(demo, "supervisor")
    p = off.get("/api/pairs").json()[0]
    ids = {"a_id": p["a"], "b_id": p["b"]}
    assert off.post("/api/decisions", json={**ids, "decision": "accept"}).status_code == 201
    for _ in range(20):                                    # spamming the same decision is a no-op
        r = off.post("/api/decisions", json={**ids, "decision": "accept"})
        assert r.status_code == 200 and r.json()["unchanged"] is True
    assert len(off.get("/api/decisions").json()) == 1
    assert off.post("/api/decisions", json={**ids, "decision": "reject", "note": "x"}).status_code == 403
    assert sup.post("/api/decisions", json={**ids, "decision": "reject"}).status_code == 400    # no reason
    r = sup.post("/api/decisions", json={**ids, "decision": "reject", "note": "site visit shows two plots"})
    assert r.status_code == 201 and r.json()["supersedes"] == 1 and r.json()["role"] == "supervisor"
    sup.post("/api/decisions", json={**ids, "decision": "accept", "note": "second visit"})
    sup.post("/api/decisions", json={**ids, "decision": "reject", "note": "third visit"})
    assert sup.post("/api/decisions", json={**ids, "decision": "accept", "note": "too many"}).status_code == 409
    assert len(sup.get("/api/decisions").json()) == 4
    assert sup.get("/api/verify").json()["valid"] is True


def test_tampering_is_detected(tmp_path_factory):
    demo = _build(tmp_path_factory, "demo3")
    c = _client(demo, "officer1")
    for p in c.get("/api/pairs").json()[:3]:
        assert c.post("/api/decisions", json={"a_id": p["a"], "b_id": p["b"], "decision": "accept"}).status_code == 201
    assert c.get("/api/verify").json() == {**c.get("/api/verify").json(), "valid": True, "entries": 3}
    log = demo / "decisions.jsonl"
    lines = log.read_text().splitlines()
    t = json.loads(lines[1]); t["decision"] = "reject"; lines[1] = json.dumps(t)
    log.write_text("\n".join(lines) + "\n")
    bad = c.get("/api/verify").json()
    assert bad["valid"] is False and bad["first_bad_seq"] == 2


def test_unknown_pair_rejected(demo):
    r = _client(demo, "officer1").post("/api/decisions", json={"a_id": "A99999", "b_id": "B99999", "decision": "accept"})
    assert r.status_code == 404


def test_admin_manages_users(tmp_path_factory):
    demo = _build(tmp_path_factory, "demo4")
    adm = _client(demo, "admin")
    r = adm.post("/api/admin/users", json={"username": "officer3", "name": "T. Devi", "role": "officer", "password": "longpassword1"})
    assert r.status_code == 201
    assert adm.post("/api/admin/users", json={"username": "officer3", "name": "Someone", "role": "officer", "password": "longpassword1"}).status_code == 409
    c = _client(demo)
    assert c.post("/api/login", json={"username": "officer3", "password": "longpassword1"}).status_code == 200
    assert adm.patch("/api/admin/users/officer3", json={"active": False}).status_code == 200
    assert c.get("/api/me").status_code == 401                                   # disabled mid-session
    assert adm.patch("/api/admin/users/admin", json={"active": False}).status_code == 400
    events = [e["event"] for e in adm.get("/api/admin/access").json()]
    assert "login" in events and "user_disabled:officer3" in events
    assert json.loads((demo / "users.json").read_text())["officer3"]["password"].startswith("pbkdf2_sha256$")


def test_root_sends_visitors_to_sign_in_and_pages_are_not_cached(demo):
    c = _client(demo)
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/login.html?v=9"
    assert c.get("/login.html").headers["cache-control"] == "no-cache"
    assert c.get("/assets/common.js").headers["cache-control"] == "no-cache"
    off = _client(demo, "officer1")
    assert off.get("/", follow_redirects=False).headers["location"] == "/review.html?v=9"


def test_sign_in_and_out_clear_the_browser_cache(demo):
    c = _client(demo)
    r = c.post("/api/login", json={"username": "officer1", "password": "officer@123"})
    assert r.headers["clear-site-data"] == '"cache"'
    assert c.post("/api/logout").headers["clear-site-data"] == '"cache"'
    assert c.get("/api/me").status_code == 401
