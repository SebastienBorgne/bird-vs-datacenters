"""Ports to the external sources the Geodata use cases read from.

Implemented in `core.infrastructure.sources` (iNaturalist, OpenStreetMap).
Persistence ports are domain repositories (`core.domain.geodata.repositories`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.domain.geodata.entities import BirdObservation, Datacenter


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
