"""Repository interfaces (ports) for the Geodata bounded context.

Defined in the domain layer because the domain dictates what persistence
operations it needs. Concrete implementations live in
`core.frameworks.django_app.geodata` and depend on these interfaces —
never the other way around.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .entities import BirdObservation, Datacenter
from .value_objects import GeoPoint


class BirdObservationRepository(ABC):
    @abstractmethod
    def save_many(self, observations: list[BirdObservation]) -> int:
        """Insert or update observations (keyed by `id`); returns how many were written."""

    @abstractmethod
    def list_all(self) -> list[BirdObservation]: ...

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
