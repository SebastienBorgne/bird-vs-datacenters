"""Repository interfaces (ports) for the Geodata bounded context.

Defined in the domain layer because the domain dictates what persistence
operations it needs. Concrete implementations live in
`core.infrastructure.persistence.cassandra` and depend on these interfaces —
never the other way around.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .entities import BirdObservation, DailyWeather, Datacenter, DatacenterPowerEstimate
from .value_objects import GeoPoint, GridCell


class BirdObservationRepository(ABC):
    @abstractmethod
    def save_many(self, observations: list[BirdObservation]) -> int:
        """Insert or update observations (keyed by `id`); returns how many were written."""

    @abstractmethod
    def list_all(self) -> list[BirdObservation]: ...

    @abstractmethod
    def list_observed_between(
        self, observed_from: date, observed_to: date
    ) -> list[BirdObservation]:
        """Observations dated `observed_from`..`observed_to` (inclusive); undated ones excluded."""

    @abstractmethod
    def id_bounds(self) -> tuple[int, int] | None:
        """Lowest and highest stored observation ids, or `None` when there are none."""

    @abstractmethod
    def list_near(
        self,
        center: GeoPoint,
        radius_m: float,
        observed_from: date | None = None,
        observed_to: date | None = None,
    ) -> list[BirdObservation]:
        """Observations within `radius_m` meters of `center`, optionally bounded by date."""


class DatacenterRepository(ABC):
    @abstractmethod
    def save_many(self, datacenters: list[Datacenter]) -> int:
        """Insert or update datacenters (keyed by `external_id`); returns how many were written."""

    @abstractmethod
    def list_all(self) -> list[Datacenter]: ...


class DailyWeatherRepository(ABC):
    @abstractmethod
    def save_many(self, days: list[DailyWeather]) -> int:
        """Insert or update days (keyed by `region` and `day`); returns how many were written."""

    @abstractmethod
    def day_bounds(self, region: GridCell) -> tuple[date, date] | None:
        """First and last stored day for `region`, or `None` when there are none."""

    @abstractmethod
    def list_for_region(self, region: GridCell) -> list[DailyWeather]:
        """Every stored day for `region`, in day order."""


class DatacenterPowerEstimateRepository(ABC):
    @abstractmethod
    def save_many(self, estimates: list[DatacenterPowerEstimate]) -> int:
        """Insert or update estimates (keyed by `external_id`); returns how many were written."""

    @abstractmethod
    def list_all(self) -> list[DatacenterPowerEstimate]: ...
