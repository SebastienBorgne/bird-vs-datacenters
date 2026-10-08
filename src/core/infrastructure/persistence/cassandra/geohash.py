"""Minimal geohash: encode a point, and cover a circle with cells.

Used to partition observations by area (`bird_observations_by_cell`):
precision 4 cells are ~39 km wide x ~20 km tall at the equator.
"""

from __future__ import annotations

import math

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
METERS_PER_DEGREE_LAT = 111_320.0


def encode(latitude: float, longitude: float, precision: int) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    chars: list[str] = []
    bits, value, even = 0, 0, True
    while len(chars) < precision:
        rng, coord = (lon_range, longitude) if even else (lat_range, latitude)
        mid = (rng[0] + rng[1]) / 2
        value <<= 1
        if coord >= mid:
            value |= 1
            rng[0] = mid
        else:
            rng[1] = mid
        even, bits = not even, bits + 1
        if bits == 5:
            chars.append(_BASE32[value])
            bits, value = 0, 0
    return "".join(chars)


def cell_size(precision: int) -> tuple[float, float]:
    """(height, width) of a cell, in degrees of latitude and longitude."""
    lon_bits = math.ceil(5 * precision / 2)
    lat_bits = 5 * precision - lon_bits
    return 180 / 2**lat_bits, 360 / 2**lon_bits


def cover(latitude: float, longitude: float, radius_m: float, precision: int) -> set[str]:
    """Cells intersecting the bounding box of a circle (a superset of the circle)."""
    height, width = cell_size(precision)
    dlat = radius_m / METERS_PER_DEGREE_LAT
    lat_min, lat_max = max(-90.0, latitude - dlat), min(90.0, latitude + dlat)
    widest = max(abs(lat_min), abs(lat_max))
    cos = math.cos(math.radians(widest))
    dlon = 180.0 if widest >= 90 or dlat / max(cos, 1e-12) >= 180 else dlat / cos

    def steps(low: float, high: float, step: float) -> list[float]:
        n = max(1, math.ceil((high - low) / step))
        return [low + (high - low) * i / n for i in range(n + 1)]

    cells = set()
    for lat in steps(lat_min, lat_max, height / 2):
        for lon in steps(longitude - dlon, longitude + dlon, width / 2):
            wrapped = (lon + 180) % 360 - 180  # across the antimeridian
            cells.add(encode(min(lat, 89.999999), wrapped, precision))
    return cells


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(a))
