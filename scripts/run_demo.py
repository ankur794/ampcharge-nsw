"""End-to-end demo on synthetic data, so you can see the output shape now.

    PYTHONPATH=src python scripts/run_demo.py

Swap the synthetic world for the real CSVs (see README) and this same
script produces your real Top 20.
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
from test_synthetic import _make_world  # reuse the synthetic world
from ampcharge import build_features, score_sites, backtest, weight_stability

pd.set_option("display.width", 120)

sites, chargers, ev, demo, traffic, built_ids = _make_world()
feats = build_features(sites, chargers, ev, demo, traffic)
scored = score_sites(feats)

print("=== TOP 10 CANDIDATE SITES (synthetic) ===")
cols = ["rank", "site_id", "score", "ev_count", "ev_growth",
        "fast_chargers_nearby", "has_foodary"]
print(scored.head(10)[cols].to_string(index=False))

print("\n=== BACKTEST (do real AmpCharge sites rank top?) ===")
bt = backtest(feats, built_ids)
for k, v in bt.items():
    print(f"  {k}: {v}")

print("\n=== WEIGHT STABILITY (top 10 most robust picks) ===")
stab = weight_stability(feats, n_runs=300)
print(stab.head(10).to_string(index=False))
