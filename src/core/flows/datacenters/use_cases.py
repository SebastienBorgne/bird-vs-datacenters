"""Datacenters flow: wires OpenStreetMap (Overpass) and Cassandra into the ingestion use case."""

from __future__ import annotations

from core.application.geodata.use_cases import GeodataUseCases
from core.infrastructure.persistence.cassandra.repositories import (
    CassandraBirdObservationRepository,
    CassandraDatacenterRepository,
)
from core.infrastructure.sources.overpass import OverpassSource


def run() -> str:
    use_cases = GeodataUseCases(
        CassandraBirdObservationRepository(), CassandraDatacenterRepository()
    )
    saved = use_cases.ingest_datacenters(OverpassSource())
    return f"Stored {saved} datacenters."
