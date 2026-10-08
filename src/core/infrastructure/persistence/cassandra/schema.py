"""Cassandra keyspace and tables for the Geodata context — idempotent, like a migration.

Run by the compose `init` service: `python -m core.infrastructure.persistence.cassandra.schema`.

One table per query, as usual with Cassandra:

- `bird_observations`: the observations, partitioned by id bucket (id // 1M)
  so partitions stay small, clustered by id. Serves upserts by id, full scans
  and the ingestion cursor (`id_bounds`: first/last row of the lowest/highest
  bucket). `geohash` records which `bird_observations_by_cell` row to replace
  when an observation moves.
- `bird_observations_by_cell`: the same observations partitioned by geohash
  cell, for distance queries (`list_near`).
- `datacenters`: keyed by source id; small enough to scan.
"""

from __future__ import annotations

import logging

from core.settings import config

from .session import get_cluster

logger = logging.getLogger(__name__)

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS bird_observations (
        id_bucket bigint,
        observation_id bigint,
        common_name text,
        scientific_name text,
        observed_on date,
        latitude double,
        longitude double,
        geohash text,
        PRIMARY KEY ((id_bucket), observation_id)
    ) WITH CLUSTERING ORDER BY (observation_id ASC)
    """,
    """
    CREATE TABLE IF NOT EXISTS bird_observations_by_cell (
        geohash text,
        observation_id bigint,
        common_name text,
        scientific_name text,
        observed_on date,
        latitude double,
        longitude double,
        PRIMARY KEY ((geohash), observation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacenters (
        external_id text PRIMARY KEY,
        name text,
        operator text,
        opened_on date,
        latitude double,
        longitude double
    )
    """,
]


def create_schema() -> None:
    settings = config.cassandra
    session = get_cluster().connect()
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {settings.KEYSPACE} WITH replication = "
        f"{{'class': 'SimpleStrategy', 'replication_factor': {settings.REPLICATION_FACTOR}}}"
    )
    session.set_keyspace(settings.KEYSPACE)
    for statement in TABLES:
        session.execute(statement)
    get_cluster().control_connection.wait_for_schema_agreement()
    logger.info("Cassandra schema ready in keyspace %r.", settings.KEYSPACE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_schema()
