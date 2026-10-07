"""Service to retrieve datacenter sites from OpenStreetMap through the public Overpass API.

OSM tags datacenters with `telecom=data_center` (and sometimes only
`building=data_center`). Buildings are ways/relations, so `out center`
asks Overpass for a single representative point per element. Data is
© OpenStreetMap contributors, under the ODbL.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests
from requests.exceptions import RequestException

from core.settings import config

logger = logging.getLogger(__name__)

COLUMNS = ["external_id", "name", "operator", "start_date", "latitude", "longitude"]


class DatacenterApiService:
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

    def extract_data(self) -> dict[str, list[dict[str, Any]]]:
        """Raw Overpass elements, keyed by country code ("" for a worldwide query)."""
        if not self.countries:
            return {"": self._fetch(self.build_query(None))}
        return {country: self._fetch(self.build_query(country)) for country in self.countries}

    def transform_data(self, payload: dict[str, list[dict[str, Any]]]) -> pd.DataFrame:
        records = {}
        for elements in payload.values():
            for element in elements:
                tags = element.get("tags") or {}
                center = element.get("center") or element
                external_id = f"osm:{element.get('type')}/{element.get('id')}"
                records[external_id] = {
                    "external_id": external_id,
                    "name": tags.get("name") or tags.get("ref") or tags.get("operator"),
                    "operator": tags.get("operator"),
                    "start_date": tags.get("start_date"),
                    "latitude": center.get("lat"),
                    "longitude": center.get("lon"),
                }

        return pd.DataFrame.from_records(list(records.values()), columns=COLUMNS)
