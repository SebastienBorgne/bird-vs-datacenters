"""OpenStreetMap (public Overpass API) adapter for `DatacenterSource`.

OSM tags datacenters with `telecom=data_center` (and sometimes only
`building=data_center`). Buildings are ways/relations, so `out center`
asks Overpass for a single representative point per element. Data is
© OpenStreetMap contributors, under the ODbL.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
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


def to_datacenter(element: dict[str, Any]) -> Datacenter | None:
    """Map one Overpass element to the domain; `None` when it has no position."""
    tags = element.get("tags") or {}
    center = element.get("center") or element
    if center.get("lat") is None or center.get("lon") is None:
        return None
    external_id = f"osm:{element.get('type')}/{element.get('id')}"
    return Datacenter(
        external_id=external_id,
        name=tags.get("name")
        or tags.get("ref")
        or tags.get("operator")
        or f"Datacenter {external_id}",
        location=GeoPoint(latitude=float(center["lat"]), longitude=float(center["lon"])),
        operator=tags.get("operator"),
        opened_on=parse_start_date(tags.get("start_date")),
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
            "out center tags;"
        )

    def fetch_all(self) -> list[Datacenter]:
        """Queried one country at a time (or worldwide when none is configured). A country
        that keeps failing is skipped, so one Overpass hiccup doesn't lose the others.
        """
        scopes: list[str | None] = list(self.countries) or [None]
        datacenters: dict[str, Datacenter] = {}
        for scope in scopes:
            for element in self._fetch(self.build_query(scope)):
                datacenter = to_datacenter(element)
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
