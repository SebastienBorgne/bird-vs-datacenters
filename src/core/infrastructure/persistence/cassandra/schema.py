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
- `bird_observations_by_month`: the dated observations partitioned by month
  ("2026-09") and shard (observation id % 8, so a busy month stays in
  bounded partitions), for reading a period without scanning everything
  (`list_observed_between`).
- `datacenters`: keyed by source id; small enough to scan.
- `datacenter_power_estimates`: estimated IT power and yearly energy use of
  each datacenter, keyed like `datacenters` (same size, scanned too).
- `weather_daily`: daily weather of each datacenter region (1° grid cell,
  e.g. "38_-78"), one partition per region clustered by day. Serves upserts,
  a region's time series and the ingestion cursor (`day_bounds`: first/last
  row of the partition). The cell center is a static column.
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
    CREATE TABLE IF NOT EXISTS bird_observations_by_month (
        month text,
        shard int,
        observation_id bigint,
        common_name text,
        scientific_name text,
        observed_on date,
        latitude double,
        longitude double,
        PRIMARY KEY ((month, shard), observation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacenters (
        external_id text PRIMARY KEY,
        name text,
        operator text,
        opened_on date,
        latitude double,
        longitude double,
        country text,
        footprint_m2 double,
        levels int
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacenter_power_estimates (
        external_id text PRIMARY KEY,
        country text,
        year int,
        basis text,
        it_power_mw double,
        energy_gwh double
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS weather_daily (
        region text,
        day date,
        latitude double STATIC,
        longitude double STATIC,
        temperature_mean_c double,
        temperature_max_c double,
        temperature_min_c double,
        precipitation_mm double,
        wind_speed_max_kmh double,
        relative_humidity_mean_pct double,
        PRIMARY KEY ((region), day)
    ) WITH CLUSTERING ORDER BY (day ASC)
    """,
]


# Columns added after their table was created: `CREATE TABLE IF NOT EXISTS` leaves an
# existing table as it is.
ADDED_COLUMNS = [
    "ALTER TABLE datacenters ADD IF NOT EXISTS country text",
    "ALTER TABLE datacenters ADD IF NOT EXISTS footprint_m2 double",
    "ALTER TABLE datacenters ADD IF NOT EXISTS levels int",
]


def create_schema() -> None:
    settings = config.cassandra
    session = get_cluster().connect()
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {settings.KEYSPACE} WITH replication = "
        f"{{'class': 'SimpleStrategy', 'replication_factor': {settings.REPLICATION_FACTOR}}}"
    )
    session.set_keyspace(settings.KEYSPACE)
    for statement in [*TABLES, *ADDED_COLUMNS]:
        session.execute(statement)
    get_cluster().control_connection.wait_for_schema_agreement()
    logger.info("Cassandra schema ready in keyspace %r.", settings.KEYSPACE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_schema()
