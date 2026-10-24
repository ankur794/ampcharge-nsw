"""Pull Ampol/Caltex sites out of the fuel.db from the fuel-price project.

Tailored to that database's schema:
    stations(stationcode, name, address, latitude, longitude, brand)

Run (point --db at your fuel.db):
    python scripts/extract_ampol_sites.py --db ~/Desktop/fuel-price-project/fuel.db

Writes data/raw/ampol_sites_nsw.csv with:
    site_id, name, lat, lon, postcode, has_foodary, is_24_7, on_highway

- Ampol/Caltex/EG Ampol brands are kept (Caltex sites are now Ampol).
- has_foodary is set automatically from the "Ampol Foodary" brand.
- postcode is parsed from the address (last 4-digit number).
- is_24_7 and on_highway start False; fill any you know by editing the CSV.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import pandas as pd

KEEP = ["ampol", "caltex"]  # Caltex rebranded to Ampol in Australia


def extract_postcode(address: str):
    if not isinstance(address, str):
        return None
    # NSW postcodes are 2xxx/23xx; take the last 4-digit run in the address.
    matches = re.findall(r"\b(\d{4})\b", address)
    return matches[-1] if matches else None


def main(db, out):
    con = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM stations", con)
    con.close()

    brand_l = df["brand"].str.lower().fillna("")
    keep = brand_l.str.contains("|".join(KEEP))
    ampol = df[keep].copy()

    out_df = pd.DataFrame({
        "site_id": ampol["stationcode"].astype(str),
        "name": ampol["name"],
        "lat": ampol["latitude"],
        "lon": ampol["longitude"],
        "postcode": ampol["address"].map(extract_postcode),
        "has_foodary": brand_l[keep].str.contains("foodary").values,
        "is_24_7": False,
        "on_highway": False,
    })
    out_df = out_df.drop_duplicates("site_id").dropna(subset=["lat", "lon"])

    out_df.to_csv(out, index=False)
    print(f"saved {len(out_df)} Ampol/Caltex NSW sites to {out}")
    print(f"  with a Foodary: {int(out_df['has_foodary'].sum())}")
    missing_pc = out_df["postcode"].isna().sum()
    if missing_pc:
        print(f"  note: {missing_pc} sites had no postcode in the address")
    print("\nBrands kept:")
    print(ampol["brand"].value_counts().to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="data/raw/ampol_sites_nsw.csv")
    a = ap.parse_args()
    main(a.db, a.out)
