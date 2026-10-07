"""Bird observations flow: fetch observations from the bird API and store them."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.domain.geodata.entities import BirdObservation
from core.domain.geodata.repositories import BirdObservationRepository
from core.domain.geodata.value_objects import GeoPoint
from core.infrastructure.bird_api_service import BirdApiService

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


def ingest(api_service: BirdApiService, repository: BirdObservationRepository) -> int:
    """Fetch observations from the API and upsert them; returns how many were stored."""
    df = api_service.transform_data(api_service.extract_data())
    saved = repository.save_many(to_observations(df))
    logger.info("Stored %d bird observations.", saved)
    return saved


def run() -> str:
    # Imported here, not at module level: flows are Django apps, so this module is
    # imported while Django loads apps, before ORM models can be imported.
    # pylint: disable-next=import-outside-toplevel
    from core.frameworks.django_app.geodata.repositories import DjangoBirdObservationRepository

    saved = ingest(BirdApiService(), DjangoBirdObservationRepository())
    return f"Stored {saved} bird observations."
