"""White-space analysis: high need, low market attention.

Every Ampol site gets two scores:

  NEED       demand side only: EVs per existing fast charger in the site's LGA.
             High = lots of EV owners sharing few fast chargers.
  ATTENTION  market side only: how likely operators are to build a fast charger
             nearby, from the proximity model (distance to existing chargers,
             chargers within 5 km, distance to CBD). Scored out-of-fold so no
             site is scored by a model that saw it.

Both become percentiles (0 = lowest, 1 = highest), then sites fall into:

  WHITE SPACE   high need, low attention   <- the shortlist
  CONTESTED     high need, high attention  (the market is already coming)
  SATURATED     low need, high attention
  LOW PRIORITY  low need, low attention

    PYTHONPATH=src python scripts/white_space.py

Needs outputs/placement_drivers_sites.csv (what_drives_placement.py) and
outputs/lga_validation.csv (validate_demand.py).
Writes outputs/white_space_sites.csv and outputs/white_space.png
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from ampcharge.geo import dedupe_sites, BORDER_LGAS

OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
ATTENTION_COLS = ["log_nearest_existing", "existing_within_5km", "log_dist_cbd"]
COLOURS = {"WHITE SPACE": "#d62828", "CONTESTED": "#f4a300",
           "SATURATED": "#5a7d9a", "LOW PRIORITY": "#b8b8b8"}


def main():
    s = pd.read_csv(os.path.join(OUT, "placement_drivers_sites.csv"), dtype={"site_id": str})
    before = len(s)
    s = dedupe_sites(s)
    print(f"Merged duplicate FuelCheck entries: {before} -> {len(s)} physical sites")
    lga = pd.read_csv(os.path.join(OUT, "lga_validation.csv"))[["lga", "fast_chargers"]]
    s = s.merge(lga, on="lga", how="left")
    s["border_area"] = s["lga"].isin(BORDER_LGAS)

    # ATTENTION: out-of-fold probability from the proximity-only model
    y = s["planned_within_2km"].astype(int).values
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    s["attention_prob"] = cross_val_predict(model, s[ATTENTION_COLS].values, y,
                                            cv=cv, method="predict_proba")[:, 1]

    # NEED: EVs per existing fast charger in the LGA (only where we know the LGA)
    known = s["has_lga"].astype(bool) & s["fast_chargers"].notna()
    s["evs_per_fast_charger"] = np.where(known, s["ev_count"] / (s["fast_chargers"] + 1), np.nan)

    k = s[known].copy()
    k["need_pct"] = k["evs_per_fast_charger"].rank(pct=True)
    k["attention_pct"] = k["attention_prob"].rank(pct=True)
    hi_need = k["need_pct"] >= 0.5
    hi_att = k["attention_pct"] >= 0.5
    k["quadrant"] = np.select(
        [hi_need & ~hi_att, hi_need & hi_att, ~hi_need & hi_att],
        ["WHITE SPACE", "CONTESTED", "SATURATED"], default="LOW PRIORITY")
    k["white_space_score"] = k["need_pct"] - k["attention_pct"]

    overlap = k["need_pct"].corr(k["attention_pct"], method="spearman")
    print(f"Sites scored: {len(k)} of {len(s)} (the rest have no LGA match)")
    print(f"Overlap between need and attention (rank correlation): {overlap:.2f}")
    print("  positive = the market mostly does go where need is; white space = the exceptions")

    print("\n=== Sites per quadrant ===")
    q = k.groupby("quadrant").agg(sites=("site_id", "count"),
                                  planned_nearby=("planned_within_2km", "mean"),
                                  foodary=("has_foodary", "mean"))
    q["planned_nearby"] = (q["planned_nearby"] * 100).round(0).astype(int).astype(str) + "%"
    q["foodary"] = (q["foodary"] * 100).round(0).astype(int).astype(str) + "%"
    print(q.to_string())

    all_ws = k[k["quadrant"] == "WHITE SPACE"].sort_values("white_space_score", ascending=False)
    border_ws = all_ws[all_ws["border_area"]]
    ws = all_ws[~all_ws["border_area"]]
    if len(border_ws):
        print(f"\nWhite-space sites in border areas, left out of the ranking "
              f"(cross-border chargers not in the data): {len(border_ws)}")
        print("  " + ", ".join(f"{n} ({l.title()})" for n, l in zip(border_ws["name"], border_ws["lga"])))
    cols = ["site_id", "name", "lga", "evs_per_fast_charger", "nearest_existing_km",
            "need_pct", "attention_pct", "has_foodary"]
    show = ws.head(20)[cols].copy()
    show["evs_per_fast_charger"] = show["evs_per_fast_charger"].round(0).astype(int)
    show["nearest_existing_km"] = show["nearest_existing_km"].round(1)
    show[["need_pct", "attention_pct"]] = show[["need_pct", "attention_pct"]].round(2)
    show["has_foodary"] = show["has_foodary"].astype(bool)
    print("\n=== Top 20 WHITE SPACE sites (high need, low market attention) ===")
    print(show.to_string(index=False))

    k["white_space_rank"] = np.nan
    k.loc[ws.index, "white_space_rank"] = np.arange(1, len(ws) + 1)
    out = s.merge(k[["site_id", "need_pct", "attention_pct", "quadrant",
                     "white_space_score", "white_space_rank"]], on="site_id", how="left")
    out["quadrant"] = out["quadrant"].fillna("UNKNOWN (no LGA)")
    out.to_csv(os.path.join(OUT, "white_space_sites.csv"), index=False)

    # ---- the 2x2 chart (numbered top 10 + ranked list on the right) ----
    fig = plt.figure(figsize=(12.5, 7.5), dpi=150)
    gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.15], wspace=0.04)
    ax = fig.add_subplot(gs[0])
    side = fig.add_subplot(gs[1]); side.axis("off")
    for name, colour in COLOURS.items():
        g = k[k["quadrant"] == name]
        ax.scatter(g["attention_pct"], g["need_pct"], s=26, c=colour,
                   alpha=0.85, edgecolors="white", linewidths=0.4,
                   label=f"{name.title()} ({len(g)})")
    ax.axhline(0.5, color="#888", lw=0.8, ls="--")
    ax.axvline(0.5, color="#888", lw=0.8, ls="--")
    top10 = ws.head(10)
    ax.scatter(top10["attention_pct"], top10["need_pct"], s=170, c=COLOURS["WHITE SPACE"],
               edgecolors="black", linewidths=0.8, zorder=3)
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        ax.text(r["attention_pct"], r["need_pct"], str(i), ha="center", va="center",
                fontsize=7, fontweight="bold", color="white", zorder=4)

    side.text(0.0, 0.97, "Top 10 white-space sites", fontsize=10.5, fontweight="bold",
              va="top", transform=side.transAxes)
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        name = r["name"].replace("Ampol Foodary", "Foodary").title().replace("Eg ", "EG ")
        foodary = "  (Foodary)" if bool(r["has_foodary"]) and "foodary" not in name.lower() else ""
        side.text(0.0, 0.92 - (i - 1) * 0.075, f"{i}.  {name}{foodary}",
                  fontsize=8.6, va="top", transform=side.transAxes)
        side.text(0.065, 0.92 - (i - 1) * 0.075 - 0.032, f"{r['lga'].title()}",
                  fontsize=7.6, color="#777", va="top", transform=side.transAxes)
    ax.set_xlabel("Market attention  (how likely operators build nearby, percentile)")
    ax.set_ylabel("Need  (EVs per existing fast charger in the LGA, percentile)")
    ax.set_title("Ampol sites in NSW: where need is high and the market isn't looking",
                 fontsize=12, loc="left", pad=14)
    ax.text(0.02, 0.98, "WHITE SPACE", transform=ax.transAxes, va="top",
            fontsize=10, fontweight="bold", color=COLOURS["WHITE SPACE"])
    ax.text(0.98, 0.98, "CONTESTED", transform=ax.transAxes, va="top", ha="right",
            fontsize=10, fontweight="bold", color=COLOURS["CONTESTED"])
    ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.06)
    ax.legend(loc="lower right", fontsize=8, frameon=True)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 0.01, "Independent project, public data only. Not affiliated with Ampol.",
             fontsize=7, color="#777")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.92, bottom=0.08)
    fig.savefig(os.path.join(OUT, "white_space.png"))
    print("\nSaved outputs/white_space_sites.csv and outputs/white_space.png")


if __name__ == "__main__":
    main()
