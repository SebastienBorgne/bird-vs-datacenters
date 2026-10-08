"""Service to retrieve bird observations from the iNaturalist API, one page at a time.

Pages are addressed by observation id (`id_above` / `id_below`) rather than
page number: iNaturalist caps `page * per_page` at 10,000, while an id cursor
can walk the whole (tens of millions) result set.
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

PER_PAGE = 200  # iNaturalist's maximum


class BirdApiService:
    def __init__(self, retries: int = 4, backoff_s: float = 5.0):
        self.api_url = config.bird_api.BIRD_API_URL
        self.delay_s = config.bird_api.BIRD_API_DELAY_S
        self.retries = retries
        self.backoff_s = backoff_s
        self._last_request_at = 0.0

    def extract_data(
        self, id_above: int | None = None, id_below: int | None = None
    ) -> dict[str, Any]:
        """One page of observations, ordered by id: ascending above `id_above`, else descending
        (from the newest, or below `id_below`). Returns `{}` once retries are exhausted.
        """
        params: dict[str, Any] = {"per_page": PER_PAGE, "order_by": "id"}
        if id_above is not None:
            params.update(order="asc", id_above=id_above)
        else:
            params.update(order="desc")
            if id_below is not None:
                params["id_below"] = id_below

        for attempt in range(1, self.retries + 1):
            # Throttle to iNaturalist's recommended request rate.
            time.sleep(max(0.0, self._last_request_at + self.delay_s - time.monotonic()))
            self._last_request_at = time.monotonic()
            try:
                response = requests.get(
                    self.api_url,
                    params=params,
                    headers={"User-Agent": "birdy/0.1 (bird-vs-datacenters)"},
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
            except (RequestException, ValueError) as e:
                logger.warning("iNaturalist request failed (attempt %d): %s", attempt, e)
                if attempt < self.retries:
                    time.sleep(self.backoff_s * 2 ** (attempt - 1))
        return {}

    def transform_data(self, payload: dict[str, Any]) -> pd.DataFrame:
        observations = payload.get("results", []) if isinstance(payload, dict) else []
        records = []

        for observation in observations:
            taxon = observation.get("taxon") or {}
            coordinates = (observation.get("geojson") or {}).get("coordinates") or []
            longitude = coordinates[0] if len(coordinates) >= 2 else None
            latitude = coordinates[1] if len(coordinates) >= 2 else None

            records.append(
                {
                    "observation_id": observation.get("id"),
                    "common_name": taxon.get("preferred_common_name")
                    or observation.get("species_guess"),
                    "scientific_name": taxon.get("name"),
                    "observed_on": observation.get("observed_on"),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        return pd.DataFrame.from_records(
            records,
            columns=[
                "observation_id",
                "common_name",
                "scientific_name",
                "observed_on",
                "latitude",
                "longitude",
            ],
        )
