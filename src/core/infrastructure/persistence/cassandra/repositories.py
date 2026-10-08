"""Cassandra implementations of the Geodata repository ports (tables: see `schema.py`)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from typing import Any

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.query import SimpleStatement
from cassandra.util import Date
from core.domain.geodata.entities import BirdObservation, Datacenter
from core.domain.geodata.repositories import BirdObservationRepository, DatacenterRepository
from core.domain.geodata.value_objects import GeoPoint

from . import geohash
from .session import get_session

ID_BUCKET_SIZE = 1_000_000
IN_CHUNK = 200  # keep `IN (...)` lookups small
GEOHASH_PRECISION = 4
CONCURRENCY = 64
FETCH_SIZE = 5_000

_BIRD_COLUMNS = "observation_id, common_name, scientific_name, observed_on, latitude, longitude"


def id_bucket(observation_id: int) -> int:
    return observation_id // ID_BUCKET_SIZE


def _to_date(value: Date | date | None) -> date | None:
    return value.date() if isinstance(value, Date) else value


def _to_point(latitude: float | None, longitude: float | None) -> GeoPoint | None:
    if latitude is None or longitude is None:
        return None
    return GeoPoint(latitude=latitude, longitude=longitude)


def _to_observation(row: Any) -> BirdObservation:
    return BirdObservation(
        id=row.observation_id,
        common_name=row.common_name,
        scientific_name=row.scientific_name,
        observed_on=_to_date(row.observed_on),
        location=_to_point(row.latitude, row.longitude),
    )


def _cell(observation: BirdObservation) -> str | None:
    location = observation.location
    if location is None:
        return None
    return geohash.encode(location.latitude, location.longitude, GEOHASH_PRECISION)


def _run(statement: Any, args: Iterable[tuple]) -> None:
    """Execute a prepared statement once per args tuple, concurrently; raises on any error."""
    execute_concurrent_with_args(
        get_session(), statement, list(args), concurrency=CONCURRENCY, raise_on_first_error=True
    )


class CassandraBirdObservationRepository(BirdObservationRepository):
    def __init__(self) -> None:
        session = get_session()
        self._insert = session.prepare(
            "INSERT INTO bird_observations (id_bucket, observation_id, common_name, "
            "scientific_name, observed_on, latitude, longitude, geohash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._insert_by_cell = session.prepare(
            "INSERT INTO bird_observations_by_cell (geohash, observation_id, common_name, "
            "scientific_name, observed_on, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        self._delete_by_cell = session.prepare(
            "DELETE FROM bird_observations_by_cell WHERE geohash = ? AND observation_id = ?"
        )
        self._cells_of = session.prepare(
            "SELECT observation_id, geohash FROM bird_observations "
            "WHERE id_bucket = ? AND observation_id IN ?"
        )
        self._select_cell = session.prepare(
            f"SELECT {_BIRD_COLUMNS} FROM bird_observations_by_cell WHERE geohash = ?"
        )
        self._first_id = session.prepare(
            "SELECT observation_id FROM bird_observations WHERE id_bucket = ? "
            "ORDER BY observation_id ASC LIMIT 1"
        )
        self._last_id = session.prepare(
            "SELECT observation_id FROM bird_observations WHERE id_bucket = ? "
            "ORDER BY observation_id DESC LIMIT 1"
        )

    def _stored_cells(self, ids: list[int]) -> dict[int, str | None]:
        by_bucket: dict[int, list[int]] = defaultdict(list)
        for observation_id in ids:
            by_bucket[id_bucket(observation_id)].append(observation_id)
        args = [
            (bucket, bucket_ids[i : i + IN_CHUNK])
            for bucket, bucket_ids in by_bucket.items()
            for i in range(0, len(bucket_ids), IN_CHUNK)
        ]
        results = execute_concurrent_with_args(
            get_session(), self._cells_of, args, concurrency=CONCURRENCY, raise_on_first_error=True
        )
        return {row.observation_id: row.geohash for _, rows in results for row in rows}

    def save_many(self, observations: list[BirdObservation]) -> int:
        if not observations:
            return 0
        observations = list({o.id: o for o in observations}.values())
        cells = {o.id: _cell(o) for o in observations}
        stored = self._stored_cells(list(cells))
        # An observation whose location changed leaves a row in its previous cell.
        _run(
            self._delete_by_cell,
            ((old, i) for i, old in stored.items() if old is not None and old != cells[i]),
        )
        _run(
            self._insert,
            (
                (
                    id_bucket(o.id),
                    o.id,
                    o.common_name,
                    o.scientific_name,
                    o.observed_on,
                    o.location.latitude if o.location else None,
                    o.location.longitude if o.location else None,
                    cells[o.id],
                )
                for o in observations
            ),
        )
        _run(
            self._insert_by_cell,
            (
                (
                    cells[o.id],
                    o.id,
                    o.common_name,
                    o.scientific_name,
                    o.observed_on,
                    o.location.latitude,
                    o.location.longitude,
                )
                for o in observations
                if o.location is not None
            ),
        )
        return len(observations)

    def iter_all(self) -> Iterator[BirdObservation]:
        """Stream every observation, paging through the table."""
        statement = SimpleStatement(
            f"SELECT {_BIRD_COLUMNS} FROM bird_observations", fetch_size=FETCH_SIZE
        )
        for row in get_session().execute(statement):
            yield _to_observation(row)

    def list_all(self) -> list[BirdObservation]:
        return list(self.iter_all())

    def id_bounds(self) -> tuple[int, int] | None:
        session = get_session()
        statement = SimpleStatement(
            "SELECT DISTINCT id_bucket FROM bird_observations", fetch_size=FETCH_SIZE
        )
        buckets = [row.id_bucket for row in session.execute(statement)]
        if not buckets:
            return None
        low = session.execute(self._first_id, (min(buckets),)).one()
        high = session.execute(self._last_id, (max(buckets),)).one()
        return low.observation_id, high.observation_id

    def list_near(
        self,
        center: GeoPoint,
        radius_m: float,
        observed_from: date | None = None,
        observed_to: date | None = None,
    ) -> list[BirdObservation]:
        cells = geohash.cover(center.latitude, center.longitude, radius_m, GEOHASH_PRECISION)
        results = execute_concurrent_with_args(
            get_session(),
            self._select_cell,
            [(cell,) for cell in cells],
            concurrency=CONCURRENCY,
            raise_on_first_error=True,
            results_generator=True,
        )
        observations = []
        for _, rows in results:
            for row in rows:
                observed_on = _to_date(row.observed_on)
                if observed_from is not None and (
                    observed_on is None or observed_on < observed_from
                ):
                    continue
                if observed_to is not None and (observed_on is None or observed_on > observed_to):
                    continue
                distance = geohash.haversine_m(
                    center.latitude, center.longitude, row.latitude, row.longitude
                )
                if distance <= radius_m:
                    observations.append(_to_observation(row))
        return observations


class CassandraDatacenterRepository(DatacenterRepository):
    def __init__(self) -> None:
        self._insert = get_session().prepare(
            "INSERT INTO datacenters (external_id, name, operator, opened_on, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )

    def save_many(self, datacenters: list[Datacenter]) -> int:
        _run(
            self._insert,
            (
                (
                    d.external_id,
                    d.name,
                    d.operator,
                    d.opened_on,
                    d.location.latitude,
                    d.location.longitude,
                )
                for d in datacenters
            ),
        )
        return len(datacenters)

    def list_all(self) -> list[Datacenter]:
        statement = SimpleStatement(
            "SELECT external_id, name, operator, opened_on, latitude, longitude FROM datacenters",
            fetch_size=FETCH_SIZE,
        )
        return [
            Datacenter(
                external_id=row.external_id,
                name=row.name,
                operator=row.operator,
                opened_on=_to_date(row.opened_on),
                location=GeoPoint(latitude=row.latitude, longitude=row.longitude),
            )
            for row in get_session().execute(statement)
        ]
