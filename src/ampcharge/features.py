"""Turn raw data into one row of features per Ampol site.

Inputs (all pandas DataFrames):
  sites       : Ampol sites.  columns: site_id, name, lat, lon, postcode,
                has_foodary (bool), is_24_7 (bool), on_highway (bool)
  chargers    : public EV chargers.  columns: lat, lon, power_kw, operator
  ev          : EVs by postcode.  columns: postcode, ev_count, ev_count_prev
  demographics: by postcode.  columns: postcode, population, apartment_share
  traffic     : optional.  columns: site_id, aadt  (avg daily traffic)

Output: one DataFrame, one row per site, with raw feature columns.
Normalising to 0-1 happens later in scoring.py, so the raw numbers stay
readable and checkable here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FAST_CHARGER_MIN_KW, CATCHMENT_FALLBACK_KM

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Accepts scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def count_fast_chargers_near(site, chargers, radius_km=CATCHMENT_FALLBACK_KM):
    """How many fast chargers, and total kW, sit within radius_km of a site."""
    if chargers.empty:
        return 0, 0.0, np.inf
    d = haversine_km(site["lat"], site["lon"], chargers["lat"].values, chargers["lon"].values)
    fast = chargers["power_kw"].values >= FAST_CHARGER_MIN_KW
    within = (d <= radius_km) & fast
    n = int(within.sum())
    total_kw = float(chargers["power_kw"].values[within].sum())
    nearest = float(d[fast].min()) if fast.any() else np.inf
    return n, total_kw, nearest


def postcodes_within(site, demographics, radius_km=CATCHMENT_FALLBACK_KM):
    """Postcodes whose centroid falls inside the catchment.

    demographics must carry postcode centroid lat/lon as pc_lat, pc_lon.
    """
    d = haversine_km(site["lat"], site["lon"],
                     demographics["pc_lat"].values, demographics["pc_lon"].values)
    return demographics[d <= radius_km]


def build_features(sites, chargers, ev, demographics, traffic=None,
                   radius_km=CATCHMENT_FALLBACK_KM):
    """Assemble the per-site feature table. Pure function, no I/O."""
    ev_by_pc = ev.set_index("postcode")
    demo = demographics.copy()
    demo = demo.merge(ev, on="postcode", how="left")
    demo[["ev_count", "ev_count_prev"]] = demo[["ev_count", "ev_count_prev"]].fillna(0)

    rows = []
    for _, site in sites.iterrows():
        catch = postcodes_within(site, demo, radius_km)
        ev_count = float(catch["ev_count"].sum())
        ev_prev = float(catch["ev_count_prev"].sum())
        ev_growth = (ev_count - ev_prev) / ev_prev if ev_prev > 0 else 0.0

        pop = float(catch["population"].sum())
        if pop > 0:
            apt_share = float((catch["apartment_share"] * catch["population"]).sum() / pop)
        else:
            apt_share = 0.0

        n_fast, fast_kw, nearest = count_fast_chargers_near(site, chargers, radius_km)

        rows.append({
            "site_id": site["site_id"],
            "name": site.get("name", ""),
            "lat": site["lat"], "lon": site["lon"],
            "ev_count": ev_count,
            "ev_growth": ev_growth,
            "apartment_share": apt_share,
            "fast_chargers_nearby": n_fast,
            "fast_kw_nearby": fast_kw,
            "nearest_fast_km": nearest,
            "has_foodary": bool(site.get("has_foodary", False)),
            "is_24_7": bool(site.get("is_24_7", False)),
            "on_highway": bool(site.get("on_highway", False)),
        })

    feats = pd.DataFrame(rows)

    if traffic is not None and not traffic.empty:
        feats = feats.merge(traffic[["site_id", "aadt"]], on="site_id", how="left")
    else:
        feats["aadt"] = np.nan
    # Missing traffic: fill with the median so a site isn't punished for a
    # data gap. Flagged so the limitation is visible.
    feats["aadt_imputed"] = feats["aadt"].isna()
    feats["aadt"] = feats["aadt"].fillna(feats["aadt"].median() if feats["aadt"].notna().any() else 0.0)

    return feats
