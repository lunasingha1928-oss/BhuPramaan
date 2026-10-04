#!/usr/bin/env python
"""Download building footprints for a bounding box from OSM (Overpass) as GeoJSON.

Run on your own machine. Retries across several public Overpass mirrors and splits the box
into tiles so a busy server doesn't kill the whole request.

    python scripts/fetch_osm.py --bbox 13.0380,80.2330,13.0480,80.2430 --out data/ward.geojson
bbox order is south,west,north,east.
"""
import argparse
import json
import time
import urllib.parse
import urllib.request

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

ap = argparse.ArgumentParser()
ap.add_argument("--bbox", required=True, help="south,west,north,east")
ap.add_argument("--out", default="data/ward.geojson")
ap.add_argument("--tiles", type=int, default=2, help="split the box into NxN tiles (default 2)")
ap.add_argument("--endpoint", default=None, help="use only this Overpass endpoint")
a = ap.parse_args()

s, w, n, e = (float(x) for x in a.bbox.split(","))
endpoints = [a.endpoint] if a.endpoint else ENDPOINTS


def query(bbox: str):
    q = f'[out:json][timeout:90];way["building"]({bbox});out geom;'
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(3):
        for ep in endpoints:
            try:
                req = urllib.request.Request(ep, data=body, headers={"User-Agent": "sih26013-benchmark/0.2"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except Exception as ex:  # noqa: BLE001
                last = f"{ep}: {ex}"
                print(f"  failed {last}")
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"All Overpass mirrors failed. Last error: {last}\n"
                     "Fallback: draw the area on https://overpass-turbo.eu with\n"
                     '  way["building"]({{bbox}}); out geom;  then Export -> GeoJSON, save as data/ward.geojson')


features, seen = [], set()
N = max(1, a.tiles)
for i in range(N):
    for j in range(N):
        bb = f"{s + (n - s) * i / N},{w + (e - w) * j / N},{s + (n - s) * (i + 1) / N},{w + (e - w) * (j + 1) / N}"
        print(f"tile {i * N + j + 1}/{N * N} ...")
        for el in query(bb).get("elements", []):
            if el["id"] in seen:
                continue
            seen.add(el["id"])
            pts = [[p["lon"], p["lat"]] for p in el.get("geometry", [])]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                features.append({"type": "Feature", "properties": {"osm_id": el["id"]},
                                 "geometry": {"type": "Polygon", "coordinates": [pts]}})
with open(a.out, "w") as fh:
    json.dump({"type": "FeatureCollection", "features": features}, fh)
print(f"Saved {len(features)} building footprints to {a.out}")
