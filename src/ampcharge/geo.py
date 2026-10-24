"""Shared helpers used across the analysis scripts.

Kept in one place so every script cleans names, parses ratings and measures
distance the same way.
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
SYDNEY_CBD = (-33.8688, 151.2093)

# LGAs on the ACT / QLD / VIC / SA border. The NSW charger register doesn't
# include chargers across the state line, so these areas can look
# under-served when drivers actually use chargers a few minutes away.
BORDER_LGAS = frozenset({
    "QUEANBEYAN PALERANG", "YASS VALLEY", "SNOWY MONARO",            # ACT
    "TWEED", "KYOGLE", "TENTERFIELD", "MOREE PLAINS", "GWYDIR",       # QLD
    "WALGETT", "BREWARRINA", "BOURKE", "INVERELL",
    "ALBURY", "GREATER HUME", "FEDERATION", "BERRIGAN",               # VIC
    "MURRAY RIVER", "EDWARD RIVER", "BALRANALD", "WENTWORTH",
    "SNOWY VALLEYS", "BEGA VALLEY",
    "BROKEN HILL", "UNINCORPORATED NSW",                               # SA / far west
})


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Works on scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def norm_lga(name) -> str:
    """Normalise an LGA name so different sources match.

    'Canada Bay Council, City of', 'Canada Bay' -> 'CANADA BAY'
    'Canterbury-Bankstown', 'Canterbury Bankstown Council' -> 'CANTERBURY BANKSTOWN'
    """
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace(",", " ").replace("-", " ")
    s = re.sub(r"\b(COUNCIL|CITY|SHIRE|REGIONAL|MUNICIPAL|OF|THE)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def max_kw(rating) -> float:
    """Highest power in a charger rating string: '2x350kW & 2x175kW' -> 350.0."""
    if not isinstance(rating, str):
        return 0.0
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*kW", rating, flags=re.I)
    return max((float(n) for n in nums), default=0.0)


def norm_postcode(x):
    """Turn 2153, '2153', 2153.0 or ' 2153 ' into '2153'; anything else -> None."""
    try:
        return str(int(float(str(x).strip()))).zfill(4)
    except (ValueError, TypeError):
        return None


def dedupe_sites(s: pd.DataFrame, near_km: float = 0.1, same_name_km: float = 1.0) -> pd.DataFrame:
    """Merge FuelCheck entries that are really one physical site.

    Two entries count as one if they are within near_km, or within same_name_km
    and share a name once 'Petrol' / 'Diesel' / 'Stop' is stripped (FuelCheck
    lists some sites twice, e.g. separate petrol and diesel stations).
    Entries with a Foodary are kept in preference.
    Needs columns: name, lat, lon, has_foodary.
    """
    base = (s["name"].astype(str).str.upper()
              .str.replace(r"\b(PETROL|DIESEL|STOP)\b", "", regex=True)
              .str.replace(r"\s+", " ", regex=True).str.strip())
    order = (s.assign(_f=s["has_foodary"].astype(bool))
               .sort_values("_f", ascending=False, kind="stable").index)
    kept, klat, klon, kname = [], [], [], []
    for i in order:
        a, b, n = s.at[i, "lat"], s.at[i, "lon"], base.at[i]
        if kept:
            d = haversine_km(a, b, np.array(klat), np.array(klon))
            same = np.array(kname) == n
            if (d <= near_km).any() or ((d <= same_name_km) & same).any():
                continue
        kept.append(i); klat.append(a); klon.append(b); kname.append(n)
    return s.loc[sorted(kept)].reset_index(drop=True)
