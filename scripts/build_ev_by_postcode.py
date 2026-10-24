"""Turn EV-registrations-by-LGA into EV counts per NSW postcode.

Input : data/raw/ev_by_lga.csv  (semicolon-separated, from Peclet)
Output: data/raw/ev_by_postcode.csv  (postcode, ev_count, ev_count_prev)
        data/raw/demographics.csv     (postcode, pc_lat, pc_lon,
                                        population, apartment_share)

Method: sum battery-electric registrations per LGA for the latest month and
for ~12 months earlier (for growth), then spread each LGA's total evenly
across the postcodes that sit in it. Even spreading is a documented
simplification: within an LGA we don't know which postcode each EV is in.
"""
from __future__ import annotations

import os
import io
import re
import pandas as pd
import requests

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
POSTCODES_URL = ("https://raw.githubusercontent.com/matthewproctor/"
                 "australianpostcodes/master/australian_postcodes.csv")


def norm_lga(name):
    if not isinstance(name, str):
        return ""
    # "Albury (C)" / "Sydney (A)" -> "ALBURY" / "SYDNEY"
    name = re.sub(r"\(.*?\)", "", name)
    return name.strip().upper()


def main():
    ev = pd.read_csv(os.path.join(RAW, "ev_by_lga.csv"), sep=";")
    ev = ev[ev["motive_power"].str.contains("BATTERY ELECTRIC", case=False, na=False)]
    ev["lga"] = ev["vehicle_garaged_lga"].map(norm_lga)
    ev["date"] = pd.to_datetime(ev["date"])

    latest = ev["date"].max()
    prev = latest - pd.DateOffset(months=12)
    # nearest available month to 12 months ago
    prev = ev["date"][ev["date"] <= prev].max()

    now = ev[ev["date"] == latest].groupby("lga")["count"].sum().rename("ev_count")
    if pd.notna(prev):
        was = ev[ev["date"] == prev].groupby("lga")["count"].sum().rename("ev_count_prev")
    else:
        was = (now * 0.75).rename("ev_count_prev")  # fallback if no history
    lga_ev = pd.concat([now, was], axis=1).fillna(0).reset_index()
    print(f"EV data: latest={latest.date()}, prev={prev.date() if pd.notna(prev) else 'n/a'}, "
          f"{len(lga_ev)} LGAs")

    # NSW postcodes with their LGA
    r = requests.get(POSTCODES_URL, timeout=120)
    r.raise_for_status()
    pc = pd.read_csv(io.StringIO(r.text))
    pc = pc[pc["state"].astype(str).str.upper() == "NSW"].copy()
    pc = pc.dropna(subset=["lat", "long"])
    pc["postcode"] = pc["postcode"].astype(str).str.zfill(4)
    pc["lga"] = pc["lgaregion"].map(norm_lga)
    # one row per postcode (average the centroid over its localities)
    pc = (pc.groupby("postcode")
            .agg(pc_lat=("lat", "mean"), pc_lon=("long", "mean"),
                 lga=("lga", lambda s: s.mode().iat[0] if not s.mode().empty else ""))
            .reset_index())

    # spread each LGA's EV total evenly across its postcodes
    counts_per_lga = pc.groupby("lga")["postcode"].count().rename("n_pc")
    lga_ev = lga_ev.merge(counts_per_lga, on="lga", how="left")
    lga_ev["ev_per_pc"] = lga_ev["ev_count"] / lga_ev["n_pc"].clip(lower=1)
    lga_ev["ev_prev_per_pc"] = lga_ev["ev_count_prev"] / lga_ev["n_pc"].clip(lower=1)

    merged = pc.merge(lga_ev[["lga", "ev_per_pc", "ev_prev_per_pc"]], on="lga", how="left").fillna(0)

    ev_out = pd.DataFrame({
        "postcode": merged["postcode"],
        "ev_count": merged["ev_per_pc"],
        "ev_count_prev": merged["ev_prev_per_pc"],
    })
    ev_out.to_csv(os.path.join(RAW, "ev_by_postcode.csv"), index=False)

    demo = pd.DataFrame({
        "postcode": merged["postcode"],
        "pc_lat": merged["pc_lat"], "pc_lon": merged["pc_lon"],
        "population": 0.0, "apartment_share": 0.0,
    })
    demo.to_csv(os.path.join(RAW, "demographics.csv"), index=False)

    matched = (merged["ev_per_pc"] > 0).sum()
    print(f"wrote ev_by_postcode.csv and demographics.csv for {len(merged)} postcodes")
    print(f"  postcodes matched to EV data: {matched}")
    print(f"  total EVs latest: {int(now.sum()):,}")


if __name__ == "__main__":
    main()
