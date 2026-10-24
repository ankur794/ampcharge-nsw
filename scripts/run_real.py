"""Run the model on your REAL NSW data.

Works in two modes depending on what data you've downloaded:

  * sites + chargers only  -> scores on GAP (charger shortage) + SITE quality
  * + EV + demographics    -> adds DEMAND (full model)

    PYTHONPATH=src python scripts/run_real.py

Reads data/raw/ampol_sites_nsw.csv and data/raw/chargers_nsw.csv (required),
and data/raw/ev_by_postcode.csv + data/raw/demographics.csv (optional).
Writes outputs/top20.csv and outputs/all_sites_scored.csv .
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ampcharge.features import haversine_km, count_fast_chargers_near, build_features
from ampcharge import score_sites, backtest
from ampcharge.config import FAST_CHARGER_MIN_KW, CATCHMENT_FALLBACK_KM

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT, exist_ok=True)


def find_built_ampcharge_sites(sites, chargers, radius_km=0.5):
    """Which Ampol sites already have an AmpCharge charger on them?

    Match AmpCharge chargers to the nearest Ampol site within radius_km.
    These become the 'already built' sites the backtest checks.
    """
    amp = chargers[chargers["operator"].str.contains("ampcharge", case=False, na=False)]
    built = set()
    for _, c in amp.iterrows():
        d = haversine_km(c["lat"], c["lon"], sites["lat"].values, sites["lon"].values)
        j = int(np.argmin(d))
        if d[j] <= radius_km:
            built.add(sites.iloc[j]["site_id"])
    return built


def main():
    sites = pd.read_csv(os.path.join(RAW, "ampol_sites_nsw.csv"), dtype={"site_id": str})
    chargers = pd.read_csv(os.path.join(RAW, "chargers_nsw.csv"))
    chargers = chargers.dropna(subset=["lat", "lon"])
    chargers["power_kw"] = pd.to_numeric(chargers["power_kw"], errors="coerce").fillna(0)

    built = find_built_ampcharge_sites(sites, chargers)
    print(f"{len(sites)} Ampol sites, {len(chargers)} chargers "
          f"({int((chargers['power_kw']>=FAST_CHARGER_MIN_KW).sum())} fast)")
    print(f"Ampol sites that already have AmpCharge: {len(built)}")

    # For a fair backtest, judge the gap as it was BEFORE AmpCharge was built:
    # exclude AmpCharge's own chargers from the competitor supply.
    competitors = chargers[~chargers["operator"].str.contains("ampcharge", case=False, na=False)]

    ev_path = os.path.join(RAW, "ev_by_postcode.csv")
    demo_path = os.path.join(RAW, "demographics.csv")
    full = os.path.exists(ev_path) and os.path.exists(demo_path)

    if full:
        print("Mode: FULL (demand + gap + traffic + site)")
        ev = pd.read_csv(ev_path)
        demo = pd.read_csv(demo_path)
        feats = build_features(sites, competitors, ev, demo)
        scored = score_sites(feats)
    else:
        print("Mode: GAP + SITE only (add ev_by_postcode.csv + demographics.csv for full demand)")
        feats = _gap_site_features(sites, competitors)
        scored = _score_gap_site(feats)

    scored.to_csv(os.path.join(OUT, "all_sites_scored.csv"), index=False)
    top20 = scored.head(20)
    cols = [c for c in ["rank", "site_id", "name", "score", "fast_chargers_nearby",
                        "nearest_fast_km", "has_foodary", "on_highway"] if c in scored.columns]
    top20[cols].to_csv(os.path.join(OUT, "top20.csv"), index=False)

    print("\n=== TOP 20 CANDIDATE AMPOL SITES (real NSW data) ===")
    print(top20[cols].to_string(index=False))

    if built:
        bt = backtest(feats, built) if full else _backtest_gap_site(feats, built)
        print("\n=== BACKTEST: where do the 9 real AmpCharge sites rank? ===")
        for k, v in bt.items():
            print(f"  {k}: {v}")


# --- lightweight gap+site path (no EV/census needed) ---
def _gap_site_features(sites, chargers):
    rows = []
    for _, s in sites.iterrows():
        n, kw, nearest = count_fast_chargers_near(s, chargers, CATCHMENT_FALLBACK_KM)
        rows.append({
            "site_id": s["site_id"], "name": s.get("name", ""),
            "lat": s["lat"], "lon": s["lon"],
            "fast_chargers_nearby": n, "fast_kw_nearby": kw,
            "nearest_fast_km": nearest,
            "has_foodary": bool(s.get("has_foodary", False)),
            "is_24_7": bool(s.get("is_24_7", False)),
            "on_highway": bool(s.get("on_highway", False)),
        })
    return pd.DataFrame(rows)


def _minmax(s):
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi > lo else pd.Series(np.zeros(len(s)), index=s.index)


def _score_gap_site(f):
    f = f.copy()
    supply = _minmax(f["fast_kw_nearby"])
    nearest = f["nearest_fast_km"].replace(np.inf, f["nearest_fast_km"].replace(np.inf, np.nan).max() if
                                           f["nearest_fast_km"].replace(np.inf, np.nan).notna().any() else 50.0)
    gap = (1 - supply) * 0.6 + _minmax(nearest) * 0.4
    site = (f["has_foodary"].astype(float) * 0.4 + f["is_24_7"].astype(float) * 0.2
            + f["on_highway"].astype(float) * 0.4)
    # Without demand/traffic, weight gap 0.65 / site 0.35.
    f["gap_score"] = gap
    f["site_score"] = site
    f["score"] = 100 * (gap * 0.65 + site * 0.35)
    f = f.sort_values("score", ascending=False).reset_index(drop=True)
    f["rank"] = np.arange(1, len(f) + 1)
    return f


def _backtest_gap_site(f, built):
    scored = _score_gap_site(f)
    n = len(scored)
    b = scored[scored["site_id"].isin(built)]
    ranks = b["rank"].tolist()
    if not ranks:
        return {"n_built": 0, "note": "built sites not matched"}
    pct = [100 * r / n for r in ranks]
    return {
        "n_sites": n, "n_built": len(ranks),
        "built_ranks": sorted(ranks),
        "built_percentiles": [round(p, 1) for p in sorted(pct)],
        "median_percentile": round(float(np.median(pct)), 1),
        "share_in_top_20pct": round(sum(1 for p in pct if p <= 20) / len(ranks), 2),
        "expected_by_chance": 0.20,
    }


if __name__ == "__main__":
    main()
