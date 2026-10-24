"""Score every site, then prove the score works.

Three public functions:
  score_sites      : raw features  -> a score per site (0-100) and rank
  backtest         : do real AmpCharge sites land near the top? (the key test)
  weight_stability : how often does each site stay in the Top 20 when the
                     weights are jiggled? (the honesty test)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (WEIGHTS, DEMAND_SUBWEIGHTS, SITE_SUBWEIGHTS,
                     RANDOM_SEED, TOP_N)


def _minmax(s: pd.Series) -> pd.Series:
    """Scale a column to 0-1. A flat column becomes all zeros (no signal)."""
    lo, hi = s.min(), s.max()
    if hi - lo == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def score_sites(feats: pd.DataFrame, weights=None) -> pd.DataFrame:
    """Return feats plus demand/gap/traffic/site sub-scores, a 0-100 score and rank."""
    w = {**WEIGHTS, **(weights or {})}
    f = feats.copy()

    # --- Demand: more EVs, faster growth, more apartments = higher ---
    demand = (
        _minmax(f["ev_count"]) * DEMAND_SUBWEIGHTS["ev_count"]
        + _minmax(f["ev_growth"]) * DEMAND_SUBWEIGHTS["ev_growth"]
        + _minmax(f["apartment_share"]) * DEMAND_SUBWEIGHTS["apartment_share"]
    )

    # --- Gap: fewer fast chargers nearby + further to the nearest = higher ---
    # Invert supply so that "less supply" scores high.
    supply = _minmax(f["fast_kw_nearby"])
    # nearest_fast_km can be inf (no fast charger at all) -> cap for scaling.
    nearest = f["nearest_fast_km"].replace(np.inf, f["nearest_fast_km"].replace(np.inf, np.nan).max() * 1.5
                                           if f["nearest_fast_km"].replace(np.inf, np.nan).notna().any() else 50.0)
    gap = (1 - supply) * 0.6 + _minmax(nearest) * 0.4

    # --- Traffic: more cars past the door = higher ---
    traffic = _minmax(f["aadt"])

    # --- Site quality: Foodary, 24/7, on a highway ---
    site = (
        f["has_foodary"].astype(float) * SITE_SUBWEIGHTS["has_foodary"]
        + f["is_24_7"].astype(float) * SITE_SUBWEIGHTS["is_24_7"]
        + f["on_highway"].astype(float) * SITE_SUBWEIGHTS["on_highway"]
    )

    f["demand_score"] = demand
    f["gap_score"] = gap
    f["traffic_score"] = traffic
    f["site_score"] = site

    f["score"] = 100 * (
        demand * w["demand"] + gap * w["gap"]
        + traffic * w["traffic"] + site * w["site"]
    )
    f = f.sort_values("score", ascending=False).reset_index(drop=True)
    f["rank"] = np.arange(1, len(f) + 1)
    return f


def backtest(feats: pd.DataFrame, built_site_ids, weights=None) -> dict:
    """Score sites, then see where the already-built AmpCharge sites land.

    If the model is any good, Ampol's own choices should sit near the top.
    Returns summary stats plus the ranks of the built sites.
    """
    scored = score_sites(feats, weights)
    n = len(scored)
    built = scored[scored["site_id"].isin(built_site_ids)]
    ranks = built["rank"].tolist()
    if not ranks:
        return {"n_sites": n, "n_built": 0, "note": "no built sites found in data"}

    # Percentile: rank 1 of 300 -> 0.3rd percentile (very top).
    pct = [100 * r / n for r in ranks]
    # How many built sites fall in the top 20%?
    top20pct = sum(1 for p in pct if p <= 20)
    # Compare to chance: if the model were random, we'd expect 20% of them.
    return {
        "n_sites": n,
        "n_built": len(ranks),
        "built_ranks": sorted(ranks),
        "built_percentiles": [round(p, 1) for p in sorted(pct)],
        "median_percentile": round(float(np.median(pct)), 1),
        "share_in_top_20pct": round(top20pct / len(ranks), 2),
        "expected_by_chance": 0.20,
    }


def weight_stability(feats: pd.DataFrame, n_runs=500, jitter=0.5,
                     seed=RANDOM_SEED, top_n=TOP_N) -> pd.DataFrame:
    """Jiggle the weights n_runs times; count how often each site stays Top-N.

    A site that stays in the Top 20 under almost any weighting is a solid
    pick. One that drops out easily depends on our assumptions and should be
    labelled a "maybe". This is what stops the ranking being a single
    opinion dressed up as a result.
    """
    rng = np.random.default_rng(seed)
    base = np.array([WEIGHTS[k] for k in ("demand", "gap", "traffic", "site")])
    counts = pd.Series(0, index=feats["site_id"])

    for _ in range(n_runs):
        # Multiply each weight by a random factor, then renormalise to sum 1.
        factors = 1 + rng.uniform(-jitter, jitter, size=4)
        w = base * factors
        w = w / w.sum()
        wd = dict(zip(("demand", "gap", "traffic", "site"), w))
        scored = score_sites(feats, wd)
        top = scored.head(top_n)["site_id"]
        counts.loc[top] += 1

    out = (counts / n_runs).rename("top_n_stability").reset_index()
    return out.sort_values("top_n_stability", ascending=False).reset_index(drop=True)
