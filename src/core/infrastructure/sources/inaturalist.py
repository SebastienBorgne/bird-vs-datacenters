"""iNaturalist adapter for `BirdObservationSource`.

Pages are addressed by observation id (`id_above` / `id_below`) rather than
page number: iNaturalist caps `page * per_page` at 10,000, while an id cursor
can walk the whole (tens of millions) result set. Filters (taxon, geo, ...)
come from the query string of `BIRD_API_URL`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.application.geodata.ports import BirdObservationSource, ObservationPage
from core.domain.geodata.entities import BirdObservation
from core.domain.geodata.value_objects import GeoPoint
from core.settings import config

from .http import ThrottledJsonClient

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
        # Throttled to iNaturalist's recommended request rate.
        self.client = ThrottledJsonClient(
            "iNaturalist", config.bird_api.BIRD_API_DELAY_S, retries, backoff_s
        )

    def newer_than(self, observation_id: int) -> ObservationPage:
        return self._page({"order": "asc", "id_above": observation_id})

    def older_than(self, observation_id: int | None) -> ObservationPage:
        params: dict[str, Any] = {"order": "desc"}
        if observation_id is not None:
            params["id_below"] = observation_id
        return self._page(params)

    def _page(self, params: dict[str, Any]) -> ObservationPage:
        results = self.client.get(
            self.api_url, {"per_page": PER_PAGE, "order_by": "id", **params}
        ).get("results", [])
        observations = [o for o in map(to_observation, results) if o is not None]
        return ObservationPage(observations=observations, has_more=len(results) >= PER_PAGE)
