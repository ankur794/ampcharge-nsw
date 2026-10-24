"""Prove the engine on a world where we KNOW the right answer.

We build a fake NSW: 200 sites scattered on a grid. We plant 10 "obvious"
sites that have lots of EVs nearby, fast EV growth, no chargers for miles,
heavy traffic and a Foodary. The engine must rank those 10 near the top.

We also plant 10 "AmpCharge already built here" sites in genuinely good spots
and check the backtest flags them as top-ranked. If this passes, the scoring
logic is sound and any later surprise is in the real data, not the code.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ampcharge import build_features, score_sites, backtest, weight_stability



def _make_world(n_sites=200, n_obvious=10, seed=0):
    RNG = np.random.default_rng(seed)  # fresh each call: same world whatever the test order
    # Sites on a lat/lon grid roughly the size of greater Sydney.
    lat = -33.8 + RNG.uniform(-0.6, 0.6, n_sites)
    lon = 151.0 + RNG.uniform(-0.8, 0.8, n_sites)
    site_id = [f"S{i:03d}" for i in range(n_sites)]

    sites = pd.DataFrame({
        "site_id": site_id, "name": site_id, "lat": lat, "lon": lon,
        "postcode": 2000 + np.arange(n_sites),
        "has_foodary": RNG.random(n_sites) < 0.5,
        "is_24_7": RNG.random(n_sites) < 0.3,
        "on_highway": RNG.random(n_sites) < 0.3,
    })

    # Demographics + EVs, one postcode per site, centroid = the site itself
    # so catchments line up simply in this synthetic world.
    demographics = pd.DataFrame({
        "postcode": sites["postcode"],
        "pc_lat": lat, "pc_lon": lon,
        "population": RNG.integers(2000, 20000, n_sites),
        "apartment_share": RNG.uniform(0.05, 0.6, n_sites),
    })
    ev_count = RNG.integers(50, 400, n_sites).astype(float)
    ev = pd.DataFrame({
        "postcode": sites["postcode"],
        "ev_count": ev_count,
        "ev_count_prev": ev_count * RNG.uniform(0.7, 0.95, n_sites),
    })

    # Lots of competitor chargers scattered about.
    n_ch = 300
    chargers = pd.DataFrame({
        "lat": -33.8 + RNG.uniform(-0.6, 0.6, n_ch),
        "lon": 151.0 + RNG.uniform(-0.8, 0.8, n_ch),
        "power_kw": RNG.choice([22, 50, 150, 350], n_ch, p=[0.4, 0.3, 0.2, 0.1]),
        "operator": "Other",
    })

    traffic = pd.DataFrame({
        "site_id": site_id,
        "aadt": RNG.integers(5000, 40000, n_sites),
    })

    # --- Plant 10 obviously-great sites ---
    obvious = list(range(n_obvious))
    sites.loc[obvious, ["has_foodary", "is_24_7", "on_highway"]] = True
    ev.loc[obvious, "ev_count"] = RNG.integers(1500, 3000, n_obvious).astype(float)
    ev.loc[obvious, "ev_count_prev"] = ev.loc[obvious, "ev_count"] * 0.5  # fast growth
    demographics.loc[obvious, "population"] = 40000
    demographics.loc[obvious, "apartment_share"] = 0.8
    traffic.loc[obvious, "aadt"] = 80000
    # Push any charger well away from the obvious sites so their gap is huge.
    for i in obvious:
        d = np.hypot(chargers["lat"] - lat[i], chargers["lon"] - lon[i])
        chargers = chargers[d > 0.2]

    obvious_ids = [site_id[i] for i in obvious]
    return sites, chargers, ev, demographics, traffic, obvious_ids


def test_obvious_sites_rank_top():
    sites, chargers, ev, demo, traffic, obvious_ids = _make_world()
    feats = build_features(sites, chargers, ev, demo, traffic)
    scored = score_sites(feats)
    top10 = set(scored.head(10)["site_id"])
    hits = len(top10 & set(obvious_ids))
    # The 10 planted sites should fill most of the top 10.
    assert hits >= 8, f"only {hits}/10 planted sites in the top 10"


def test_backtest_flags_built_sites():
    sites, chargers, ev, demo, traffic, obvious_ids = _make_world()
    feats = build_features(sites, chargers, ev, demo, traffic)
    # Treat the planted-good sites as the ones AmpCharge "already built".
    result = backtest(feats, built_site_ids=obvious_ids)
    assert result["share_in_top_20pct"] >= 0.8
    assert result["median_percentile"] <= 10


def test_stability_runs_and_ranks():
    sites, chargers, ev, demo, traffic, obvious_ids = _make_world()
    feats = build_features(sites, chargers, ev, demo, traffic)
    stab = weight_stability(feats, n_runs=100).set_index("site_id")["top_n_stability"]
    # The planted sites should stay in the Top 20 under almost any weighting.
    # (Checked directly: many sites can tie at 1.0, so "the first 10 rows"
    # depends on how pandas breaks ties and isn't a fair test.)
    planted = stab.loc[obvious_ids]
    assert (planted >= 0.95).sum() >= 8
    # ...and be clearly more stable than a typical site.
    assert planted.median() > stab.drop(obvious_ids).median()


def test_scores_in_range():
    sites, chargers, ev, demo, traffic, _ = _make_world()
    feats = build_features(sites, chargers, ev, demo, traffic)
    scored = score_sites(feats)
    assert scored["score"].between(0, 100).all()
    assert scored["rank"].is_monotonic_increasing
