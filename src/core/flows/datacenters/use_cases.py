"""Datacenters flow: fetch datacenter sites from OpenStreetMap (Overpass API) and store them."""

from __future__ import annotations

import logging
import re
from datetime import date

import pandas as pd

from core.domain.geodata.entities import Datacenter
from core.domain.geodata.repositories import DatacenterRepository
from core.domain.geodata.value_objects import GeoPoint
from core.infrastructure.datacenter_api_service import DatacenterApiService

logger = logging.getLogger(__name__)

# OSM `start_date` is free-form; only exact `YYYY`, `YYYY-MM` or `YYYY-MM-DD` values are
# kept (approximations like "~2010" or "before 2000" are dropped). Missing month/day
# default to 1.
_START_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def _none_if_na[T](value: T) -> T | None:
    return None if pd.isna(value) else value


def parse_start_date(value: object) -> date | None:
    match = _START_DATE.match(str(value).strip()) if value else None
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None


def to_datacenters(df: pd.DataFrame) -> list[Datacenter]:
    """Map the `DatacenterApiService.transform_data` DataFrame to domain entities."""
    datacenters = []
    for row in df.itertuples(index=False):
        latitude, longitude = _none_if_na(row.latitude), _none_if_na(row.longitude)
        if latitude is None or longitude is None:
            continue
        datacenters.append(
            Datacenter(
                external_id=row.external_id,
                name=_none_if_na(row.name) or f"Datacenter {row.external_id}",
                location=GeoPoint(latitude=float(latitude), longitude=float(longitude)),
                operator=_none_if_na(row.operator),
                opened_on=parse_start_date(_none_if_na(row.start_date)),
            )
        )
    return datacenters


def ingest(api_service: DatacenterApiService, repository: DatacenterRepository) -> int:
    """Fetch datacenters from the API and upsert them; returns how many were stored."""
    df = api_service.transform_data(api_service.extract_data())
    saved = repository.save_many(to_datacenters(df))
    logger.info("Stored %d datacenters.", saved)
    return saved


def run() -> str:
    # Imported here, not at module level: flows are Django apps, so this module is
    # imported while Django loads apps, before ORM models can be imported.
    # pylint: disable-next=import-outside-toplevel
    from core.frameworks.django_app.geodata.repositories import DjangoDatacenterRepository

    saved = ingest(DatacenterApiService(), DjangoDatacenterRepository())
    return f"Stored {saved} datacenters."
