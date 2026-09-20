"""
Nofar USA · Grid Interconnection Intelligence
=============================================
Maps and screens Orennia "Greenfield Interconnection Capacity" buses (headroom /
capacity nodes) against a physical substations layer, so the development team can
find the best places to site solar + storage.

Answers Bill Hilliard's three asks:
  1. Filter buses to a state + voltage class + headroom threshold, with names,
     coordinates and every congestion parameter (MA @ 69/115 kV, >600 MW as a preset).
  2. A lookup tool: type coordinates OR an address → nearest medium-voltage headroom.
  3. Same filter engine works for NY / any state the data covers (this Orennia export
     is ISO-NE; a NYISO export drops straight in and Westchester etc. light up).

Plus a FREE LLM assistant (ai_assistant.py) that reads the tables and answers
questions, and a Nofar-branded username/password gate (auth.py).
"""
from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_loader as dl

# ── plotly map compatibility shim ─────────────────────────────────────────────
# Plotly ≥6 renamed the token-free map API: scatter_mapbox → scatter_map,
# Scattermapbox → Scattermap, and layout key `mapbox` → `map`. These helpers pick
# whichever the installed version exposes, so the app runs on plotly 5, 6 or 7.
_NEWMAP = hasattr(px, "scatter_map")


def px_scatter_map(df, **kw):
    fn = px.scatter_map if _NEWMAP else px.scatter_mapbox
    return fn(df, **kw)


def add_map_scatter(fig, **kw):
    (fig.add_scattermap if _NEWMAP else fig.add_scattermapbox)(**kw)


def set_map_layout(fig, *, style, center=None, zoom=None):
    spec = {"style": style}
    if center is not None:
        spec["center"] = center
    if zoom is not None:
        spec["zoom"] = zoom
    fig.update_layout(**({"map": spec} if _NEWMAP else {"mapbox": spec}))

# Optional modules degrade gracefully — a missing one never takes the app down.
try:
    import auth
except Exception as _e:
    auth = None
try:
    import ai_assistant
except Exception as _e:
    ai_assistant = None

# ─────────────────────────────── brand tokens (Nofar)
INDIGO = "#4A2EE3"; DEEP = "#2B1B8F"; INK = "#17153A"
GOLD   = "#F4C843"; PAPER = "#F7F6FC"; MIST = "#E6E2FA"

st.set_page_config(page_title="Nofar · Grid Interconnection Intelligence",
                   layout="wide", page_icon="assets/nofar_logo.png",
                   initial_sidebar_state="expanded")

APP_VERSION = "v1 · 2026-09-19 · Orennia buses + substations · ISO-NE"

APP_USER = auth.require_login() if auth else "dev"


def _logo_b64():
    for p in ("assets/nofar_logo.png", "assets/logo.png"):
        f = Path(p)
        if f.exists():
            try:
                return base64.b64encode(f.read_bytes()).decode()
            except Exception:
                pass
    return ""


st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp {{ font-family:'Inter',sans-serif; color:{INK}; }}
.stApp {{ background:{PAPER}; }}
#MainMenu, footer {{ visibility:hidden; }}
header[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:0.8rem; max-width:1500px; }}
h1,h2,h3,h4 {{ font-family:'Space Grotesk',sans-serif; color:{INK}; letter-spacing:-.01em; }}

.hero {{ background:linear-gradient(120deg,{DEEP} 0%,{INDIGO} 70%);
  border-radius:18px; padding:24px 32px 50px; position:relative; overflow:hidden; }}
.hero::after {{ content:""; position:absolute; right:-40px; top:-60px; width:320px; height:320px;
  background:repeating-linear-gradient(45deg,{GOLD} 0 14px,transparent 14px 42px);
  opacity:.26; transform:rotate(8deg); border-radius:24px; }}
.hero img {{ height:42px; background:#fff; padding:7px 14px; border-radius:10px; }}
.hero .t {{ font-family:'Space Grotesk'; font-size:29px; font-weight:700; color:#fff; margin:12px 0 2px; }}
.hero .s {{ color:#CFC8F7; font-size:14.5px; max-width:900px; }}
.hero .chip {{ display:inline-block; background:rgba(255,255,255,.14); color:#fff; font-size:12px;
  padding:4px 12px; border-radius:99px; margin-right:8px; margin-top:12px; }}

.kpis {{ display:flex; gap:14px; margin:-30px 8px 6px; position:relative; z-index:3; flex-wrap:wrap; }}
.kpi {{ flex:1; min-width:150px; background:#fff; border:1px solid {MIST}; border-radius:14px;
  padding:14px 18px 12px; box-shadow:0 8px 22px rgba(43,27,143,.10); position:relative; overflow:hidden; }}
.kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:5px;
  background:repeating-linear-gradient(45deg,{GOLD} 0 6px,{INDIGO} 6px 12px); }}
.kpi .v {{ font-family:'Space Grotesk'; font-size:25px; font-weight:700; color:{INDIGO}; }}
.kpi .l {{ font-size:12px; color:#6B668F; margin-top:2px; }}

.stTabs [data-baseweb="tab-list"] {{ gap:8px; background:transparent; }}
.stTabs [data-baseweb="tab"] {{ background:#fff; border:1px solid {MIST}; border-radius:99px;
  padding:8px 18px; font-weight:500; color:{INK}; }}
.stTabs [aria-selected="true"] {{ background:{INDIGO} !important; color:#fff !important; border-color:{INDIGO} !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}

.card {{ background:#fff; border:1px solid {MIST}; border-radius:16px; padding:18px 20px;
  box-shadow:0 4px 16px rgba(43,27,143,.06); margin-bottom:14px; }}
.sect {{ font-family:'Space Grotesk'; font-weight:700; font-size:18px; margin:6px 0 2px;
  padding-left:14px; border-left:5px solid {GOLD}; }}
.sub {{ color:#6B668F; font-size:13px; margin-bottom:10px; }}
.stButton>button {{ background:{INDIGO}; color:#fff; border:none; border-radius:10px; font-weight:600; padding:8px 16px; }}
.stButton>button:hover {{ background:{DEEP}; color:{GOLD}; }}
div[data-testid="stDataFrame"] {{ background:#fff; border-radius:14px; border:1px solid {MIST}; padding:6px; }}
section[data-testid="stSidebar"] {{ background:#fff; border-right:1px solid {MIST}; }}
</style>""", unsafe_allow_html=True)


# ─────────────────────────────── data (with optional sidebar uploads)
with st.sidebar:
    lb = _logo_b64()
    if lb:
        st.markdown(f'<img src="data:image/png;base64,{lb}" style="max-height:52px;margin:4px 0 10px">',
                    unsafe_allow_html=True)
    st.markdown(f"**Signed in:** `{APP_USER}`")
    if auth and st.button("Log out", use_container_width=True):
        auth.logout()
    st.divider()
    st.markdown("##### Data sources")
    up_bus = st.file_uploader("Buses / headroom CSV (optional override)", type=["csv"], key="ub")
    up_sub = st.file_uploader("Substations CSV (optional override)", type=["csv"], key="us")

buses = dl.load_buses(up_bus if up_bus else None)
subs  = dl.load_substations(up_sub if up_sub else None)

if buses.empty:
    st.error("No buses data found. Place `buses.csv` in ./data or upload it in the sidebar.")
    st.stop()


# ─────────────────────────────── hero
lb = _logo_b64()
logo_html = f'<img src="data:image/png;base64,{lb}">' if lb else '<div style="color:#fff;font-family:Space Grotesk;font-size:26px;font-weight:700">Nofar<sup style="font-size:12px">USA</sup></div>'
iso_list = ", ".join(sorted(buses["ISO"].dropna().unique())) if "ISO" in buses else "—"
st.markdown(f"""<div class="hero">{logo_html}
  <div class="t">Grid Interconnection Intelligence</div>
  <div class="s">Where to site solar + storage: Orennia greenfield headroom &amp; capacity by bus,
  with the congestion parameters that decide siting — filtered by state, county, utility, voltage,
  risk and constraint. Physical substation layer + free-text data assistant included.</div>
  <span class="chip">ISO: {iso_list}</span>
  <span class="chip">{len(buses):,} buses</span>
  <span class="chip">{len(subs):,} substations</span>
  <span class="chip">{APP_VERSION}</span>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────── filter engine
def cat_options(df, col):
    return sorted(df[col].dropna().unique().tolist()) if col in df else []


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if f["states"]:      m &= df["State"].isin(f["states"])
    if f["counties"]:    m &= df["County"].isin(f["counties"])
    if f["owners"]:      m &= df["Owner"].isin(f["owners"])
    if f["volts"]:       m &= df[dl.VOLTAGE_COL].isin(f["volts"])
    if f["risk"]:        m &= df["Risk Level"].isin(f["risk"])
    if f["ctype"]:       m &= df["Constraint Type"].isin(f["ctype"])
    m &= df[dl.HEADROOM_COL].between(*f["headroom"])
    m &= df[dl.CAPACITY_COL].between(*f["capacity"])
    if f["max_loading"] is not None and "Constraint AC Loading Ratio (Percentage)" in df:
        m &= df["Constraint AC Loading Ratio (Percentage)"].fillna(0) <= f["max_loading"]
    if f["max_sf"] is not None and "Shift Factor (Number)" in df:
        m &= df["Shift Factor (Number)"].abs().fillna(0) <= f["max_sf"]
    if f["hide_overload"] and "Existing Overload Flag" in df:
        m &= df["Existing Overload Flag"] != True     # noqa: E712
    if f["mv_only"]:     m &= df[dl.VOLTAGE_COL] <= 115
    if f["name"].strip():
        m &= df["Bus Name"].astype(str).str.contains(f["name"].strip(), case=False, na=False)
    return df[m]


# ─────────────────────────────── tabs
tab_map, tab_lookup, tab_ai, tab_about = st.tabs(
    ["🗺️  Headroom map & screen", "📍  Nearest-node lookup", "🤖  Ask the data", "ℹ️  Data dictionary"])


# ============================================================ TAB 1: MAP + SCREEN
with tab_map:
    st.markdown('<div class="sect">Filters</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Every physical & congestion parameter is a filter. '
                'Use the preset for Bill\'s Massachusetts ask, or build your own screen.</div>',
                unsafe_allow_html=True)

    # Preset buttons
    pc1, pc2, pc3, _ = st.columns([1.1, 1.1, 1, 3])
    preset = st.session_state.get("preset", {})
    if pc1.button("⭐ Bill's MA preset (69/115 kV · >600 MW)", use_container_width=True):
        preset = {"states": ["MA"], "volts": [69.0, 115.0], "headroom_min": 600}
        st.session_state["preset"] = preset
    if pc2.button("Medium voltage ≤115 kV · high headroom", use_container_width=True):
        preset = {"mv_only": True, "headroom_min": 300}
        st.session_state["preset"] = preset
    if pc3.button("Clear filters", use_container_width=True):
        preset = {}
        st.session_state["preset"] = {}

    hmin_data = float(np.floor(buses[dl.HEADROOM_COL].min()))
    hmax_data = float(np.ceil(buses[dl.HEADROOM_COL].max()))
    cmin_data = float(np.floor(buses[dl.CAPACITY_COL].min()))
    cmax_data = float(np.ceil(buses[dl.CAPACITY_COL].max()))

    r1 = st.columns([1.2, 1.2, 1.2, 1.4])
    states = r1[0].multiselect("State", cat_options(buses, "State"),
                               default=preset.get("states", []))
    # counties depend on chosen states
    county_pool = buses[buses["State"].isin(states)] if states else buses
    counties = r1[1].multiselect("County", cat_options(county_pool, "County"))
    owners = r1[2].multiselect("Transmission owner", cat_options(buses, "Owner"))
    volt_opts = sorted(buses[dl.VOLTAGE_COL].dropna().unique().tolist())
    volts = r1[3].multiselect("Voltage class (kV)", volt_opts,
                              default=preset.get("volts", []))

    r2 = st.columns([1.4, 1.4, 1.1, 1.1])
    headroom = r2[0].slider("Headroom (MW)", hmin_data, hmax_data,
                            (float(preset.get("headroom_min", hmin_data)), hmax_data))
    capacity = r2[1].slider("Interconnection capacity (MW)", cmin_data, cmax_data,
                            (cmin_data, cmax_data))
    risk = r2[2].multiselect("Upgrade risk", cat_options(buses, "Risk Level"))
    ctype = r2[3].multiselect("Constraint type", cat_options(buses, "Constraint Type"))

    r3 = st.columns([1.3, 1.3, 1.2, 1.2])
    max_loading = r3[0].slider("Max constraint loading (%)", 0, 160, 160)
    max_sf = r3[1].slider("Max |shift factor|", 0.0, 1.2, 1.2, 0.05)
    mv_only = r3[2].checkbox("Medium voltage ≤115 kV only", value=preset.get("mv_only", False))
    hide_overload = r3[3].checkbox("Hide already-overloaded", value=False)

    name = st.text_input("Search bus / substation name contains…", "")

    f = dict(states=states, counties=counties, owners=owners, volts=volts, risk=risk,
             ctype=ctype, headroom=headroom, capacity=capacity,
             max_loading=(None if max_loading >= 160 else max_loading),
             max_sf=(None if max_sf >= 1.2 else max_sf),
             mv_only=mv_only, hide_overload=hide_overload, name=name)

    view = apply_filters(buses, f)

    # KPIs
    st.markdown(f"""<div class="kpis">
      <div class="kpi"><div class="v">{len(view):,}</div><div class="l">Buses in view</div></div>
      <div class="kpi"><div class="v">{view[dl.HEADROOM_COL].max() if len(view) else 0:,.0f}</div><div class="l">Max headroom (MW)</div></div>
      <div class="kpi"><div class="v">{view[dl.CAPACITY_COL].max() if len(view) else 0:,.0f}</div><div class="l">Max capacity (MW)</div></div>
      <div class="kpi"><div class="v">{view['State'].nunique() if len(view) else 0}</div><div class="l">States</div></div>
      <div class="kpi"><div class="v">{view['County'].nunique() if len(view) else 0}</div><div class="l">Counties</div></div>
    </div>""", unsafe_allow_html=True)

    if view.empty:
        st.warning("No buses match these filters. Loosen a threshold.")
    else:
        mc1, mc2, mc3 = st.columns([1.2, 1.2, 1.6])
        color_by = mc1.selectbox("Color map by",
                                 [dl.HEADROOM_COL, dl.CAPACITY_COL,
                                  "Constraint AC Loading Ratio (Percentage)"], index=0)
        show_subs = mc2.checkbox("Overlay substations in view area", value=False)
        base_style = mc3.selectbox("Base map",
                                   ["open-street-map", "carto-positron", "carto-darkmatter"], index=1)

        # marker size ∝ capacity (clipped so nothing dominates)
        size = view[dl.CAPACITY_COL].clip(lower=20, upper=1500)
        hover_cols = {
            dl.VOLTAGE_COL: True, dl.HEADROOM_COL: ":.0f", dl.CAPACITY_COL: ":.0f",
            "Constraint AC Loading Ratio (Percentage)": ":.0f", "Risk Level": True,
            "Constraint Type": True, "County": True, "State": True, "Owner": True,
            dl.LAT_COL: False, dl.LON_COL: False,
        }
        hover_cols = {k: v for k, v in hover_cols.items() if k in view.columns}
        color_scale = ([[0, "#E4DEFA"], [0.4, INDIGO], [1, DEEP]]
                       if color_by != "Constraint AC Loading Ratio (Percentage)"
                       else [[0, "#CFEAD6"], [0.6, GOLD], [1, "#B3261E"]])

        fig = px_scatter_map(
            view, lat=dl.LAT_COL, lon=dl.LON_COL, color=color_by, size=size,
            size_max=26, zoom=6, height=620, hover_name="Bus Name",
            hover_data=hover_cols, color_continuous_scale=color_scale)
        if show_subs and not subs.empty:
            latb = (view[dl.LAT_COL].min() - .3, view[dl.LAT_COL].max() + .3)
            lonb = (view[dl.LON_COL].min() - .3, view[dl.LON_COL].max() + .3)
            sv = subs[(subs["Latitude (Degrees)"].between(*latb)) &
                      (subs["Longitude (Degrees)"].between(*lonb))]
            add_map_scatter(
                fig,
                lat=sv["Latitude (Degrees)"], lon=sv["Longitude (Degrees)"],
                mode="markers", marker=dict(size=6, color="#8A85AD"),
                name="Substations", hoverinfo="text",
                text=sv["Substation Name"].astype(str) + " · " +
                     sv["Max Voltage (kV)"].astype(str) + " kV")
        set_map_layout(fig, style=base_style)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(orientation="h", y=1.02),
                          coloraxis_colorbar_title=dl.label(dl.BUS_COLUMNS, color_by))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # results table + download
        st.markdown('<div class="sect">Ranked buses (highest headroom first)</div>',
                    unsafe_allow_html=True)
        table_cols = [c for c in ["Bus Name", dl.VOLTAGE_COL, dl.HEADROOM_COL, dl.CAPACITY_COL,
                                  "Constraint AC Loading Ratio (Percentage)", "Existing Overload Flag",
                                  "Shift Factor (Number)", "Risk Level", "Constraint Type",
                                  "Primary Limiting Constraint", "County", "State", "Owner",
                                  dl.LAT_COL, dl.LON_COL] if c in view.columns]
        ranked = view.sort_values(dl.HEADROOM_COL, ascending=False)[table_cols]
        st.dataframe(ranked, use_container_width=True, height=340,
                     column_config={c: st.column_config.Column(dl.label(dl.BUS_COLUMNS, c))
                                    for c in table_cols})
        st.download_button("⬇️  Download this screen (CSV)",
                           ranked.to_csv(index=False).encode(),
                           file_name="nofar_headroom_screen.csv", mime="text/csv")


# ============================================================ TAB 2: NEAREST LOOKUP
with tab_lookup:
    st.markdown('<div class="sect">Nearest medium-voltage headroom</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Bill\'s tool #2 — enter coordinates or an address; '
                'get the closest buses (with headroom) and the closest physical substations.</div>',
                unsafe_allow_html=True)

    lc1, lc2 = st.columns([1.3, 1])
    mode = lc1.radio("Input", ["Coordinates (lat, lon)", "Address / place"], horizontal=True)
    lat = lon = None
    if mode.startswith("Coord"):
        cc = lc1.columns(2)
        lat = cc[0].number_input("Latitude", value=42.3601, format="%.5f")
        lon = cc[1].number_input("Longitude", value=-71.0589, format="%.5f")
    else:
        addr = lc1.text_input("Address or place", "Worcester, MA")
        if lc1.button("Geocode"):
            try:
                from geopy.geocoders import Nominatim
                geo = Nominatim(user_agent="nofar-grid-intelligence")
                loc = geo.geocode(addr, timeout=10)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
                    st.session_state["geo_latlon"] = (lat, lon)
                    st.success(f"{loc.address}  →  ({lat:.5f}, {lon:.5f})")
                else:
                    st.error("Could not geocode that address. Try coordinates instead.")
            except Exception as e:
                st.warning(f"Geocoding needs `geopy` + internet ({e}). Use coordinates instead.")
        if st.session_state.get("geo_latlon"):
            lat, lon = st.session_state["geo_latlon"]

    n_near = lc2.slider("How many results", 3, 25, 8)
    mv_lookup = lc2.checkbox("Medium voltage ≤115 kV only", value=True)
    min_head = lc2.number_input("Min headroom (MW)", value=0, step=50)

    if lat is not None and lon is not None:
        pool = buses[buses[dl.VOLTAGE_COL] <= 115] if mv_lookup else buses
        pool = pool[pool[dl.HEADROOM_COL] >= min_head].copy()
        pool["Distance (mi)"] = dl.haversine_miles(lat, lon,
                                                   pool[dl.LAT_COL], pool[dl.LON_COL])
        near = pool.nsmallest(n_near, "Distance (mi)")

        cols = ["Distance (mi)", "Bus Name", dl.VOLTAGE_COL, dl.HEADROOM_COL, dl.CAPACITY_COL,
                "Constraint AC Loading Ratio (Percentage)", "Risk Level", "County", "State", "Owner"]
        cols = [c for c in cols if c in near.columns]
        show = near[cols].copy()
        show["Distance (mi)"] = show["Distance (mi)"].round(1)
        st.dataframe(show, use_container_width=True, height=320,
                     column_config={c: st.column_config.Column(dl.label(dl.BUS_COLUMNS, c))
                                    for c in cols if c in dl.BUS_COLUMNS})

        # nearest physical substations too (names + coordinates — Bill's ask)
        if not subs.empty:
            sp = subs.copy()
            sp["Distance (mi)"] = dl.haversine_miles(lat, lon,
                                                     sp["Latitude (Degrees)"], sp["Longitude (Degrees)"])
            ns_cols = ["Distance (mi)", "Substation Name", "Min Voltage (kV)",
                       "Max Voltage (kV)", "Substation Owner", "County", "State",
                       "Latitude (Degrees)", "Longitude (Degrees)"]
            ns_cols = [c for c in ns_cols if c in sp.columns]
            ns = sp.nsmallest(6, "Distance (mi)")[ns_cols].copy()
            ns["Distance (mi)"] = ns["Distance (mi)"].round(1)
            st.markdown('<div class="sub" style="margin-top:6px">Closest physical '
                        'substations (name + coordinates):</div>', unsafe_allow_html=True)
            st.dataframe(ns, use_container_width=True, height=240, hide_index=True)

        # map
        fig = go.Figure()
        add_map_scatter(fig, lat=[lat], lon=[lon], mode="markers+text",
                        marker=dict(size=18, color=GOLD), text=["★ your point"],
                        textposition="top center", name="Your point")
        add_map_scatter(
            fig,
            lat=near[dl.LAT_COL], lon=near[dl.LON_COL], mode="markers",
            marker=dict(size=14, color=INDIGO), name="Nearest buses",
            text=near["Bus Name"].astype(str) + " · " +
                 near[dl.HEADROOM_COL].round(0).astype(str) + " MW headroom",
            hoverinfo="text")
        set_map_layout(fig, style="carto-positron",
                       center={"lat": lat, "lon": lon}, zoom=8)
        fig.update_layout(height=460, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Enter coordinates or geocode an address to see the nearest nodes.")


# ============================================================ TAB 3: AI
with tab_ai:
    st.markdown('<div class="sect">Ask the data (free LLM)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Answers are grounded in the buses currently in your '
                '<b>Headroom map</b> filter, plus keyword lookups across the full dataset.</div>',
                unsafe_allow_html=True)
    if ai_assistant is None:
        st.info("`ai_assistant.py` failed to import. Check requirements.txt.")
    else:
        # `view` is computed in the map tab (same module scope). Fall back to all buses.
        ai_assistant.render_chat(view, buses, subs)


# ============================================================ TAB 4: DICTIONARY
with tab_about:
    st.markdown('<div class="sect">What each column means</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">The buses table is Orennia\'s Greenfield Interconnection '
                'Capacity export. Headroom, capacity, loading, shift factor and risk are the '
                'siting parameters. This export covers ISO-NE; drop a NYISO export into the '
                'sidebar to screen New York (Westchester, etc.).</div>', unsafe_allow_html=True)
    dd = pd.DataFrame(
        [(v[0], k, v[1]) for k, v in dl.BUS_COLUMNS.items() if k in buses.columns],
        columns=["Field", "Raw column", "Meaning"])
    st.dataframe(dd, use_container_width=True, height=560, hide_index=True)

    st.markdown('<div class="sect">Substation reference table</div>', unsafe_allow_html=True)
    ds = pd.DataFrame(
        [(v[0], k, v[1]) for k, v in dl.SUB_COLUMNS.items() if k in subs.columns],
        columns=["Field", "Raw column", "Meaning"])
    st.dataframe(ds, use_container_width=True, height=280, hide_index=True)

st.markdown(f'<div style="text-align:center;color:#8A85AD;font-size:12px;margin-top:18px">'
            f'Nofar USA · BlueSky Utility · {APP_VERSION} · '
            f'Orennia data is licensed & confidential — authorized personnel only</div>',
            unsafe_allow_html=True)
