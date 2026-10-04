#!/usr/bin/env python
"""Start the review console at http://127.0.0.1:8000"""
import argparse
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
a = ap.parse_args()
uvicorn.run("recon.api:app", host=a.host, port=a.port, log_level="info")
