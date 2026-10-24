"""Download every public EV charger in NSW from Open Charge Map.

Run on your own machine (the data site is blocked in the build sandbox):

    python scripts/fetch_chargers.py --key YOUR_OCM_KEY

Get a free key at https://openchargemap.org/site/develop/api .
Saves data/raw/chargers_nsw.csv .

We filter to NSW by a geographic bounding box rather than the state text
field, because many Open Charge Map records leave the state blank. We also
keep full operator info so we can see who owns each charger.
"""
from __future__ import annotations

import argparse
import pandas as pd
import requests

OCM_URL = "https://api.openchargemap.io/v3/poi/"

# NSW bounding box (a little generous; trims QLD/VIC/SA edges only slightly).
NSW_LAT_MIN, NSW_LAT_MAX = -37.6, -28.1
NSW_LON_MIN, NSW_LON_MAX = 140.9, 153.7


def fetch(api_key: str, max_results: int = 20000) -> pd.DataFrame:
    params = {
        "output": "json",
        "countrycode": "AU",
        "maxresults": max_results,
        "compact": "false",   # keep OperatorInfo so we get real operator names
        "verbose": "false",
        "key": api_key,
    }
    r = requests.get(OCM_URL, params=params, timeout=120)
    r.raise_for_status()
    rows = []
    for poi in r.json():
        addr = poi.get("AddressInfo") or {}
        lat, lon = addr.get("Latitude"), addr.get("Longitude")
        if lat is None or lon is None:
            continue
        # Keep only points inside the NSW box.
        if not (NSW_LAT_MIN <= lat <= NSW_LAT_MAX and NSW_LON_MIN <= lon <= NSW_LON_MAX):
            continue
        max_kw = 0.0
        for c in poi.get("Connections") or []:
            kw = c.get("PowerKW") or 0
            max_kw = max(max_kw, float(kw))
        op = poi.get("OperatorInfo") or {}
        rows.append({
            "ocm_id": poi.get("ID"),
            "lat": lat, "lon": lon,
            "postcode": addr.get("Postcode"),
            "power_kw": max_kw,
            "operator": op.get("Title") or "Unknown",
            "title": addr.get("Title"),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="Open Charge Map API key")
    ap.add_argument("--out", default="data/raw/chargers_nsw.csv")
    args = ap.parse_args()

    df = fetch(args.key)
    df.to_csv(args.out, index=False)
    print(f"saved {len(df)} NSW chargers to {args.out}")
    fast = df[df["power_kw"] >= 50]
    print(f"  of which fast (>=50kW): {len(fast)}")
    print("\nTop operators:")
    print(df["operator"].value_counts().head(10).to_string())
