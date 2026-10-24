"""Interactive map: white space, existing chargers and planned chargers.

    PYTHONPATH=src python scripts/build_map.py

Reads outputs/white_space_sites.csv (white_space.py) and the official charger
file. Writes outputs/ampcharge_map.html.

Layers (each can be switched on/off):
  - White space sites (red, numbered top 20)   high need, low market attention
  - Contested sites (amber)                     high need, market already coming
  - Saturated / low priority sites (grey)
  - Existing fast chargers (slate dots)
  - Planned fast chargers (purple rings)        where the market is heading
"""
from __future__ import annotations

import os
import re
import pandas as pd
import folium
from folium.features import DivIcon

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
TOP_N = 20

RED, AMBER, GREY, SLATE, PURPLE = "#d62828", "#f4a300", "#9a9a9a", "#5a7d9a", "#7b2cbf"


def max_kw(rating):
    if not isinstance(rating, str):
        return 0.0
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*kW", rating, flags=re.I)
    return max((float(n) for n in nums), default=0.0)


def pct(x):
    return "n/a" if pd.isna(x) else f"{x:.0%}"


def popup_html(s, rank=None):
    head = f"#{rank} &nbsp;" if rank else ""
    evpc = "n/a" if pd.isna(s.get("evs_per_fast_charger")) else f"{s['evs_per_fast_charger']:,.0f}"
    return (
        "<div style='font-family:sans-serif;font-size:12px;min-width:220px'>"
        f"<b>{head}{s['name']}</b><br>"
        f"<span style='color:#666'>{str(s.get('lga','')).title()} &middot; {s['quadrant'].title()}</span>"
        "<hr style='margin:5px 0'>"
        f"Need percentile: <b>{pct(s.get('need_pct'))}</b><br>"
        f"Market attention percentile: <b>{pct(s.get('attention_pct'))}</b><br>"
        f"EVs per existing fast charger (LGA): <b>{evpc}</b><br>"
        f"Nearest existing fast charger: <b>{s['nearest_existing_km']:.1f} km</b><br>"
        f"Planned fast charger within 2 km: <b>{'yes' if bool(s['planned_within_2km']) else 'no'}</b><br>"
        f"Foodary on site: <b>{'yes' if bool(s['has_foodary']) else 'no'}</b></div>")


def main():
    s = pd.read_csv(os.path.join(OUT, "white_space_sites.csv"), dtype={"site_id": str})
    s = s.dropna(subset=["lat", "lon"])

    ch = pd.read_csv(os.path.join(RAW, "ev_charging_nsw_official.csv")).dropna(subset=["Latitude", "Longitude"])
    ch["kw"] = ch["Charger_rating"].map(max_kw)
    up = ch["Charger_Type"].astype(str).str.contains("upcoming", case=False, na=False)
    existing = ch[~up & (ch["kw"] >= 50)]
    planned = ch[up & (ch["kw"] >= 50)]

    m = folium.Map(location=[-33.6, 151.1], zoom_start=9, tiles="OpenStreetMap", control_scale=True)

    fg_ex = folium.FeatureGroup(name=f"Existing fast chargers ({len(existing)})", show=True)
    for _, c in existing.iterrows():
        folium.CircleMarker([c["Latitude"], c["Longitude"]], radius=3, color=SLATE, fill=True,
                            fill_color=SLATE, fill_opacity=0.75, weight=0,
                            tooltip=f"Existing: {c.get('Operator','')} ~{int(c['kw'])}kW").add_to(fg_ex)
    fg_ex.add_to(m)

    fg_pl = folium.FeatureGroup(name=f"Planned fast chargers ({len(planned)})", show=True)
    for _, c in planned.iterrows():
        folium.CircleMarker([c["Latitude"], c["Longitude"]], radius=6, color=PURPLE, fill=False,
                            weight=2.5, tooltip=f"Planned: {c.get('Operator','')} ~{int(c['kw'])}kW").add_to(fg_pl)
    fg_pl.add_to(m)

    fg_other = folium.FeatureGroup(name="Other Ampol sites (saturated / low priority)", show=False)
    fg_con = folium.FeatureGroup(name="Contested Ampol sites (market already coming)", show=True)
    fg_ws = folium.FeatureGroup(name=f"White space Ampol sites (top {TOP_N} numbered)", show=True)

    ws = s[s["quadrant"] == "WHITE SPACE"].sort_values("white_space_score", ascending=False)
    rank = {sid: i for i, sid in enumerate(ws["site_id"].head(TOP_N), 1)}

    for _, r in s.iterrows():
        q = r["quadrant"]
        if q == "WHITE SPACE":
            k = rank.get(r["site_id"])
            radius = 11 if k else 7
            folium.CircleMarker([r["lat"], r["lon"]], radius=radius, color="#7a0e0e", weight=1.2,
                                fill=True, fill_color=RED, fill_opacity=0.85,
                                popup=folium.Popup(popup_html(r, k), max_width=300),
                                tooltip=f"{'#'+str(k)+' ' if k else ''}{r['name']}").add_to(fg_ws)
            if k:
                folium.map.Marker([r["lat"], r["lon"]], icon=DivIcon(
                    icon_size=(22, 22), icon_anchor=(11, 11),
                    html=f"<div style='font-size:10px;font-weight:700;color:white;text-align:center;"
                         f"line-height:22px;pointer-events:none'>{k}</div>")).add_to(fg_ws)
        elif q == "CONTESTED":
            folium.CircleMarker([r["lat"], r["lon"]], radius=6, color=AMBER, weight=1,
                                fill=True, fill_color=AMBER, fill_opacity=0.7,
                                popup=folium.Popup(popup_html(r), max_width=300),
                                tooltip=r["name"]).add_to(fg_con)
        else:
            folium.CircleMarker([r["lat"], r["lon"]], radius=4, color=GREY, weight=1,
                                fill=True, fill_color=GREY, fill_opacity=0.6,
                                popup=folium.Popup(popup_html(r), max_width=300),
                                tooltip=r["name"]).add_to(fg_other)

    for fg in (fg_other, fg_con, fg_ws):
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    top = ws.head(TOP_N)
    if len(top):
        m.fit_bounds([[top["lat"].min(), top["lon"].min()],
                      [top["lat"].max(), top["lon"].max()]], padding=(50, 50))

    box = ("position:fixed;z-index:9999;background:white;border:1px solid #ccc;border-radius:8px;"
           "font-family:sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.2);")
    title = (f"<div style='{box}top:12px;left:50px;padding:10px 14px;max-width:370px'>"
             "<div style='font-size:15px;font-weight:700;color:#1b2a4a'>White space for EV fast charging, NSW</div>"
             "<div style='font-size:12px;color:#444;margin-top:3px'>Ampol sites where EV owners are short of fast "
             "chargers, but the market is building elsewhere. Planned chargers (purple) mostly cluster next to "
             "existing ones.</div>"
             "<div style='font-size:10.5px;color:#777;margin-top:5px'>Independent student project, public data only. "
             "Not affiliated with Ampol.</div></div>")
    def dot(c, ring=False, size=12):
        style = f"border:2.5px solid {c};" if ring else f"background:{c};"
        return (f"<span style='display:inline-block;width:{size}px;height:{size}px;border-radius:50%;"
                f"{style}margin-right:7px;vertical-align:middle'></span>")
    legend = (f"<div style='{box}bottom:24px;right:18px;padding:10px 14px;font-size:12px;line-height:1.7'>"
              "<div style='font-weight:700;margin-bottom:3px'>Legend</div>"
              f"<div>{dot(RED)}White space (number = rank)</div>"
              f"<div>{dot(AMBER)}Contested</div>"
              f"<div>{dot(GREY, size=9)}Other Ampol sites (off by default)</div>"
              f"<div>{dot(SLATE, size=8)}Existing fast charger</div>"
              f"<div>{dot(PURPLE, ring=True)}Planned fast charger</div>"
              "<div style='color:#777;font-size:10.5px;margin-top:3px'>Click any Ampol site for its scores</div></div>")
    m.get_root().html.add_child(folium.Element(title))
    m.get_root().html.add_child(folium.Element(legend))

    out = os.path.join(OUT, "ampcharge_map.html")
    m.save(out)
    print(f"saved {out}")
    print(f"  white space: {len(ws)}, contested: {(s['quadrant']=='CONTESTED').sum()}, "
          f"existing fast chargers: {len(existing)}, planned: {len(planned)}")


if __name__ == "__main__":
    main()
