"""OpenStreetMap (public Overpass API) adapter for `DatacenterSource`.

OSM tags datacenters with `telecom=data_center` (and sometimes only
`building=data_center`). Buildings are ways/relations: `out geom` returns
their outline, which gives their footprint, and their bounding box, whose
center is the datacenter's position (the same point `out center` gives).
Data is © OpenStreetMap contributors, under the ODbL.
"""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import date
from itertools import pairwise
from typing import Any

import requests
from requests.exceptions import RequestException

from core.application.geodata.ports import DatacenterSource
from core.domain.geodata.entities import Datacenter
from core.domain.geodata.value_objects import GeoPoint
from core.settings import config

logger = logging.getLogger(__name__)

# OSM `start_date` is free-form; only exact `YYYY`, `YYYY-MM` or `YYYY-MM-DD` values are
# kept (approximations like "~2010" or "before 2000" are dropped). Missing month/day
# default to 1.
_START_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def parse_start_date(value: str | None) -> date | None:
    match = _START_DATE.match(value.strip()) if value else None
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None


def parse_levels(value: str | None) -> int | None:
    """`building:levels` as a positive whole number; `None` when missing or unparsable."""
    try:
        levels = round(float(value)) if value else 0
    except ValueError:
        return None
    return levels if levels > 0 else None


EARTH_RADIUS_M = 6_371_008.8


def ring_area_m2(points: list[dict[str, float]]) -> float | None:
    """Area of a closed ring of `{"lat", "lon"}` points; `None` when it isn't closed.

    Projected on a plane tangent at its first point, which is precise enough at the
    scale of a building or a campus.
    """
    if len(points) < 4 or points[0] != points[-1]:
        return None
    lat0 = math.radians(points[0]["lat"])
    xy = [
        (
            math.radians(p["lon"]) * math.cos(lat0) * EARTH_RADIUS_M,
            math.radians(p["lat"]) * EARTH_RADIUS_M,
        )
        for p in points
    ]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(xy))) / 2


def footprint_m2(element: dict[str, Any]) -> float | None:
    """Ground area of a way or multipolygon relation; `None` for nodes, open ways, and
    relations whose rings are split across several ways (not reassembled here).
    """
    if element.get("type") == "way":
        return ring_area_m2(element.get("geometry") or [])
    if element.get("type") != "relation":
        return None
    total = 0.0
    for member in element.get("members") or []:
        if member.get("type") != "way" or member.get("role") not in ("outer", "inner"):
            continue
        area = ring_area_m2(member.get("geometry") or [])
        if area is None:
            return None
        total += area if member["role"] == "outer" else -area
    return total if total > 0 else None


def position(element: dict[str, Any]) -> GeoPoint | None:
    """A node's own position, otherwise the center of the element's bounding box."""
    if element.get("lat") is not None and element.get("lon") is not None:
        return GeoPoint(latitude=float(element["lat"]), longitude=float(element["lon"]))
    bounds = element.get("bounds")
    if not bounds:
        return None
    return GeoPoint(
        latitude=(bounds["minlat"] + bounds["maxlat"]) / 2,
        longitude=(bounds["minlon"] + bounds["maxlon"]) / 2,
    )


def to_datacenter(element: dict[str, Any], country: str | None = None) -> Datacenter | None:
    """Map one Overpass element to the domain; `None` when it has no position.

    `country` is the country it was queried in; worldwide queries fall back to its
    `addr:country` tag.
    """
    tags = element.get("tags") or {}
    location = position(element)
    if location is None:
        return None
    external_id = f"osm:{element.get('type')}/{element.get('id')}"
    return Datacenter(
        external_id=external_id,
        name=tags.get("name")
        or tags.get("ref")
        or tags.get("operator")
        or f"Datacenter {external_id}",
        location=location,
        operator=tags.get("operator"),
        opened_on=parse_start_date(tags.get("start_date")),
        country=country or (tags.get("addr:country") or "").strip().upper() or None,
        footprint_m2=footprint_m2(element),
        levels=parse_levels(tags.get("building:levels")),
    )


class OverpassSource(DatacenterSource):
    def __init__(self, retries: int = 3, backoff_s: float = 10.0):
        self.api_url = config.datacenter_api.OVERPASS_API_URL
        countries = config.datacenter_api.DATACENTER_COUNTRIES or ""
        self.countries = [c.strip().upper() for c in countries.split(",") if c.strip()]
        self.retries = retries
        self.backoff_s = backoff_s

    @staticmethod
    def build_query(country: str | None) -> str:
        if country is None:
            area, scope = "", ""
        else:
            area = f'area["ISO3166-1"="{country}"][admin_level=2]->.a;'
            scope = "(area.a)"
        return (
            "[out:json][timeout:180];"
            f"{area}"
            f'(nwr["telecom"="data_center"]{scope};nwr["building"="data_center"]{scope};);'
            "out tags geom;"
        )

    def fetch_all(self) -> list[Datacenter]:
        """Queried one country at a time (or worldwide when none is configured). A country
        that keeps failing is skipped, so one Overpass hiccup doesn't lose the others.
        """
        scopes: list[str | None] = list(self.countries) or [None]
        datacenters: dict[str, Datacenter] = {}
        for scope in scopes:
            for element in self._fetch(self.build_query(scope)):
                datacenter = to_datacenter(element, scope)
                if datacenter is not None:
                    datacenters[datacenter.external_id] = datacenter
        return list(datacenters.values())

    def _fetch(self, query: str) -> list[dict[str, Any]]:
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    self.api_url,
                    data={"data": query},
                    headers={"User-Agent": "birdy/0.1 (bird-vs-datacenters)"},
                    timeout=200,
                )
                response.raise_for_status()
                # A busy Overpass server answers 200 with an HTML error page.
                return response.json().get("elements", [])
            except (RequestException, ValueError) as e:
                logger.warning("Overpass request failed (attempt %d): %s", attempt, e)
                if attempt < self.retries:
                    time.sleep(self.backoff_s * attempt)
        return []
