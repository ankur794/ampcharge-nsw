"""Flag which Ampol sites sit on a major road, using OpenStreetMap.

AmpCharge's strategy is highway-corridor charging, so whether a site is on a
motorway/trunk/primary road matters a lot. OSM has those roads; we pull them
for NSW and flag any Ampol site within ~500 m of one.

    python scripts/flag_highways.py

Updates data/raw/ampol_sites_nsw.csv in place (the on_highway column).
"""
from __future__ import annotations

import os
import time
import numpy as np
import pandas as pd
import requests

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
SITES = os.path.join(RAW, "ampol_sites_nsw.csv")
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
HEADERS = {"User-Agent": "ampcharge-student-project/1.0 (contact: bajaj9ankur@gmail.com)"}
THRESHOLD_KM = 0.5

# NSW bounding box
QUERY = """
[out:json][timeout:180];
way["highway"~"^(motorway|trunk|primary)$"](-37.6,140.9,-28.1,153.7);
out geom;
"""


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def main():
    print("Downloading NSW major roads from OpenStreetMap (can take a minute)...")
    data = None
    for server in OVERPASS_SERVERS:
        try:
            r = requests.post(server, data=QUERY.encode("utf-8"),
                              headers=HEADERS, timeout=200)
            r.raise_for_status()
            data = r.json()
            print(f"  got data from {server}")
            break
        except Exception as e:
            print(f"  {server} failed ({e}); trying next server")
            time.sleep(3)
    if data is None:
        print("Overpass unavailable right now. Try again later (on_highway stays False).")
        return
    lats, lons = [], []
    for el in data.get("elements", []):
        for nd in el.get("geometry", []) or []:
            lats.append(nd["lat"]); lons.append(nd["lon"])
    road_lat = np.array(lats); road_lon = np.array(lons)
    print(f"  got {len(road_lat):,} road points")

    sites = pd.read_csv(SITES, dtype={"site_id": str})
    on_hw = []
    for _, s in sites.iterrows():
        d = haversine_km(s["lat"], s["lon"], road_lat, road_lon)
        on_hw.append(bool(d.min() <= THRESHOLD_KM))
    sites["on_highway"] = on_hw
    sites.to_csv(SITES, index=False)
    print(f"flagged {sum(on_hw)} of {len(sites)} sites as on a major road")


if __name__ == "__main__":
    main()
