"""Tests for the shared helpers, using the real edge cases found in the data."""
from __future__ import annotations

import pandas as pd
import pytest

from ampcharge.geo import (BORDER_LGAS, dedupe_sites, haversine_km, max_kw,
                           norm_lga, norm_postcode)


# ---- LGA names: the two NSW sources spell them differently ----
@pytest.mark.parametrize("a, b", [
    ("Canada Bay Council, City of", "Canada Bay"),
    ("Canterbury Bankstown Council", "Canterbury-Bankstown"),
    ("Armidale Regional Council", "Armidale Regional"),
    ("Albury City Council", "Albury"),
    ("The Hills Shire Council", "The Hills Shire"),
    ("Queanbeyan-Palerang Regional Council", "Queanbeyan-Palerang Regional"),
])
def test_lga_names_from_both_sources_match(a, b):
    assert norm_lga(a) == norm_lga(b)
    assert norm_lga(a) != ""


def test_lga_name_handles_missing():
    assert norm_lga(None) == ""
    assert norm_lga(float("nan")) == ""


def test_border_lgas_are_in_normalised_form():
    assert norm_lga("Queanbeyan-Palerang Regional Council") in BORDER_LGAS
    assert norm_lga("Tweed Shire Council") in BORDER_LGAS
    assert norm_lga("Lake Macquarie City Council") not in BORDER_LGAS


# ---- charger ratings ----
@pytest.mark.parametrize("rating, expected", [
    ("2x350kW & 2x175kW", 350.0),
    ("50kW", 50.0),
    ("22 kW", 22.0),
    ("1x7.4kW", 7.4),
    ("", 0.0),
    (None, 0.0),
])
def test_max_kw(rating, expected):
    assert max_kw(rating) == pytest.approx(expected)


# ---- postcodes ----
@pytest.mark.parametrize("raw, expected", [
    (2153, "2153"), ("2153", "2153"), (2153.0, "2153"), (" 2153 ", "2153"),
    (800, "0800"), (None, None), ("abc", None),
])
def test_norm_postcode(raw, expected):
    assert norm_postcode(raw) == expected


# ---- distance ----
def test_haversine_sydney_to_melbourne():
    d = haversine_km(-33.8688, 151.2093, -37.8136, 144.9631)
    assert 700 < d < 730          # about 713 km

def test_haversine_same_point_is_zero():
    assert haversine_km(-33.8, 151.0, -33.8, 151.0) == pytest.approx(0.0)


# ---- de-duplicating FuelCheck entries ----
def _sites(rows):
    return pd.DataFrame(rows, columns=["site_id", "name", "lat", "lon", "has_foodary"])


def test_petrol_and_diesel_entries_merge_into_one_site():
    s = _sites([
        ("1", "Ampol Foodary Wyong M1 Northbound Petrol", -33.2800, 151.4200, True),
        ("2", "Ampol Foodary Wyong M1 Northbound Diesel", -33.2830, 151.4210, True),  # ~350 m
        ("3", "Ampol Foodary Wyong M1 Southbound Petrol", -33.2850, 151.4150, True),
        ("4", "Ampol Foodary Wyong M1 Southbound Diesel", -33.2880, 151.4160, True),
    ])
    out = dedupe_sites(s)
    assert len(out) == 2   # one northbound, one southbound


def test_entries_within_100m_merge_and_foodary_is_kept():
    s = _sites([
        ("1", "EG Ampol Somewhere", -33.80000, 151.00000, False),
        ("2", "Ampol Foodary Somewhere", -33.80050, 151.00000, True),   # ~55 m
    ])
    out = dedupe_sites(s)
    assert len(out) == 1
    assert out.iloc[0]["site_id"] == "2"


def test_different_sites_are_left_alone():
    s = _sites([
        ("1", "Ampol Toronto", -33.01, 151.59, True),
        ("2", "Ampol Morisset", -33.11, 151.49, False),   # ~14 km away
        ("3", "Ampol Belmont", -33.03, 151.66, False),
    ])
    assert len(dedupe_sites(s)) == 3


def test_same_name_far_apart_is_not_merged():
    s = _sites([
        ("1", "Ampol Diesel Stop", -33.0, 151.0, False),
        ("2", "Ampol Diesel Stop", -34.0, 150.0, False),   # ~140 km apart
    ])
    assert len(dedupe_sites(s)) == 2
