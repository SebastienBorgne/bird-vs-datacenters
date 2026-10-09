"""Ports to the external sources the Geodata use cases read from.

Implemented in `core.infrastructure.sources` (iNaturalist, OpenStreetMap, Open-Meteo, EU
datacentre reporting).
Persistence ports are domain repositories (`core.domain.geodata.repositories`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from core.domain.geodata.entities import (
    BirdObservation,
    CountryEnergyBenchmark,
    DailyWeather,
    Datacenter,
)
from core.domain.geodata.value_objects import GridCell


class SourceUnavailableError(Exception):
    """The source could not be reached or answered with an error, after retries."""


@dataclass(frozen=True, slots=True)
class ObservationPage:
    observations: list[BirdObservation]
    # False once the source returned a short page: nothing further in that direction.
    has_more: bool


class BirdObservationSource(ABC):
    """Observations ordered by id, read one page at a time from either side of a cursor."""

    @abstractmethod
    def newer_than(self, observation_id: int) -> ObservationPage:
        """The page of observations right after `observation_id`, in ascending id order."""

    @abstractmethod
    def older_than(self, observation_id: int | None) -> ObservationPage:
        """The page right before `observation_id` (or the newest, when `None`), descending."""


class DatacenterSource(ABC):
    @abstractmethod
    def fetch_all(self) -> list[Datacenter]:
        """Every datacenter the source knows of, within its configured scope."""


class WeatherSource(ABC):
    @abstractmethod
    def fetch_daily(self, region: GridCell, start: date, end: date) -> list[DailyWeather]:
        """Daily weather over `region`, one entry per day from `start` to `end` (inclusive)."""


class EnergyBenchmarkSource(ABC):
    @abstractmethod
    def fetch_all(self) -> list[CountryEnergyBenchmark]:
        """Per-country benchmarks, at most one per country (the latest year available)."""
