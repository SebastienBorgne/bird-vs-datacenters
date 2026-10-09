"""Streamlit dashboard: bird observations, datacenters and their regions' weather.

Run with `make dashboard` (or `uv run streamlit run src/core/frameworks/streamlit_app/app.py`).
Reads through the Geodata repositories (Cassandra), so it must be up (`make up`).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from core.domain.geodata.value_objects import GridCell
from core.infrastructure.persistence.cassandra.repositories import (
    CassandraBirdObservationRepository,
    CassandraDailyWeatherRepository,
    CassandraDatacenterRepository,
)

# Caps on what is sent to the browser: every point and row is serialized, so showing
# hundreds of thousands of observations exhausts memory. Filters and metrics still
# use every observation.
MAX_MAP_BIRDS = 50_000
MAX_TABLE_ROWS = 10_000
# Older (and undated) observations are not loaded: only these months' partitions are read.
OBSERVED_FROM = date(2010, 1, 1)

BIRD_COLOR = [34, 139, 94, 200]
DATACENTER_COLOR = [214, 72, 40, 220]
EARTH_RADIUS_KM = 6371.0088
DAYS_PER_YEAR = 365.25

# Map coloring of the weather regions: metric -> (summary column, unit, low color, high color).
WEATHER_METRICS = {
    "Mean temperature": ("temperature_mean_c", "°C", [49, 130, 189], [222, 45, 38]),
    "Annual precipitation": ("precipitation_mm_per_year", "mm/yr", [254, 224, 139], [33, 102, 172]),
}


def _flatten(entity: object) -> dict:
    row = asdict(entity)  # type: ignore[call-overload]
    location = row.pop("location") or {}
    return {**row, "latitude": location.get("latitude"), "longitude": location.get("longitude")}


@st.cache_data(ttl=600, show_spinner="Loading bird observations…")
def load_birds() -> pd.DataFrame:
    # Built column by column from the stream: per-row dicts would cost several times
    # the memory of the final frame.
    columns: dict[str, list] = {
        "id": [],
        "observed_on": [],
        "latitude": [],
        "longitude": [],
        "species": [],
    }
    today = datetime.now(UTC).date()
    for o in CassandraBirdObservationRepository().iter_observed_between(OBSERVED_FROM, today):
        if o.location is None:
            continue
        columns["id"].append(o.id)
        columns["observed_on"].append(o.observed_on)
        columns["latitude"].append(o.location.latitude)
        columns["longitude"].append(o.location.longitude)
        columns["species"].append(
            f"{o.common_name} ({o.scientific_name})"
            if o.common_name and o.scientific_name
            else o.common_name or o.scientific_name or "Unknown"
        )
    df = pd.DataFrame(columns)
    df["observed_on"] = pd.to_datetime(df["observed_on"])
    # Few distinct species for many rows: categorical storage is much smaller.
    df["species"] = df["species"].astype("category")
    return df


@st.cache_data(ttl=600, show_spinner="Loading datacenters…")
def load_datacenters() -> pd.DataFrame:
    df = pd.DataFrame(
        [_flatten(d) for d in CassandraDatacenterRepository().list_all()],
        columns=["external_id", "name", "operator", "opened_on", "latitude", "longitude"],
    )
    df["opened_on"] = pd.to_datetime(df["opened_on"])
    df["operator"] = df["operator"].fillna("Unknown")
    return df


def region_key(latitude: pd.Series, longitude: pd.Series) -> pd.Series:
    """`GridCell` key ("38_-78") of each point, vectorized."""
    lat = np.minimum(np.floor(latitude), 89).astype(int).astype(str)
    lon = np.minimum(np.floor(longitude), 179).astype(int).astype(str)
    return lat + "_" + lon


@st.cache_data(ttl=600, show_spinner="Loading weather…")
def load_region_weather(key: str) -> pd.DataFrame:
    """Daily weather of one region, indexed by day."""
    days = CassandraDailyWeatherRepository().list_for_region(GridCell.from_key(key))
    df = pd.DataFrame([{k: v for k, v in asdict(d).items() if k != "region"} for d in days])
    if df.empty:
        return df
    df["day"] = pd.to_datetime(df["day"])
    return df.set_index("day")


@st.cache_data(ttl=600, show_spinner="Summarizing the weather of datacenter regions…")
def load_weather_summary(keys: tuple[str, ...]) -> pd.DataFrame:
    """One row per region with stored weather: coverage and long-run averages."""
    rows = []
    for key in keys:
        df = load_region_weather(key)
        if df.empty:
            continue
        cell = GridCell.from_key(key)
        rows.append(
            {
                "region": key,
                "latitude": cell.latitude,
                "longitude": cell.longitude,
                "first_day": df.index.min(),
                "last_day": df.index.max(),
                "days": len(df),
                "temperature_mean_c": df["temperature_mean_c"].mean(),
                "temperature_min_c": df["temperature_min_c"].min(),
                "temperature_max_c": df["temperature_max_c"].max(),
                "precipitation_mm_per_year": df["precipitation_mm"].mean() * DAYS_PER_YEAR,
                "relative_humidity_mean_pct": df["relative_humidity_mean_pct"].mean(),
            }
        )
    return pd.DataFrame(rows)


def color_scale(values: pd.Series, low: list[int], high: list[int]) -> list[list[int]]:
    """Linear interpolation between two RGB colors over the values' range."""
    span = values.max() - values.min()
    ratio = (values - values.min()) / span if span else values * 0 + 0.5
    return [
        [round(lo + (hi - lo) * r) for lo, hi in zip(low, high, strict=True)] + [140] for r in ratio
    ]


def _unit_vectors(points: pd.DataFrame) -> np.ndarray:
    lat = np.radians(points["latitude"].to_numpy())
    lon = np.radians(points["longitude"].to_numpy())
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def distance_to_nearest_km(points: pd.DataFrame, targets: pd.DataFrame) -> np.ndarray:
    """Great-circle distance from each point to its nearest target.

    On the unit sphere the nearest target is the one with the largest dot product,
    so a (chunked) matrix product finds it, instead of a haversine per pair.
    """
    if points.empty or targets.empty:
        return np.full(len(points), np.inf)
    target_vectors = _unit_vectors(targets).T
    point_vectors = _unit_vectors(points)
    best = np.empty(len(points))
    chunk = max(1, 4_000_000 // len(targets))  # ~32 MB of dot products at a time
    for start in range(0, len(points), chunk):
        best[start : start + chunk] = (point_vectors[start : start + chunk] @ target_vectors).max(
            axis=1
        )
    return EARTH_RADIUS_KM * np.arccos(np.clip(best, -1, 1))


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

    st.header("Weather")
    show_weather = st.checkbox(
        "Datacenter regions",
        value=True,
        help="1° x 1° cells holding a shown datacenter, colored by their weather (Open-Meteo).",
    )
    weather_metric = st.selectbox(
        "Color by", options=list(WEATHER_METRICS), disabled=not show_weather
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

    st.caption(
        "Map data © OpenStreetMap contributors (ODbL) · Birds: iNaturalist · "
        "Weather: Open-Meteo (CC BY 4.0)"
    )

# --- Apply filters ------------------------------------------------------------------------------
birds = birds_all
if species:
    birds = birds[birds["species"].isin(species)]
if bird_dates:
    date_from, date_to = (pd.Timestamp(d) for d in bird_dates)
    birds = birds[birds["observed_on"].between(date_from, date_to)]

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
datacenters = datacenters.assign(
    region=region_key(datacenters["latitude"], datacenters["longitude"])
)
region_datacenters = datacenters["region"].value_counts()
weather_all = load_weather_summary(
    tuple(region_key(datacenters_all["latitude"], datacenters_all["longitude"]).unique())
)
weather = (
    weather_all[weather_all["region"].isin(region_datacenters.index)]
    if not weather_all.empty
    else weather_all
)
map_birds = birds.sample(MAX_MAP_BIRDS, random_state=0) if len(birds) > MAX_MAP_BIRDS else birds

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
bird_layer_data = map_birds[["latitude", "longitude"]].assign(
    title=map_birds["species"].astype(str),
    detail="Observed " + map_birds["observed_on"].dt.strftime("%Y-%m-%d"),
    distance=map_birds["nearest_dc_km"].map(
        lambda d: "" if np.isinf(d) else f"Nearest datacenter: {d:,.1f} km"
    ),
)
dc_layer_data = datacenters.assign(
    title=datacenters["name"],
    detail="Operator: " + datacenters["operator"],
    distance="Opened " + datacenters["opened_on"].dt.strftime("%Y-%m-%d").fillna("on unknown date"),
)

layers = []
if show_weather and not weather.empty:
    column, unit, low_color, high_color = WEATHER_METRICS[weather_metric]
    weather_layer_data = weather.assign(
        polygon=[
            [[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1]]
            for lat, lon in zip(weather["latitude"], weather["longitude"], strict=True)
        ],
        color=color_scale(weather[column], low_color, high_color),
        title="Region "
        + weather["region"]
        + " · "
        + weather["region"].map(region_datacenters).astype(str)
        + " datacenter(s)",
        detail=weather["temperature_mean_c"].map(lambda t: f"Mean {t:.1f} °C")
        + " · "
        + weather["precipitation_mm_per_year"].map(lambda p: f"{p:,.0f} mm/yr"),
        distance="Weather "
        + weather["first_day"].dt.strftime("%Y-%m-%d")
        + " → "
        + weather["last_day"].dt.strftime("%Y-%m-%d"),
    )[["polygon", "color", "title", "detail", "distance"]]
    layers.append(
        pdk.Layer(
            "PolygonLayer",
            id="weather",
            data=weather_layer_data,
            get_polygon="polygon",
            get_fill_color="color",
            get_line_color=[80, 80, 80, 120],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True,
        )
    )
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
    initial_view_state=view_state([map_birds, datacenters]),
    map_style=None,
    tooltip={"html": "<b>{title}</b><br/>{detail}<br/>{distance}"},
)
st.caption("🟢 Bird observation · 🔴 Datacenter — scroll to zoom, drag to pan, hover for details.")
if show_weather:
    column, unit, _, _ = WEATHER_METRICS[weather_metric]
    if weather.empty:
        st.caption("No weather stored yet for the shown datacenters' regions.")
    else:
        st.caption(
            f"{weather_metric}: {weather[column].min():,.1f} {unit} (first color) to "
            f"{weather[column].max():,.1f} {unit} (second color), over "
            f"{len(weather)} of {len(region_datacenters)} regions with stored weather."
        )
if len(map_birds) < len(birds):
    st.caption(
        f"The map shows a random sample of {len(map_birds):,} of the {len(birds):,} matching "
        "observations; narrow the filters to see them all."
    )
st.pydeck_chart(deck, width="stretch", height=620)

# --- Tables -------------------------------------------------------------------------------------
birds_tab, datacenters_tab, species_tab, weather_tab = st.tabs(
    ["Bird observations", "Datacenters", "Species", "Weather"]
)
with birds_tab:
    if len(birds) > MAX_TABLE_ROWS:
        st.caption(f"The {MAX_TABLE_ROWS:,} most recent of {len(birds):,} observations.")
    st.dataframe(
        birds.nlargest(MAX_TABLE_ROWS, "observed_on")[
            ["species", "observed_on", "nearest_dc_km", "latitude", "longitude", "id"]
        ].replace(np.inf, np.nan),
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
with weather_tab:
    if weather.empty:
        st.info("No weather stored yet for the shown datacenters' regions.")
    else:
        regions = [r for r in region_datacenters.index if r in set(weather["region"])]
        region = st.selectbox(
            "Datacenter region (1° x 1° cell)",
            options=regions,
            format_func=lambda r: f"{r} · {region_datacenters[r]} datacenter(s)",
        )
        summary = weather.set_index("region").loc[region]
        daily = load_region_weather(region)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mean temperature", f"{summary['temperature_mean_c']:.1f} °C")
        c2.metric(
            "Record low / high",
            f"{summary['temperature_min_c']:.0f} / {summary['temperature_max_c']:.0f} °C",
        )
        c3.metric("Precipitation", f"{summary['precipitation_mm_per_year']:,.0f} mm/yr")
        c4.metric("Mean humidity", f"{summary['relative_humidity_mean_pct']:.0f} %")
        st.caption(
            f"{summary['days']:,} days stored, {summary['first_day']:%Y-%m-%d} → "
            f"{summary['last_day']:%Y-%m-%d}. The backfill fills five years per region over a "
            "few days (Open-Meteo rate limits)."
        )

        monthly = daily.resample("MS").agg(
            {
                "temperature_mean_c": "mean",
                "temperature_min_c": "min",
                "temperature_max_c": "max",
                "precipitation_mm": "sum",
            }
        )
        st.subheader("Temperature per month (°C)")
        st.line_chart(
            monthly[["temperature_min_c", "temperature_mean_c", "temperature_max_c"]].rename(
                columns={
                    "temperature_min_c": "min",
                    "temperature_mean_c": "mean",
                    "temperature_max_c": "max",
                }
            ),
            color=["#3182bd", "#636363", "#de2d26"],
        )
        st.subheader("Precipitation per month (mm)")
        st.bar_chart(monthly["precipitation_mm"], color="#2166ac")

        st.subheader("Bird observations per month in this region")
        region_birds = birds[region_key(birds["latitude"], birds["longitude"]) == region]
        per_month = (
            region_birds.set_index("observed_on")
            .resample("MS")
            .size()
            .reindex(monthly.index, fill_value=0)
        )
        st.bar_chart(per_month.rename("observations"), color="#228B5E")
        st.caption(
            "Same months as the weather above; follows the bird filters (species, dates). "
            "Recent months dominate because observations are ingested newest first."
        )
