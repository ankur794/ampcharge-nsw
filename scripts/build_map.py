"""Build a polished interactive map of the AmpCharge opportunity shortlist.

    PYTHONPATH=src python scripts/build_map.py

Reads outputs/opportunity_sites.csv, the official charger file and the Ampol
sites; writes outputs/ampcharge_map.html.

  - grey dots: every existing fast charger (context)
  - numbered red circles: the Top 25 opportunity sites, ranked, sized by
    demand gap; a gold ring means the site has a Foodary
  - legend with a size scale, and a title block
"""
from __future__ import annotations

import os
import re
import pandas as pd
import folium
from folium.features import DivIcon

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
TOP_N = 25

RED = "#d62828"
RED_FILL = "#e63946"
GOLD = "#f4a300"
CHARGER = "#5a7d9a"


def max_kw(rating):
    if not isinstance(rating, str):
        return 0.0
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*kW", rating, flags=re.I)
    return max((float(n) for n in nums), default=0.0)


def main():
    opp = pd.read_csv(os.path.join(OUT, "opportunity_sites.csv"), dtype={"site_id": str}).head(TOP_N)
    sites = pd.read_csv(os.path.join(RAW, "ampol_sites_nsw.csv"), dtype={"site_id": str})
    opp = opp.merge(sites[["site_id", "lat", "lon"]], on="site_id", how="left").dropna(subset=["lat", "lon"])

    ch = pd.read_csv(os.path.join(RAW, "ev_charging_nsw_official.csv"))
    ch["kw"] = ch["Charger_rating"].map(max_kw)
    fast = ch[(ch["kw"] >= 50)
              & ~ch["Charger_Type"].astype(str).str.contains("upcoming|planned", case=False, na=False)]
    fast = fast.dropna(subset=["Latitude", "Longitude"])

    m = folium.Map(location=[-33.82, 151.0], zoom_start=11, tiles="OpenStreetMap", control_scale=True)

    # existing fast chargers
    fg_ch = folium.FeatureGroup(name="Existing fast chargers", show=True)
    for _, c in fast.iterrows():
        folium.CircleMarker([c["Latitude"], c["Longitude"]], radius=3,
                            color=CHARGER, fill=True, fill_color=CHARGER,
                            fill_opacity=0.7, weight=0,
                            tooltip=f"{c.get('Operator','charger')} ~{int(c['kw'])}kW").add_to(fg_ch)
    fg_ch.add_to(m)

    # opportunity sites, ranked + sized by gap
    fg_opp = folium.FeatureGroup(name="AmpCharge opportunity sites (Top 25)", show=True)
    gmax = opp["gap"].max() if len(opp) else 1
    for i, (_, s) in enumerate(opp.iterrows(), 1):
        r = 10 + 16 * (s["gap"] / gmax)
        popup = folium.Popup(html=(
            f"<div style='font-family:sans-serif;font-size:12px'>"
            f"<b>#{i} &nbsp;{s['name']}</b><br>"
            f"<span style='color:#555'>{s['lga']} LGA</span><hr style='margin:4px 0'>"
            f"EVs in LGA: <b>{int(s['ev_count']):,}</b><br>"
            f"Shortfall vs demand: <b>{s['gap']:.1f}</b> fast chargers<br>"
            f"Nearest fast charger: <b>{s['nearest_fast_km']:.1f} km</b><br>"
            f"Foodary on site: <b>{'yes' if s['has_foodary'] else 'no'}</b></div>"), max_width=260)
        # gold ring for Foodary sites
        if s["has_foodary"]:
            folium.CircleMarker([s["lat"], s["lon"]], radius=r + 3, color=GOLD,
                                fill=False, weight=3, opacity=0.9).add_to(fg_opp)
        folium.CircleMarker([s["lat"], s["lon"]], radius=r, color=RED, fill=True,
                            fill_color=RED_FILL, fill_opacity=0.8, weight=1.5,
                            popup=popup, tooltip=f"#{i} {s['name']}").add_to(fg_opp)
        folium.map.Marker([s["lat"], s["lon"]], icon=DivIcon(
            icon_size=(24, 24), icon_anchor=(12, 12),
            html=f"<div style='font-size:11px;font-weight:700;color:white;"
                 f"text-align:center;line-height:24px;pointer-events:none'>{i}</div>")).add_to(fg_opp)
    fg_opp.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    if len(opp):
        m.fit_bounds([[opp["lat"].min(), opp["lon"].min()],
                      [opp["lat"].max(), opp["lon"].max()]], padding=(60, 60))

    title = ("<div style='position:fixed;top:12px;left:50px;z-index:9999;background:white;"
             "padding:10px 14px;border:1px solid #ccc;border-radius:8px;font-family:sans-serif;"
             "max-width:360px;box-shadow:0 1px 4px rgba(0,0,0,.2)'>"
             "<div style='font-size:15px;font-weight:700;color:#1b2a4a'>Where AmpCharge could build next</div>"
             "<div style='font-size:12px;color:#444;margin-top:2px'>NSW Ampol sites in areas with more EV "
             "demand than the charging network has kept up with.</div>"
             "<div style='font-size:10.5px;color:#777;margin-top:5px'>Independent student project. "
             "Public data: NSW EV registrations, NSW EV charger locations, FuelCheck. Not affiliated with Ampol.</div></div>")
    m.get_root().html.add_child(folium.Element(title))

    legend = ("<div style='position:fixed;bottom:24px;right:18px;z-index:9999;background:white;"
              "padding:10px 14px;border:1px solid #ccc;border-radius:8px;font-family:sans-serif;"
              "font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.2)'>"
              "<div style='font-weight:700;margin-bottom:6px'>Legend</div>"
              "<div><span style='display:inline-block;width:12px;height:12px;border-radius:50%;"
              f"background:{RED_FILL};margin-right:6px'></span>Opportunity site (number = rank)</div>"
              "<div style='margin-top:3px'><span style='display:inline-block;width:12px;height:12px;"
              f"border-radius:50%;border:2px solid {GOLD};margin-right:6px'></span>Has a Foodary</div>"
              "<div style='margin-top:3px'><span style='display:inline-block;width:8px;height:8px;"
              f"border-radius:50%;background:{CHARGER};margin-right:8px'></span>Existing fast charger</div>"
              "<div style='margin-top:6px;color:#777;font-size:10.5px'>Bigger circle = bigger demand gap</div></div>")
    m.get_root().html.add_child(folium.Element(legend))

    out = os.path.join(OUT, "ampcharge_map.html")
    m.save(out)
    print(f"saved {out}  ({len(opp)} opportunity sites, {len(fast)} existing fast chargers)")


if __name__ == "__main__":
    main()
