"""Users, roles, password hashing and signed session tokens (standard library only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# One place that says what each role is for, which pages it sees and what it may do.
ROLES: dict[str, dict] = {
    "officer": {
        "label": "Revenue officer",
        "about": "Works through the review queue and records the first decision on each flagged link.",
        "home": "review.html",
        "pages": ["review.html", "map.html", "changes.html", "real.html", "upload.html"],
        "can": {"decide": True, "override": False, "truth": False, "admin": False, "export": False, "label": True},
    },
    "supervisor": {
        "label": "Supervisor",
        "about": "Oversees the ward, reviews links, and is the only role that can change a recorded decision.",
        "home": "index.html",
        "pages": ["index.html", "review.html", "map.html", "quality.html", "changes.html", "real.html", "upload.html", "audit.html", "method.html"],
        "can": {"decide": True, "override": True, "truth": True, "admin": False, "export": True, "label": True},
    },
    "auditor": {
        "label": "Auditor",
        "about": "Read-only. Checks the audit trail, verifies the hash chain and exports records.",
        "home": "audit.html",
        "pages": ["audit.html", "index.html", "quality.html", "changes.html", "real.html", "method.html"],
        "can": {"decide": False, "override": False, "truth": False, "admin": False, "export": True, "label": False},
    },
    "admin": {
        "label": "System administrator",
        "about": "Manages user accounts and checks the data build and policy settings. Cannot decide links.",
        "home": "admin.html",
        "pages": ["admin.html", "index.html", "quality.html", "real.html", "audit.html", "method.html"],
        "can": {"decide": False, "override": False, "truth": True, "admin": True, "export": True, "label": False},
    },
}

# Demo accounts created on first run. Change or disable them before any real use.
DEMO_USERS = [
    ("officer1", "R. Meena", "officer", "officer@123"),
    ("officer2", "S. Karthik", "officer", "officer@123"),
    ("supervisor", "A. Rahman", "supervisor", "super@123"),
    ("auditor", "P. Lakshmi", "auditor", "audit@123"),
    ("admin", "System Admin", "admin", "admin@123"),
]

TOKEN_TTL_S = 8 * 3600
PBKDF2_ROUNDS = 200_000
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, dk = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(test.hex(), dk)
    except (ValueError, TypeError):
        return False


def _users_path(d: Path) -> Path:
    return d / "users.json"


def load_users(d: Path) -> dict[str, dict]:
    p = _users_path(d)
    with _lock:
        if not p.exists():
            d.mkdir(parents=True, exist_ok=True)
            users = {u: {"username": u, "name": n, "role": r, "active": True, "created": now_iso(),
                         "password": hash_password(pw)} for u, n, r, pw in DEMO_USERS}
            p.write_text(json.dumps(users, indent=2), encoding="utf-8")
            return users
        return json.loads(p.read_text(encoding="utf-8"))


def save_users(d: Path, users: dict[str, dict]) -> None:
    with _lock:
        tmp = _users_path(d).with_suffix(".tmp")
        tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
        tmp.replace(_users_path(d))


def public(user: dict) -> dict:
    role = ROLES[user["role"]]
    return {"username": user["username"], "name": user["name"], "role": user["role"], "role_label": role["label"],
            "about": role["about"], "home": role["home"], "pages": role["pages"], "can": role["can"],
            "active": user.get("active", True), "created": user.get("created")}


def _secret(d: Path) -> bytes:
    env = os.environ.get("RECON_SECRET")
    if env:
        return env.encode()
    p = d / ".secret"
    with _lock:
        if not p.exists():
            d.mkdir(parents=True, exist_ok=True)
            p.write_text(secrets.token_hex(32))
        return p.read_text().strip().encode()


def make_token(d: Path, username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": int(time.time()) + TOKEN_TTL_S}).encode()).decode()
    sig = hmac.new(_secret(d), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_token(d: Path, token: str) -> str | None:
    """Return the username if the token is genuine and unexpired."""
    try:
        payload, sig = token.rsplit(".", 1)
        good = hmac.new(_secret(d), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        return data["u"] if data["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def log_access(d: Path, event: str, username: str, role: str | None = None) -> None:
    with _lock:
        with (d / "access.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": now_iso(), "event": event, "user": username, "role": role}) + "\n")


def read_access(d: Path, limit: int = 50) -> list[dict]:
    p = d / "access.jsonl"
    if not p.exists():
        return []
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines[-limit:]][::-1]
