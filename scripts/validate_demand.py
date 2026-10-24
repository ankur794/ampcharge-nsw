"""Validation with the OFFICIAL NSW Government charger dataset.

data/raw/ev_charging_nsw_official.csv has ~3,400 charger stations with the
LGA name and postcode already attached, and a charger rating we can read kW
from. Far more complete than the crowdsourced data, and no guessing which
LGA a charger is in.

Test: does EV demand predict where chargers were actually built (R^2, held
out)? Then find Ampol sites in under-served LGAs with no fast charger nearby.

Outputs: outputs/lga_validation.csv, outputs/opportunity_sites.csv
"""
from __future__ import annotations

import os
import re
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.metrics import r2_score

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT, exist_ok=True)
FAST_KW = 50.0


def norm_lga(name):
    """Normalise LGA names so the two sources match.

    'Canada Bay Council, City of' and 'Canada Bay' both -> 'CANADA BAY'.
    Strips council-type words, punctuation and hyphens from both sides.
    """
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace(",", " ").replace("-", " ")
    s = re.sub(r"\b(COUNCIL|CITY|SHIRE|REGIONAL|MUNICIPAL|OF|THE)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def max_kw(rating):
    """'2x350kW & 2x175kW' -> 350.0 ; blank -> 0."""
    if not isinstance(rating, str):
        return 0.0
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*kW", rating, flags=re.I)
    return max((float(n) for n in nums), default=0.0)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def main():
    ch = pd.read_csv(os.path.join(RAW, "ev_charging_nsw_official.csv"))
    print("Charger_Type values:")
    print(ch["Charger_Type"].value_counts(dropna=False).to_string())

    ch["kw"] = ch["Charger_rating"].map(max_kw)
    ch["lga"] = ch["LGANAME"].map(norm_lga)
    ch = ch.dropna(subset=["Latitude", "Longitude"])
    # "existing" = anything not flagged Upcoming/Planned
    existing = ~ch["Charger_Type"].astype(str).str.contains("upcoming|planned", case=False, na=False)
    fast = ch[existing & (ch["kw"] >= FAST_KW) & (ch["lga"] != "")].copy()
    print(f"\n{len(ch)} charger records, {len(fast)} existing fast (>=50kW) with an LGA")

    charger_counts = fast.groupby("lga").size().rename("fast_chargers").reset_index()

    # EVs per LGA (latest month)
    ev = pd.read_csv(os.path.join(RAW, "ev_by_lga.csv"), sep=";")
    ev = ev[ev["motive_power"].str.contains("BATTERY ELECTRIC", case=False, na=False)]
    ev["lga"] = ev["vehicle_garaged_lga"].map(norm_lga)
    ev["date"] = pd.to_datetime(ev["date"])
    latest = ev[ev["date"] == ev["date"].max()]
    lga = (latest.groupby("lga")
                 .agg(ev_count=("count", "sum"), total_vehicles=("total_vehicles", "max"))
                 .reset_index())
    lga["ev_share"] = lga["ev_count"] / lga["total_vehicles"].clip(lower=1)

    t = lga.merge(charger_counts, on="lga", how="left")
    t["fast_chargers"] = t["fast_chargers"].fillna(0)
    t = t[t["ev_count"] > 0].reset_index(drop=True)

    # VALIDATION
    X = t[["ev_count", "ev_share"]].values
    y = t["fast_chargers"].values
    model = LinearRegression()
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    y_cv = cross_val_predict(model, X, y, cv=kf)
    r2_cv = r2_score(y, y_cv)
    corr = np.corrcoef(t["ev_count"], t["fast_chargers"])[0, 1]

    print("\n=== VALIDATION: does EV demand predict industry charger placement? ===")
    print(f"  LGAs analysed: {len(t)}")
    print(f"  existing fast chargers: {int(y.sum())}")
    print(f"  correlation (EV count vs chargers): {corr:.3f}")
    print(f"  cross-validated R^2 (held-out): {r2_cv:.3f}")

    model.fit(X, y)
    t["predicted_chargers"] = model.predict(X)
    t["gap"] = t["predicted_chargers"] - t["fast_chargers"]
    t = t.sort_values("gap", ascending=False).reset_index(drop=True)
    t.to_csv(os.path.join(OUT, "lga_validation.csv"), index=False)

    print("\n=== MOST UNDER-SERVED LGAs (more EV demand than chargers) ===")
    show = t.head(12)[["lga", "ev_count", "ev_share", "fast_chargers",
                       "predicted_chargers", "gap"]].copy()
    show["ev_share"] = (show["ev_share"] * 100).round(2).astype(str) + "%"
    show[["predicted_chargers", "gap"]] = show[["predicted_chargers", "gap"]].round(1)
    print(show.to_string(index=False))

    # Ampol opportunity sites. Map each site to its LGA via the official
    # file's PCODE -> LGANAME lookup (the most reliable postcode->LGA we have).
    sites = pd.read_csv(os.path.join(RAW, "ampol_sites_nsw.csv"), dtype={"site_id": str})
    pc_to_lga = (ch.dropna(subset=["PCODE"])
                   .assign(pc=lambda d: d["PCODE"].astype(str).str.extract(r"(\d{4})")[0])
                   .dropna(subset=["pc"])
                   .groupby("pc")["lga"]
                   .agg(lambda s: s.mode().iat[0] if not s.mode().empty else ""))
    pc_to_lga = pc_to_lga.to_dict()

    sites["pc"] = sites["postcode"].astype(str).str.extract(r"(\d{4})")[0]
    sites["lga"] = sites["pc"].map(pc_to_lga).fillna("")
    # nearest existing fast charger distance
    near = []
    fl, fo = fast["Latitude"].values, fast["Longitude"].values
    for _, s in sites.iterrows():
        d = haversine_km(s["lat"], s["lon"], fl, fo)
        near.append(float(d.min()) if len(fast) else np.inf)
    sites["nearest_fast_km"] = near

    sites = sites.merge(t[["lga", "gap", "ev_count", "ev_share"]], on="lga", how="left")
    opp = sites[(sites["gap"] > 0) & (sites["nearest_fast_km"] > 2.0)].copy()
    opp = opp.sort_values(["gap", "ev_count"], ascending=False)
    keep = ["site_id", "name", "lga", "ev_count", "gap", "nearest_fast_km",
            "has_foodary", "on_highway"]
    opp[keep].to_csv(os.path.join(OUT, "opportunity_sites.csv"), index=False)

    print("\n=== TOP AMPOL OPPORTUNITY SITES (under-served LGA, no fast charger <2km) ===")
    print(opp.head(20)[keep].to_string(index=False))
    print("\nSaved outputs/lga_validation.csv and outputs/opportunity_sites.csv")


if __name__ == "__main__":
    main()
