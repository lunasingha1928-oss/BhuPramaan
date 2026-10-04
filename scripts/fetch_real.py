#!/usr/bin/env python
"""Download REAL open data for the study area (run on your own machine; needs internet).

  * Microsoft Global ML Building Footprints (ODbL)  -> data/real/microsoft_buildings.geojson
  * OpenStreetMap roads (ODbL)                       -> data/real/osm_roads.geojson
  * OpenStreetMap land-use areas (ODbL)              -> data/real/osm_landuse.geojson

OSM buildings are already in data/ward.geojson (scripts/fetch_osm.py). Google Open Buildings come
from Earth Engine: see scripts/gee_google_buildings.js.

    python scripts/fetch_real.py --bbox 13.0380,80.2330,13.0480,80.2430
bbox order: south,west,north,east (same as fetch_osm.py).
"""
import argparse
import csv
import gzip
import io
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

MS_LINKS = "https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = {"User-Agent": "sih26013-real-data/0.1"}

ap = argparse.ArgumentParser()
ap.add_argument("--bbox", required=True, help="south,west,north,east")
ap.add_argument("--out", default="data/real")
ap.add_argument("--links", default=MS_LINKS, help="Microsoft dataset-links.csv URL, if it has moved")
ap.add_argument("--skip-microsoft", action="store_true")
ap.add_argument("--skip-osm", action="store_true")
a = ap.parse_args()
S, W, N, E = (float(x) for x in a.bbox.split(","))
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)


def get(url, data=None, timeout=180, tries=3):
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as ex:  # noqa: BLE001
            last = ex
            print(f"  retry {t + 1}: {ex}")
            time.sleep(4 * (t + 1))
    raise RuntimeError(f"failed: {url}: {last}")


def quadkey(lat, lon, z=9):
    s = math.sin(math.radians(lat))
    x = int((lon + 180) / 360 * 2 ** z)
    y = int((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * 2 ** z)
    q = ""
    for i in range(z, 0, -1):
        d, m = 0, 1 << (i - 1)
        if x & m:
            d += 1
        if y & m:
            d += 2
        q += str(d)
    return q


def in_bbox(coords):
    for lon, lat in coords:
        if W <= lon <= E and S <= lat <= N:
            return True
    return False


# ---------------------------------------------------------------- Microsoft footprints
if not a.skip_microsoft:
    print("Microsoft: reading dataset index ...")
    links = list(csv.DictReader(io.StringIO(get(a.links).decode())))
    want = {quadkey(lat, lon) for lat in (S, N) for lon in (W, E)}
    rows = [r for r in links if r["Location"] == "India" and str(r["QuadKey"]).zfill(9) in want]
    if not rows:
        raise SystemExit(f"No Microsoft tiles for quadkeys {want}. Check the index URL (--links).")
    feats = []
    for r in rows:
        print(f"Microsoft: downloading tile {r['QuadKey']} ({r.get('Size', '?')}) ...")
        raw = gzip.decompress(get(r["Url"], timeout=600))
        for line in raw.decode().splitlines():
            if not line.strip():
                continue
            f = json.loads(line)
            ring = f["geometry"]["coordinates"][0]
            if in_bbox(ring):
                feats.append({"type": "Feature", "geometry": f["geometry"],
                              "properties": {"source": "microsoft", **(f.get("properties") or {})}})
    (out / "microsoft_buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"Microsoft: saved {len(feats)} footprints")


# ---------------------------------------------------------------- OSM roads and land use
def overpass(query):
    body = urllib.parse.urlencode({"data": query}).encode()
    for ep in OVERPASS:
        try:
            return json.loads(get(ep, data=body, tries=2))
        except Exception as ex:  # noqa: BLE001
            print(f"  {ep} failed: {ex}")
    raise SystemExit("All Overpass mirrors failed; try again in a few minutes.")


if not a.skip_osm:
    bb = f"{S},{W},{N},{E}"
    print("OSM: roads ...")
    d = overpass(f'[out:json][timeout:120];way["highway"]({bb});out geom;')
    roads = [{"type": "Feature", "properties": {"osm_id": e["id"], "highway": e["tags"].get("highway"),
                                                "name": e["tags"].get("name"), "lanes": e["tags"].get("lanes"),
                                                "width": e["tags"].get("width")},
              "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in e["geometry"]]}}
             for e in d.get("elements", []) if len(e.get("geometry", [])) >= 2]
    (out / "osm_roads.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": roads}))
    print(f"OSM: saved {len(roads)} road segments")
    print("OSM: land use ...")
    d = overpass(f'[out:json][timeout:120];(way["landuse"]({bb});way["leisure"="park"]({bb});'
                 f'way["amenity"~"school|hospital|place_of_worship"]({bb}););out geom;')
    lu = []
    for e in d.get("elements", []):
        pts = [[p["lon"], p["lat"]] for p in e.get("geometry", [])]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            t = e.get("tags", {})
            lu.append({"type": "Feature", "properties": {"osm_id": e["id"], "landuse": t.get("landuse") or t.get("leisure") or t.get("amenity")},
                       "geometry": {"type": "Polygon", "coordinates": [pts]}})
    (out / "osm_landuse.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": lu}))
    print(f"OSM: saved {len(lu)} land-use areas")

print(f"Done. Files are in {out}/")
