"""Streamlit dashboard: bird observations and datacenters on an interactive map.

Run with `make dashboard` (or `uv run streamlit run src/core/frameworks/streamlit_app/app.py`).
Reads through the Geodata repositories, so the db must be up (`make up`).
"""

from __future__ import annotations

import os
from dataclasses import asdict

import django
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.frameworks.django_app.config.settings")
django.setup()

from core.frameworks.django_app.geodata.repositories import (
    DjangoBirdObservationRepository,
    DjangoDatacenterRepository,
)

BIRD_COLOR = [34, 139, 94, 200]
DATACENTER_COLOR = [214, 72, 40, 220]
EARTH_RADIUS_KM = 6371.0088


def _flatten(entity: object) -> dict:
    row = asdict(entity)  # type: ignore[call-overload]
    location = row.pop("location") or {}
    return {**row, "latitude": location.get("latitude"), "longitude": location.get("longitude")}


@st.cache_data(ttl=600, show_spinner="Loading bird observations…")
def load_birds() -> pd.DataFrame:
    df = pd.DataFrame(
        [_flatten(o) for o in DjangoBirdObservationRepository().list_all()],
        columns=["id", "common_name", "scientific_name", "observed_on", "latitude", "longitude"],
    )
    df = df.dropna(subset=["latitude", "longitude"])
    df["observed_on"] = pd.to_datetime(df["observed_on"])
    df["species"] = np.where(
        df["common_name"].notna() & df["scientific_name"].notna(),
        df["common_name"].fillna("") + " (" + df["scientific_name"].fillna("") + ")",
        df["common_name"].fillna(df["scientific_name"]).fillna("Unknown"),
    )
    return df


@st.cache_data(ttl=600, show_spinner="Loading datacenters…")
def load_datacenters() -> pd.DataFrame:
    df = pd.DataFrame(
        [_flatten(d) for d in DjangoDatacenterRepository().list_all()],
        columns=["external_id", "name", "operator", "opened_on", "latitude", "longitude"],
    )
    df["opened_on"] = pd.to_datetime(df["opened_on"])
    df["operator"] = df["operator"].fillna("Unknown")
    return df


def distance_to_nearest_km(points: pd.DataFrame, targets: pd.DataFrame) -> np.ndarray:
    """Haversine distance from each point to its nearest target, chunked to bound memory."""
    if points.empty or targets.empty:
        return np.full(len(points), np.inf)
    lat2 = np.radians(targets["latitude"].to_numpy())[None, :]
    lon2 = np.radians(targets["longitude"].to_numpy())[None, :]
    lat1_all = np.radians(points["latitude"].to_numpy())
    lon1_all = np.radians(points["longitude"].to_numpy())
    out = np.empty(len(points))
    chunk = max(1, 2_000_000 // len(targets))
    for start in range(0, len(points), chunk):
        lat1 = lat1_all[start : start + chunk, None]
        lon1 = lon1_all[start : start + chunk, None]
        a = (
            np.sin((lat2 - lat1) / 2) ** 2
            + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
        )
        out[start : start + chunk] = (2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))).min(axis=1)
    return out


def view_state(frames: list[pd.DataFrame]) -> pdk.ViewState:
    non_empty = [f[["latitude", "longitude"]] for f in frames if not f.empty]
    if not non_empty:
        return pdk.ViewState(latitude=30, longitude=0, zoom=1)
    points = pd.concat(non_empty)
    lat_span = points["latitude"].max() - points["latitude"].min()
    lon_span = points["longitude"].max() - points["longitude"].min()
    span = max(lat_span, lon_span, 0.01)
    zoom = float(np.clip(np.log2(360 / span) - 0.5, 1, 14))
    return pdk.ViewState(
        latitude=points["latitude"].mean(), longitude=points["longitude"].mean(), zoom=zoom
    )


st.set_page_config(page_title="Birds vs Datacenters", page_icon="🐦", layout="wide")
st.title("Birds vs Datacenters")

birds_all = load_birds()
datacenters_all = load_datacenters()

# --- Sidebar filters ---------------------------------------------------------------------------
with st.sidebar:
    if st.button("Reload data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.header("Layers")
    show_birds = st.checkbox("Bird observations", value=True)
    show_datacenters = st.checkbox("Datacenters", value=True)

    st.header("Birds")
    species_counts = birds_all["species"].value_counts()
    species = st.multiselect(
        "Species",
        options=species_counts.index.tolist(),
        format_func=lambda s: f"{s} · {species_counts[s]}",
        placeholder="All species",
        disabled=not show_birds,
    )
    observed = birds_all["observed_on"].dropna()
    bird_dates = None
    if not observed.empty and observed.min() < observed.max():
        bird_dates = st.slider(
            "Observed between",
            min_value=observed.min().date(),
            max_value=observed.max().date(),
            value=(observed.min().date(), observed.max().date()),
            disabled=not show_birds,
        )

    st.header("Datacenters")
    operator_counts = datacenters_all["operator"].value_counts()
    operators = st.multiselect(
        "Operators",
        options=operator_counts.index.tolist(),
        format_func=lambda o: f"{o} · {operator_counts[o]}",
        placeholder="All operators",
        disabled=not show_datacenters,
    )
    name_query = st.text_input("Name contains", disabled=not show_datacenters)
    only_dated = st.checkbox(
        "Only with a known opening date",
        help="OpenStreetMap rarely records it.",
        disabled=not show_datacenters,
    )

    st.header("Proximity")
    radius_km = st.slider(
        "Only birds within (km) of a shown datacenter",
        min_value=0,
        max_value=200,
        value=0,
        step=5,
        help="0 disables the filter.",
        disabled=not (show_birds and show_datacenters),
    )
    show_rings = st.checkbox(
        "Draw radius around datacenters", disabled=not (radius_km and show_datacenters)
    )

    st.caption("Map data © OpenStreetMap contributors (ODbL) · Birds: iNaturalist")

# --- Apply filters ------------------------------------------------------------------------------
birds = birds_all
if species:
    birds = birds[birds["species"].isin(species)]
if bird_dates:
    date_from, date_to = (pd.Timestamp(d) for d in bird_dates)
    birds = birds[birds["observed_on"].isna() | birds["observed_on"].between(date_from, date_to)]

datacenters = datacenters_all
if operators:
    datacenters = datacenters[datacenters["operator"].isin(operators)]
if name_query:
    datacenters = datacenters[datacenters["name"].str.contains(name_query, case=False, regex=False)]
if only_dated:
    datacenters = datacenters[datacenters["opened_on"].notna()]

birds = birds.assign(nearest_dc_km=distance_to_nearest_km(birds, datacenters))
if radius_km and show_birds and show_datacenters:
    birds = birds[birds["nearest_dc_km"] <= radius_km]

birds = birds if show_birds else birds.iloc[0:0]
datacenters = datacenters if show_datacenters else datacenters.iloc[0:0]

# --- Metrics ------------------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Bird observations", f"{len(birds):,}", f"of {len(birds_all):,}", delta_color="off")
col2.metric("Species", f"{birds['species'].nunique():,}")
col3.metric(
    "Datacenters", f"{len(datacenters):,}", f"of {len(datacenters_all):,}", delta_color="off"
)
nearest = birds["nearest_dc_km"].replace(np.inf, np.nan).median()
col4.metric("Median bird → datacenter", "—" if pd.isna(nearest) else f"{nearest:,.1f} km")

# --- Map ----------------------------------------------------------------------------------------
bird_layer_data = birds.assign(
    title=birds["species"],
    detail="Observed " + birds["observed_on"].dt.strftime("%Y-%m-%d").fillna("on unknown date"),
    distance=birds["nearest_dc_km"].map(
        lambda d: "" if np.isinf(d) else f"Nearest datacenter: {d:,.1f} km"
    ),
)
dc_layer_data = datacenters.assign(
    title=datacenters["name"],
    detail="Operator: " + datacenters["operator"],
    distance="Opened " + datacenters["opened_on"].dt.strftime("%Y-%m-%d").fillna("on unknown date"),
)

layers = []
if show_rings and radius_km:
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            id="radius",
            data=dc_layer_data[["latitude", "longitude"]],
            get_position=["longitude", "latitude"],
            get_radius=radius_km * 1000,
            get_fill_color=[*DATACENTER_COLOR[:3], 25],
            get_line_color=[*DATACENTER_COLOR[:3], 120],
            stroked=True,
            line_width_min_pixels=1,
        )
    )
layers += [
    pdk.Layer(
        "ScatterplotLayer",
        id="datacenters",
        data=dc_layer_data,
        get_position=["longitude", "latitude"],
        get_fill_color=DATACENTER_COLOR,
        get_line_color=[255, 255, 255],
        stroked=True,
        line_width_min_pixels=1,
        get_radius=400,
        radius_min_pixels=5,
        radius_max_pixels=14,
        pickable=True,
        auto_highlight=True,
    ),
    pdk.Layer(
        "ScatterplotLayer",
        id="birds",
        data=bird_layer_data,
        get_position=["longitude", "latitude"],
        get_fill_color=BIRD_COLOR,
        get_radius=250,
        radius_min_pixels=4,
        radius_max_pixels=10,
        pickable=True,
        auto_highlight=True,
    ),
]

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state([birds, datacenters]),
    map_style=None,
    tooltip={"html": "<b>{title}</b><br/>{detail}<br/>{distance}"},
)
st.caption("🟢 Bird observation · 🔴 Datacenter — scroll to zoom, drag to pan, hover for details.")
st.pydeck_chart(deck, width="stretch", height=620)

# --- Tables -------------------------------------------------------------------------------------
birds_tab, datacenters_tab, species_tab = st.tabs(["Bird observations", "Datacenters", "Species"])
with birds_tab:
    st.dataframe(
        birds[["species", "observed_on", "nearest_dc_km", "latitude", "longitude", "id"]]
        .replace(np.inf, np.nan)
        .sort_values("observed_on", ascending=False),
        hide_index=True,
        width="stretch",
        column_config={
            "observed_on": st.column_config.DateColumn("Observed on"),
            "nearest_dc_km": st.column_config.NumberColumn(
                "Nearest datacenter (km)", format="%.1f"
            ),
            "id": st.column_config.NumberColumn("iNaturalist id", format="%d"),
        },
    )
with datacenters_tab:
    st.dataframe(
        datacenters[["name", "operator", "opened_on", "latitude", "longitude", "external_id"]],
        hide_index=True,
        width="stretch",
        column_config={"opened_on": st.column_config.DateColumn("Opened on")},
    )
with species_tab:
    st.bar_chart(birds["species"].value_counts().head(20), horizontal=True, color="#228B5E")
