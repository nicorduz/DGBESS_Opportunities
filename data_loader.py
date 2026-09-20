"""
data_loader.py — loads, cleans and describes the Orennia grid datasets.

Two datasets power the app:

  • BUSES  (Greenfield Interconnection Capacity)  — the headroom / capacity nodes.
      This is the analytical core: every row is a bus (node) in the ISO powerflow
      model with the MW that can be injected there, the constraint that binds first,
      and the congestion parameters around it.

  • SUBSTATIONS — a physical reference layer (names, coordinates, voltage class,
      owner). Used for the "nearest medium-voltage" lookup tool and as an optional
      map overlay.

The file is deliberately data-driven. Drop a newer export into ./data (or upload it
in the sidebar) and everything downstream — filters, map, AI — adapts, because the
column registry below is the single source of truth for labels, help text and which
columns are numeric / filterable.
"""
from __future__ import annotations

from pathlib import Path
import glob
import pandas as pd
import numpy as np
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ─────────────────────────────────────────────────────────────────────────────
# Column registry: raw column  ->  (short label, help/description, kind)
# kind ∈ {"num","cat","geo","text","id","bool"}.  Anything not listed still loads;
# it simply won't get a curated label or a tuned filter.
# ─────────────────────────────────────────────────────────────────────────────
BUS_COLUMNS: dict[str, tuple[str, str, str]] = {
    "Bus ID":                                   ("Bus ID", "Unique node identifier in the ISO powerflow model.", "id"),
    "Bus Name":                                 ("Bus / substation name", "Name of the electrical bus (usually the host substation).", "text"),
    "Bus Voltage (kV)":                         ("Voltage (kV)", "Nominal voltage class of the bus. Medium voltage for siting is typically ≤115 kV (commonly 69 kV and 115 kV).", "num"),
    "Interconnection Type":                     ("Interconnection type", "Direction studied. 'Injection' = adding generation/storage export.", "cat"),
    "Bus Interconnection Capacity (MW)":        ("Interconnection capacity (MW)", "MW that can be injected at this bus before ANY constraint binds. The headline 'how big can I build here' number.", "num"),
    "Constraint Headroom (MW)":                 ("Headroom (MW)", "MW of remaining margin on the first binding constraint before it reaches its limit. Higher is better. Capacity ≈ Headroom ÷ |Shift factor|.", "num"),
    "Base Flow (MVA)":                          ("Base flow (MVA)", "Existing loading on the limiting element before any new injection.", "num"),
    "Constraint Base Flow (MW)":                ("Constraint base flow (MW)", "Real-power flow on the binding constraint in the base case.", "num"),
    "Number of Upgrades Assumed (Upgrades)":    ("Upgrades assumed", "Network upgrades baked into the case (0 = greenfield, as-is grid).", "num"),
    "Primary Limiting Constraint":              ("Limiting constraint", "The branch or transformer that binds first and caps injection here.", "text"),
    "Shift Factor (Number)":                    ("Shift factor", "Sensitivity of the binding constraint to injection at this bus. Larger |value| = your project loads that constraint harder.", "num"),
    "Risk Level":                               ("Upgrade risk", "Orennia's qualitative risk that relieving the constraint needs a hard/expensive upgrade.", "cat"),
    "Latitude (Degrees)":                       ("Latitude", "Latitude in decimal degrees.", "geo"),
    "Longitude (Degrees)":                      ("Longitude", "Longitude in decimal degrees.", "geo"),
    "County":                                   ("County", "County of the bus.", "cat"),
    "ISO":                                      ("ISO / RTO", "Grid operator region.", "cat"),
    "State":                                    ("State", "US state.", "cat"),
    "Owner":                                    ("Transmission owner", "Utility that owns the bus / local transmission.", "cat"),
    "Case Last Updated":                        ("Case updated", "Date the underlying powerflow case was refreshed.", "cat"),
    "Constraint Area":                          ("Constraint area", "Region the binding constraint sits in (can differ from the bus's own ISO).", "cat"),
    "Constraint Type":                          ("Constraint type", "Whether the first bind is a line (Branch) or a Transformer.", "cat"),
    "Existing Overload Flag":                   ("Already overloaded", "True = the constraint is already overloaded in the base case (little/no room).", "bool"),
    "Constraint AC Loading Ratio (Percentage)": ("Constraint loading (%)", "How loaded the binding element is. Approaching/over 100% = congested.", "num"),
    "Constraint Voltage":                       ("Constraint voltage (kV)", "Voltage class of the limiting element.", "cat"),
    "Contingency Event":                        ("Contingency event", "The N-1 outage(s) that create the binding condition.", "text"),
    "Contingency Event Facility":               ("Contingency facility", "Facilities out of service in the contingency.", "text"),
    "Contingency Name":                         ("Contingency name", "Label of the driving contingency.", "text"),
    "Descriptive Powerflow Case":               ("Powerflow case", "Study case the numbers come from.", "cat"),
    "Sensitivity Case":                         ("Sensitivity case", "Sensitivity variant of the study.", "cat"),
    "Generator Modeling Assumptions":           ("Generator assumptions", "How queued generators were modeled.", "text"),
    "Interconnection Scenario":                 ("IX scenario", "Interconnection scenario studied.", "cat"),
    "Study Year":                               ("Study year", "Planning horizon of the case.", "cat"),
    "Transmission Modeling Assumptions":        ("Transmission assumptions", "Transmission upgrades reflected in the case.", "text"),
}

SUB_COLUMNS: dict[str, tuple[str, str, str]] = {
    "Substation Name":  ("Substation", "Substation name.", "text"),
    "Min Voltage (kV)": ("Min voltage (kV)", "Lowest voltage class present at the substation.", "num"),
    "Max Voltage (kV)": ("Max voltage (kV)", "Highest voltage class present at the substation.", "num"),
    "Substation Owner": ("Owner", "Owning utility.", "cat"),
    "Substation Status":("Status", "In Service / Planned / Under Construction …", "cat"),
    "Type":             ("Type", "Substation, Tap, Riser, Dead End …", "cat"),
    "Latitude (Degrees)":("Latitude", "Latitude in decimal degrees.", "geo"),
    "Longitude (Degrees)":("Longitude", "Longitude in decimal degrees.", "geo"),
    "County":           ("County", "County.", "cat"),
    "Owner Source":     ("Owner source", "Provenance of the owner attribution.", "cat"),
    "State":            ("State", "US state / province.", "cat"),
    "Substation ID":    ("Substation ID", "Unique identifier.", "id"),
}

# Fields we treat as the headline metrics everywhere (KPIs, default sorts, AI focus).
HEADROOM_COL   = "Constraint Headroom (MW)"
CAPACITY_COL   = "Bus Interconnection Capacity (MW)"
VOLTAGE_COL    = "Bus Voltage (kV)"
LAT_COL        = "Latitude (Degrees)"
LON_COL        = "Longitude (Degrees)"


def _find(pattern: str, exact: str) -> Path | None:
    """Prefer the stable name in ./data, else the newest timestamped export."""
    p = DATA_DIR / exact
    if p.exists():
        return p
    hits = sorted(glob.glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(hits[0]) if hits else None


def _read_csv(path_or_buffer) -> pd.DataFrame:
    # utf-8-sig strips the BOM the Orennia exports carry on the first header.
    df = pd.read_csv(path_or_buffer, encoding="utf-8-sig", low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def _coerce(df: pd.DataFrame, registry: dict) -> pd.DataFrame:
    for col, (_, _, kind) in registry.items():
        if col not in df.columns:
            continue
        if kind in ("num", "geo"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif kind == "bool":
            df[col] = (
                df[col].astype(str).str.strip().str.lower()
                .map({"true": True, "false": False, "1": True, "0": False,
                      "yes": True, "no": False})
            )
    # Clean obvious "not available" strings in categoricals so filters stay tidy.
    for col, (_, _, kind) in registry.items():
        if col in df.columns and kind == "cat":
            df[col] = df[col].replace(
                {"NOT AVAILABLE": np.nan, "Not Available": np.nan,
                 "NaN": np.nan, "": np.nan})
    return df


@st.cache_data(show_spinner=False)
def load_buses(upload=None) -> pd.DataFrame:
    src = upload if upload is not None else _find(
        "*Buses*.csv", "buses.csv")
    if src is None:
        return pd.DataFrame()
    df = _coerce(_read_csv(src), BUS_COLUMNS)
    # Orennia exports repeat some rows verbatim; drop only the EXACT duplicates.
    # Rows that share a Bus ID but differ by limiting constraint/contingency are
    # kept on purpose — they are real, distinct congestion conditions.
    df = df.drop_duplicates()
    # keep only rows we can actually place on a map
    df = df.dropna(subset=[LAT_COL, LON_COL])
    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_substations(upload=None) -> pd.DataFrame:
    src = upload if upload is not None else _find(
        "*Substation*.csv", "substations.csv")
    if src is None:
        return pd.DataFrame()
    df = _coerce(_read_csv(src), SUB_COLUMNS)
    df = df.drop_duplicates()
    df = df.dropna(subset=["Latitude (Degrees)", "Longitude (Degrees)"])
    return df.reset_index(drop=True)


def read_uploaded(file) -> pd.DataFrame:
    """Used by the sidebar uploader for either dataset (no caching on buffer)."""
    return _read_csv(file)


# ── helpers shared by the UI and the AI grounding ──────────────────────────────
def cols_by_kind(registry: dict, kind: str, present_in: pd.DataFrame) -> list[str]:
    return [c for c, (_, _, k) in registry.items()
            if k == kind and c in present_in.columns]


def label(registry: dict, col: str) -> str:
    return registry.get(col, (col, "", ""))[0]


def haversine_miles(lat1, lon1, lat2, lon2):
    """Vectorised great-circle distance in miles."""
    R = 3958.7613
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))
