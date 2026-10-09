"""Value objects for the Geodata bounded context.

Value objects are immutable and compared by value, not identity. They
carry no framework dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A WGS84 (EPSG:4326) position, in decimal degrees."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"longitude out of range: {self.longitude}")


@dataclass(frozen=True, slots=True)
class GridCell:
    """A 1° x 1° latitude/longitude cell, named by the floor of its south-west corner.

    Used as the "region" of a datacenter: its key (e.g. "38_-78") is what
    analyses join bird observations, datacenters and weather on.
    """

    latitude: int
    longitude: int

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 89:
            raise ValueError(f"cell latitude out of range: {self.latitude}")
        if not -180 <= self.longitude <= 179:
            raise ValueError(f"cell longitude out of range: {self.longitude}")

    @classmethod
    def containing(cls, point: GeoPoint) -> GridCell:
        # The north pole and the antimeridian (180) belong to the last cell.
        return cls(
            latitude=min(math.floor(point.latitude), 89),
            longitude=min(math.floor(point.longitude), 179),
        )

    @classmethod
    def from_key(cls, key: str) -> GridCell:
        latitude, longitude = key.split("_")
        return cls(latitude=int(latitude), longitude=int(longitude))

    @property
    def key(self) -> str:
        return f"{self.latitude}_{self.longitude}"

    @property
    def center(self) -> GeoPoint:
        return GeoPoint(latitude=self.latitude + 0.5, longitude=self.longitude + 0.5)


class PowerEstimateBasis(StrEnum):
    """How a datacenter's power was estimated, from the most to the least specific."""

    # Its floor area, at its country's energy per m2.
    FLOOR_AREA = "floor_area"
    # Its country's average per reporting datacenter (no floor area).
    COUNTRY_AVERAGE = "country_average"
    # Its floor area, at the energy per m2 of every benchmarked country (no benchmark for
    # its own country).
    BENCHMARK_FLOOR_AREA = "benchmark_floor_area"
    # The average per reporting datacenter over every benchmarked country.
    BENCHMARK_AVERAGE = "benchmark_average"
