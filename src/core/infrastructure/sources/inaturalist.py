"""iNaturalist adapter for `BirdObservationSource`.

Pages are addressed by observation id (`id_above` / `id_below`) rather than
page number: iNaturalist caps `page * per_page` at 10,000, while an id cursor
can walk the whole (tens of millions) result set. Filters (taxon, geo, ...)
come from the query string of `BIRD_API_URL`.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import requests
from requests.exceptions import RequestException

from core.application.geodata.ports import (
    BirdObservationSource,
    ObservationPage,
    SourceUnavailableError,
)
from core.domain.geodata.entities import BirdObservation
from core.domain.geodata.value_objects import GeoPoint
from core.settings import config

logger = logging.getLogger(__name__)

PER_PAGE = 200  # iNaturalist's maximum


def to_observation(result: dict[str, Any]) -> BirdObservation | None:
    """Map one API result to the domain; `None` when it has no id."""
    if result.get("id") is None:
        return None
    taxon = result.get("taxon") or {}
    coordinates = (result.get("geojson") or {}).get("coordinates") or []
    observed_on = result.get("observed_on")
    return BirdObservation(
        id=int(result["id"]),
        common_name=taxon.get("preferred_common_name") or result.get("species_guess"),
        scientific_name=taxon.get("name"),
        observed_on=date.fromisoformat(observed_on) if observed_on else None,
        location=(
            GeoPoint(latitude=float(coordinates[1]), longitude=float(coordinates[0]))
            if len(coordinates) >= 2
            else None
        ),
    )


class INaturalistSource(BirdObservationSource):
    def __init__(self, retries: int = 4, backoff_s: float = 5.0):
        self.api_url = config.bird_api.BIRD_API_URL
        self.delay_s = config.bird_api.BIRD_API_DELAY_S
        self.retries = retries
        self.backoff_s = backoff_s
        self._last_request_at = 0.0

    def newer_than(self, observation_id: int) -> ObservationPage:
        return self._page({"order": "asc", "id_above": observation_id})

    def older_than(self, observation_id: int | None) -> ObservationPage:
        params: dict[str, Any] = {"order": "desc"}
        if observation_id is not None:
            params["id_below"] = observation_id
        return self._page(params)

    def _page(self, params: dict[str, Any]) -> ObservationPage:
        results = self._get({"per_page": PER_PAGE, "order_by": "id", **params}).get("results", [])
        observations = [o for o in map(to_observation, results) if o is not None]
        return ObservationPage(observations=observations, has_more=len(results) >= PER_PAGE)

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
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
                if attempt == self.retries:
                    raise SourceUnavailableError(f"iNaturalist: {e}") from e
                time.sleep(self.backoff_s * 2 ** (attempt - 1))
        raise AssertionError("unreachable")
