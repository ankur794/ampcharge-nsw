"""Project EV demand per LGA to 2030 and show where the gap grows.

Fits each LGA's own battery-EV growth from its monthly history, projects to
December 2030, and compares EVs-per-fast-charger now vs then (holding the
charger network at today's level, so this is a demand projection, not a
prediction of what gets built).

    PYTHONPATH=src python scripts/forecast_2030.py

Needs data/raw/ev_by_lga.csv and outputs/lga_validation.csv.
Writes outputs/forecast_2030.csv and outputs/forecast_2030.png
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ampcharge.geo import norm_lga

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
TARGET = pd.Timestamp("2030-12-01")
MAX_ANNUAL_GROWTH = 0.60   # cap per-LGA growth so tiny LGAs don't explode


def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def project_lga(dates, counts):
    """Compound growth from a log-linear fit on the monthly history.

    Returns (projected EV count at TARGET, annual growth rate). Growth is
    capped so a tiny LGA with one noisy jump can't explode.
    """
    dates = list(dates)
    counts = np.asarray(counts, float)
    ok = counts > 0
    if ok.sum() < 3:
        return float(counts[-1]) if len(counts) else 0.0, 0.0
    x = np.array([months_between(dates[0], d) for d in dates])[ok]
    slope = np.polyfit(x, np.log(counts[ok]), 1)[0]      # log units per month
    annual = max(min(np.exp(slope * 12) - 1, MAX_ANNUAL_GROWTH), 0.0)
    ahead = months_between(dates[-1], TARGET)
    projected = counts[-1] * (1 + annual) ** (ahead / 12)
    return float(projected), float(annual)


def main():
    ev = pd.read_csv(os.path.join(RAW, "ev_by_lga.csv"), sep=";")
    ev = ev[ev["motive_power"].str.contains("BATTERY ELECTRIC", case=False, na=False)].copy()
    ev["lga"] = ev["vehicle_garaged_lga"].map(norm_lga)
    ev["date"] = pd.to_datetime(ev["date"])
    monthly = ev.groupby(["lga", "date"])["count"].sum().reset_index()
    n_months = monthly["date"].nunique()
    print(f"EV history: {n_months} months, {monthly['date'].min().date()} to {monthly['date'].max().date()}")

    rows = []
    for lga, g in monthly.groupby("lga"):
        g = g.sort_values("date")
        proj, annual = project_lga(g["date"].tolist(), g["count"].values)
        rows.append({"lga": lga, "ev_now": g["count"].iloc[-1], "ev_2030": round(proj),
                     "annual_growth": annual})
    f = pd.DataFrame(rows)

    val = pd.read_csv(os.path.join(OUT, "lga_validation.csv"))[["lga", "fast_chargers"]]
    f = f.merge(val, on="lga", how="left")
    f["fast_chargers"] = f["fast_chargers"].fillna(0)
    f["need_now"] = f["ev_now"] / (f["fast_chargers"] + 1)
    f["need_2030"] = f["ev_2030"] / (f["fast_chargers"] + 1)
    f["need_increase"] = f["need_2030"] - f["need_now"]
    f = f.sort_values("need_2030", ascending=False).reset_index(drop=True)
    f.to_csv(os.path.join(OUT, "forecast_2030.csv"), index=False)

    print(f"\nNSW battery EVs: {int(f['ev_now'].sum()):,} now -> "
          f"{int(f['ev_2030'].sum()):,} projected by end 2030")
    print("\n=== LGAs most under-served by 2030 (EVs per existing fast charger) ===")
    show = f.head(12)[["lga", "ev_now", "ev_2030", "fast_chargers", "need_now", "need_2030"]].copy()
    show["annual_growth"] = (f.head(12)["annual_growth"] * 100).round(0).astype(int).astype(str) + "%/yr"
    for c in ["need_now", "need_2030"]:
        show[c] = show[c].round(0).astype(int)
    print(show.to_string(index=False))

    # chart: biggest need in 2030, now vs 2030
    top = f.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
    yy = np.arange(len(top))
    ax.barh(yy + 0.2, top["need_now"], height=0.4, color="#9ab", label="now (2026)")
    ax.barh(yy - 0.2, top["need_2030"], height=0.4, color="#d62828", label="projected 2030")
    ax.set_yticks(yy); ax.set_yticklabels([l.title() for l in top["lga"]], fontsize=9)
    ax.set_xlabel("EVs per existing fast charger")
    ax.set_title("Where the EV charging gap grows by 2030 (NSW LGAs)\n"
                 "if the fast-charger network stays as it is today", fontsize=12, loc="left")
    ax.legend(loc="lower right"); ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 0.01, "Independent project, public data. EV demand projected from each LGA's "
             "own growth; charger count held constant.", fontsize=7, color="#777")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "forecast_2030.png"))
    print("\nSaved outputs/forecast_2030.csv and outputs/forecast_2030.png")


if __name__ == "__main__":
    main()
