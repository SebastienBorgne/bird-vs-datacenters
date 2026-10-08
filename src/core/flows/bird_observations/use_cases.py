"""Bird observations flow: incrementally fetch observations from iNaturalist and store them.

Each run walks the API by observation id from what is already stored, so the
db keeps a contiguous id range that grows on both ends:

- forward: observations newer than the highest stored id (up to half the page
  budget, so a backlog of new ones never starves the backfill);
- backfill: observations older than the lowest stored id, with what's left.

The cursor is derived from the stored ids (`id_bounds`), and every page is
saved as soon as it is fetched, so an interrupted run loses nothing.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.domain.geodata.entities import BirdObservation
from core.domain.geodata.repositories import BirdObservationRepository
from core.domain.geodata.value_objects import GeoPoint
from core.infrastructure.bird_api_service import PER_PAGE, BirdApiService
from core.settings import config

logger = logging.getLogger(__name__)


def _none_if_na[T](value: T) -> T | None:
    return None if pd.isna(value) else value


def to_observations(df: pd.DataFrame) -> list[BirdObservation]:
    """Map the `BirdApiService.transform_data` DataFrame to domain entities."""
    observations = []
    for row in df.itertuples(index=False):
        if pd.isna(row.observation_id):
            continue
        latitude, longitude = _none_if_na(row.latitude), _none_if_na(row.longitude)
        observed_on = _none_if_na(row.observed_on)
        observations.append(
            BirdObservation(
                id=int(row.observation_id),
                common_name=_none_if_na(row.common_name),
                scientific_name=_none_if_na(row.scientific_name),
                observed_on=date.fromisoformat(observed_on) if observed_on else None,
                location=(
                    GeoPoint(latitude=float(latitude), longitude=float(longitude))
                    if latitude is not None and longitude is not None
                    else None
                ),
            )
        )
    return observations


def _ingest_page(
    api_service: BirdApiService,
    repository: BirdObservationRepository,
    id_above: int | None = None,
    id_below: int | None = None,
) -> tuple[list[int], bool]:
    """Fetch and store one page; returns the page's observation ids and whether it was full."""
    payload = api_service.extract_data(id_above=id_above, id_below=id_below)
    observations = to_observations(api_service.transform_data(payload))
    repository.save_many(observations)
    return [o.id for o in observations], len(payload.get("results", [])) >= PER_PAGE


def ingest(
    api_service: BirdApiService, repository: BirdObservationRepository, max_pages: int
) -> int:
    """Fetch up to `max_pages` pages, newest first then backfill; returns how many were stored."""
    saved, pages = 0, 0
    bounds = repository.id_bounds()

    if bounds is not None:
        high = bounds[1]
        while pages < max(1, max_pages // 2):
            ids, full = _ingest_page(api_service, repository, id_above=high)
            pages, saved = pages + 1, saved + len(ids)
            if ids:
                high = max(ids)
            if not full:
                break  # caught up with the newest observations
        logger.info("Forward: %d new observations after %d page(s).", saved, pages)

    low = bounds[0] if bounds is not None else None
    while pages < max_pages:
        ids, full = _ingest_page(api_service, repository, id_below=low)
        pages, saved = pages + 1, saved + len(ids)
        if ids:
            low = min(ids)
        logger.info(
            "Backfill page %d/%d: %d observations, below id %s.", pages, max_pages, len(ids), low
        )
        if not full:
            break  # reached the oldest observation, or retries exhausted

    logger.info("Stored %d bird observations in %d page(s).", saved, pages)
    return saved


def run(max_pages: int | None = None) -> str:
    # Imported here, not at module level: flows are Django apps, so this module is
    # imported while Django loads apps, before ORM models can be imported.
    # pylint: disable-next=import-outside-toplevel
    from core.frameworks.django_app.geodata.repositories import DjangoBirdObservationRepository

    repository = DjangoBirdObservationRepository()
    pages = max_pages or config.bird_api.BIRD_API_MAX_PAGES
    saved = ingest(BirdApiService(), repository, pages)
    bounds = repository.id_bounds()
    return f"Stored {saved} bird observations (stored id range: {bounds})."
