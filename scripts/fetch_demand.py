"""Download NSW postcode centres + population, for the demand catchments.

Uses the well-maintained open Australian-postcodes dataset (postcode, state,
lat, lon, and population where available). Run on your machine:

    python scripts/fetch_demand.py

Writes data/raw/demographics.csv with:
    postcode, pc_lat, pc_lon, population, apartment_share

apartment_share is left at 0 for now (needs an ABS Census download); the
model runs fine without it and we can add it later. EV counts come from a
separate file (see fetch/README).
"""
from __future__ import annotations

import os
import io
import pandas as pd
import requests

URL = ("https://raw.githubusercontent.com/matthewproctor/"
       "australianpostcodes/master/australian_postcodes.csv")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "demographics.csv")


def main():
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    # Column names vary a little between versions; find them flexibly.
    cols = {c.lower(): c for c in df.columns}
    pc = cols.get("postcode")
    lat = cols.get("lat") or cols.get("latitude")
    lon = cols.get("long") or cols.get("lng") or cols.get("longitude")
    state = cols.get("state")
    pop = cols.get("population") or cols.get("2021_population") or cols.get("estimated_population")

    nsw = df[df[state].astype(str).str.upper() == "NSW"].copy()
    nsw = nsw.dropna(subset=[lat, lon])

    out = pd.DataFrame({
        "postcode": nsw[pc].astype(str).str.zfill(4),
        "pc_lat": pd.to_numeric(nsw[lat], errors="coerce"),
        "pc_lon": pd.to_numeric(nsw[lon], errors="coerce"),
    })
    if pop:
        out["population"] = pd.to_numeric(nsw[pop], errors="coerce").fillna(0)
    else:
        out["population"] = 0
    out["apartment_share"] = 0.0

    # One row per postcode (several localities can share a postcode -> average).
    out = (out.groupby("postcode", as_index=False)
              .agg({"pc_lat": "mean", "pc_lon": "mean",
                    "population": "sum", "apartment_share": "mean"}))
    out = out.dropna(subset=["pc_lat", "pc_lon"])
    out.to_csv(OUT, index=False)
    print(f"saved {len(out)} NSW postcodes to {OUT}")
    print(f"  population column present: {bool(pop)} "
          f"(total pop {int(out['population'].sum()):,})")
    print(out.head().to_string(index=False))


if __name__ == "__main__":
    main()
