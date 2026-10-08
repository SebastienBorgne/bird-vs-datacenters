"""Bird observations flow: wires iNaturalist and Cassandra into the ingestion use case."""

from __future__ import annotations

from core.application.geodata.use_cases import GeodataUseCases
from core.infrastructure.persistence.cassandra.repositories import (
    CassandraBirdObservationRepository,
    CassandraDatacenterRepository,
)
from core.infrastructure.sources.inaturalist import INaturalistSource
from core.settings import config


def run(max_pages: int | None = None) -> str:
    use_cases = GeodataUseCases(
        CassandraBirdObservationRepository(), CassandraDatacenterRepository()
    )
    report = use_cases.ingest_bird_observations(
        INaturalistSource(), max_pages or config.bird_api.BIRD_API_MAX_PAGES
    )
    status = " (stopped early: source unavailable)" if report.interrupted else ""
    return (
        f"Stored {report.saved} bird observations in {report.pages} page(s){status}; "
        f"stored id range: {report.id_bounds}."
    )
