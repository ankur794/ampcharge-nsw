"""Forward test: are the planned ("Upcoming") chargers going where the model points?

The model's demand gaps were built ONLY from chargers that already exist.
The official NSW file also lists chargers that are planned but not built yet.
If those planned chargers land in the LGAs the model calls under-served, more
than you'd expect from EV numbers alone, the model is picking up something real.

    PYTHONPATH=src python scripts/backtest_upcoming.py

Needs: outputs/lga_validation.csv and outputs/opportunity_sites.csv
(run validate_demand.py first), plus the raw data files.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
from ampcharge.geo import norm_lga, max_kw, haversine_km

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
FAST_KW = 50.0
NEAR_KM = 2.0


def main():
    ch = pd.read_csv(os.path.join(RAW, "ev_charging_nsw_official.csv"))
    ch = ch.dropna(subset=["Latitude", "Longitude"]).copy()
    ch["kw"] = ch["Charger_rating"].map(max_kw)
    ch["lga"] = ch["LGANAME"].map(norm_lga)
    is_up = ch["Charger_Type"].astype(str).str.contains("upcoming", case=False, na=False)

    known = ch[~is_up & (ch["lga"] != "")]
    up = ch[is_up & (ch["kw"] >= FAST_KW)].copy()
    print(f"Planned fast chargers in the file: {len(up)}")
    print("Who is building them:")
    print(up["Operator"].value_counts().head(8).to_string())

    # upcoming rows have no LGA, so take the LGA of the nearest known charger
    kl, ko, kg = known["Latitude"].values, known["Longitude"].values, known["lga"].values
    up["lga"] = [l if l else kg[int(np.argmin(haversine_km(a, b, kl, ko)))]
                 for l, a, b in zip(up["lga"], up["Latitude"], up["Longitude"])]

    # ---------- LGA-level test ----------
    t = pd.read_csv(os.path.join(OUT, "lga_validation.csv"))
    t = t.merge(up.groupby("lga").size().rename("upcoming").reset_index(), on="lga", how="left")
    t["upcoming"] = t["upcoming"].fillna(0)
    total_up = t["upcoming"].sum()

    under = t["gap"] > 0
    share_up = t.loc[under, "upcoming"].sum() / max(total_up, 1)
    share_ev = t.loc[under, "ev_count"].sum() / t["ev_count"].sum()
    rank_corr = t["gap"].rank().corr(t["upcoming"].rank())

    top = t.sort_values("gap", ascending=False).head(15)
    top_share_up = top["upcoming"].sum() / max(total_up, 1)
    top_share_ev = top["ev_count"].sum() / t["ev_count"].sum()

    print("\n=== FORWARD TEST (LGA level) ===")
    print(f"  planned fast chargers matched to an LGA: {int(total_up)}")
    print(f"  share going to under-served LGAs (gap > 0): {share_up:.0%}")
    print(f"  share you'd expect from EV numbers alone:    {share_ev:.0%}")
    print(f"  share going to the 15 most under-served:     {top_share_up:.0%}"
          f"  (EV-only expectation {top_share_ev:.0%})")
    print(f"  rank correlation, gap vs planned chargers:   {rank_corr:.2f}")
    print("  -> if the planned share beats the EV-only expectation, the model")
    print("     is spotting gaps the industry is now moving to fill.")

    # ---------- Site-level test ----------
    sites = pd.read_csv(os.path.join(RAW, "ampol_sites_nsw.csv"), dtype={"site_id": str})
    opp = pd.read_csv(os.path.join(OUT, "opportunity_sites.csv"), dtype={"site_id": str})
    ul, uo = up["Latitude"].values, up["Longitude"].values
    sites["planned_within_2km"] = [
        bool(len(ul)) and haversine_km(a, b, ul, uo).min() <= NEAR_KM
        for a, b in zip(sites["lat"], sites["lon"])]

    top_ids = set(opp.head(25)["site_id"])
    all_ids = set(opp["site_id"])
    groups = {
        "Top 25 opportunity sites": sites["site_id"].isin(top_ids),
        "All opportunity sites": sites["site_id"].isin(all_ids),
        "Every other Ampol site": ~sites["site_id"].isin(all_ids),
    }
    print("\n=== FORWARD TEST (site level): planned fast charger within 2 km ===")
    for label, mask in groups.items():
        g = sites[mask]
        hits = int(g["planned_within_2km"].sum())
        rate = hits / len(g) if len(g) else 0
        print(f"  {label:<26} {hits:>3} of {len(g):<4} ({rate:.0%})")

    t.to_csv(os.path.join(OUT, "upcoming_test_lga.csv"), index=False)
    sites.to_csv(os.path.join(OUT, "upcoming_test_sites.csv"), index=False)
    print("\nSaved outputs/upcoming_test_lga.csv and outputs/upcoming_test_sites.csv")


if __name__ == "__main__":
    main()
