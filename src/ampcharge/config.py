"""Central settings for the AmpCharge site-selection model.

Everything a reader might want to change lives here: the scoring weights,
the catchment size, and what counts as a "fast" charger. Keeping it in one
place makes the method easy to audit and to re-run with different choices.
"""
from __future__ import annotations

# A charger is "fast" (DC) from this power upward. Slower AC chargers don't
# compete with a highway fast-charging stop, so we count them separately.
FAST_CHARGER_MIN_KW = 50.0

# Catchment size. We prefer a drive-time area, but when the road network
# isn't available we fall back to a straight-line radius of this many km.
CATCHMENT_DRIVE_MINUTES = 10
CATCHMENT_FALLBACK_KM = 5.0

# The four things that make a site a good candidate, and how much each counts.
# They must sum to 1.0. These are a starting point; the sensitivity test
# later shows how much the ranking depends on them.
WEIGHTS = {
    "demand": 0.40,  # EVs nearby, EV growth, apartment share
    "gap": 0.30,     # how under-served the area is by fast chargers
    "traffic": 0.15, # passing traffic on the road outside
    "site": 0.15,    # Foodary, 24/7, highway/main-road location
}

# Within "demand", how the three parts are mixed (must sum to 1.0).
DEMAND_SUBWEIGHTS = {
    "ev_count": 0.50,
    "ev_growth": 0.30,
    "apartment_share": 0.20,
}

# Within "site", how the parts are mixed (must sum to 1.0).
SITE_SUBWEIGHTS = {
    "has_foodary": 0.40,
    "is_24_7": 0.20,
    "on_highway": 0.40,
}

RANDOM_SEED = 42
TOP_N = 20
