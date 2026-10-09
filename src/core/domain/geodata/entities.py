"""Entities for the Geodata bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .value_objects import GeoPoint, GridCell


@dataclass(frozen=True, slots=True)
class BirdObservation:
    """One bird sighting, identified by its id at the source (iNaturalist)."""

    id: int
    common_name: str | None
    scientific_name: str | None
    observed_on: date | None
    location: GeoPoint | None


@dataclass(frozen=True, slots=True)
class Datacenter:
    """A datacenter site, identified by its id at the source it was imported from."""

    external_id: str
    name: str
    location: GeoPoint
    operator: str | None = None
    opened_on: date | None = None
    # ISO 3166-1 alpha-2 code, when the source knows it.
    country: str | None = None
    # Ground area of the mapped building or site, and its number of floors, when known.
    footprint_m2: float | None = None
    levels: int | None = None

    @property
    def floor_area_m2(self) -> float | None:
        """Footprint times levels; a single level is assumed when unknown."""
        if self.footprint_m2 is None:
            return None
        return self.footprint_m2 * (self.levels or 1)


@dataclass(frozen=True, slots=True)
class DailyWeather:
    """Weather of one day over a region (a datacenter's grid cell), in UTC days.

    Metrics are `None` when the source has no value for that day.
    """

    region: GridCell
    day: date
    temperature_mean_c: float | None = None
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    precipitation_mm: float | None = None
    wind_speed_max_kmh: float | None = None
    relative_humidity_mean_pct: float | None = None


@dataclass(frozen=True, slots=True)
class CountryEnergyBenchmark:
    """Aggregate energy figures of the datacenters that reported in one country, for a year.

    `reporting_datacenters` is how many sites the totals cover.
    """

    country: str
    year: int
    reporting_datacenters: int
    it_power_mw: float
    energy_gwh: float


@dataclass(frozen=True, slots=True)
class DatacenterPowerEstimate:
    """Estimated installed IT power and yearly energy use of one datacenter.

    `basis` says how it was estimated (see `PowerEstimateBasis`); `year` is the
    year of the benchmarks it was derived from.
    """

    external_id: str
    country: str | None
    year: int
    basis: str
    it_power_mw: float
    energy_gwh: float
