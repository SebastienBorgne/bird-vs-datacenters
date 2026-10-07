"""Entities for the Geodata bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .value_objects import GeoPoint


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
