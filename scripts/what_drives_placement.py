"""What actually predicts where the planned fast chargers are going?

Unit: every Ampol site in NSW (539). Outcome: is a PLANNED fast charger going
in within 2 km? Then we compare groups of possible drivers:

  demand     : EVs and EV share in the site's LGA
  proximity  : distance to the nearest EXISTING fast charger, how many existing
               fast chargers within 5 km, distance to Sydney CBD
  site       : on a major road, has a Foodary

Each group is scored with a cross-validated AUC (0.5 = coin flip, 1.0 = perfect).
Whichever group scores highest is what the market is really following.

    PYTHONPATH=src python scripts/what_drives_placement.py
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from ampcharge.geo import norm_lga, max_kw, haversine_km

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
FAST_KW = 50.0
NEAR_KM = 2.0
CBD = (-33.8688, 151.2093)


def main():
    ch = pd.read_csv(os.path.join(RAW, "ev_charging_nsw_official.csv"))
    ch = ch.dropna(subset=["Latitude", "Longitude"]).copy()
    ch["kw"] = ch["Charger_rating"].map(max_kw)
    ch["lga"] = ch["LGANAME"].map(norm_lga)
    is_up = ch["Charger_Type"].astype(str).str.contains("upcoming", case=False, na=False)
    existing = ch[~is_up & (ch["kw"] >= FAST_KW)]
    planned = ch[is_up & (ch["kw"] >= FAST_KW)]

    sites = pd.read_csv(os.path.join(RAW, "ampol_sites_nsw.csv"), dtype={"site_id": str})
    el, eo = existing["Latitude"].values, existing["Longitude"].values
    pl, po = planned["Latitude"].values, planned["Longitude"].values

    near_km, n5, plan = [], [], []
    for a, b in zip(sites["lat"], sites["lon"]):
        d = haversine_km(a, b, el, eo)
        near_km.append(d.min())
        n5.append(int((d <= 5).sum()))
        plan.append(bool(haversine_km(a, b, pl, po).min() <= NEAR_KM))
    sites["nearest_existing_km"] = near_km
    sites["log_nearest_existing"] = np.log1p(sites["nearest_existing_km"])
    sites["existing_within_5km"] = n5
    sites["dist_cbd_km"] = haversine_km(sites["lat"], sites["lon"], *CBD)
    sites["log_dist_cbd"] = np.log1p(sites["dist_cbd_km"])
    sites["planned_within_2km"] = plan

    # LGA demand for each site (postcode -> LGA from the official file)
    pc_to_lga = (ch.dropna(subset=["PCODE"])
                   .assign(pc=lambda d: d["PCODE"].astype(str).str.extract(r"(\d{4})")[0])
                   .dropna(subset=["pc"]).query("lga != ''")
                   .groupby("pc")["lga"].agg(lambda s: s.mode().iat[0]).to_dict())
    sites["pc"] = sites["postcode"].astype(str).str.extract(r"(\d{4})")[0]
    sites["lga"] = sites["pc"].map(pc_to_lga).fillna("")
    lga = pd.read_csv(os.path.join(OUT, "lga_validation.csv"))[["lga", "ev_count", "ev_share"]]
    sites = sites.merge(lga, on="lga", how="left")
    sites["has_lga"] = sites["ev_count"].notna()
    sites[["ev_count", "ev_share"]] = sites[["ev_count", "ev_share"]].fillna(
        sites[["ev_count", "ev_share"]].median())
    sites["log_ev_count"] = np.log1p(sites["ev_count"])
    sites["on_highway"] = sites["on_highway"].astype(bool).astype(int)
    sites["has_foodary"] = sites["has_foodary"].astype(bool).astype(int)

    y = sites["planned_within_2km"].astype(int).values
    print(f"Ampol sites: {len(sites)}, with a planned fast charger within 2 km: {y.sum()}")
    print(f"(sites matched to LGA demand data: {int(sites['has_lga'].sum())})")

    groups = {
        "demand (EVs in LGA)": ["log_ev_count", "ev_share"],
        "proximity (existing chargers, CBD)": ["log_nearest_existing", "existing_within_5km", "log_dist_cbd"],
        "site (major road, Foodary)": ["on_highway", "has_foodary"],
        "everything": ["log_ev_count", "ev_share", "log_nearest_existing",
                       "existing_within_5km", "log_dist_cbd", "on_highway", "has_foodary"],
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    print("\n=== Which drivers predict planned charger placement? (cross-validated AUC) ===")
    for name, cols in groups.items():
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        p = cross_val_predict(model, sites[cols].values, y, cv=cv, method="predict_proba")[:, 1]
        print(f"  {name:<36} AUC {roc_auc_score(y, p):.2f}")
    print("  (0.50 = coin flip, 0.70+ = useful, 0.80+ = strong)")

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(sites[groups["everything"]].values, y)
    coefs = pd.Series(model[-1].coef_[0], index=groups["everything"]).sort_values()
    print("\n=== Effect of each driver (standardised; + = more likely to get a planned charger) ===")
    print(coefs.round(2).to_string())

    print("\n=== Plain-English check: hit rate by distance to nearest EXISTING fast charger ===")
    bins = [0, 1, 3, 10, 1e9]
    labels = ["< 1 km", "1-3 km", "3-10 km", "> 10 km"]
    sites["band"] = pd.cut(sites["nearest_existing_km"], bins=bins, labels=labels, right=False)
    tab = sites.groupby("band", observed=False)["planned_within_2km"].agg(["sum", "count"])
    tab["rate"] = (tab["sum"] / tab["count"]).map(lambda r: f"{r:.0%}" if pd.notna(r) else "-")
    tab.columns = ["planned nearby", "Ampol sites", "rate"]
    print(tab.to_string())

    sites.to_csv(os.path.join(OUT, "placement_drivers_sites.csv"), index=False)
    print("\nSaved outputs/placement_drivers_sites.csv")


if __name__ == "__main__":
    main()
