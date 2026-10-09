"""Cassandra implementations of the Geodata repository ports (tables: see `schema.py`)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from typing import Any

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.query import SimpleStatement
from cassandra.util import Date
from core.domain.geodata.entities import (
    BirdObservation,
    DailyWeather,
    Datacenter,
    DatacenterPowerEstimate,
)
from core.domain.geodata.repositories import (
    BirdObservationRepository,
    DailyWeatherRepository,
    DatacenterPowerEstimateRepository,
    DatacenterRepository,
)
from core.domain.geodata.value_objects import GeoPoint, GridCell

from . import geohash
from .session import get_session

ID_BUCKET_SIZE = 1_000_000
IN_CHUNK = 200  # keep `IN (...)` lookups small
GEOHASH_PRECISION = 4
# Partitions per month in `bird_observations_by_month`, by observation id: a busy month
# holds millions of observations, too many for one partition.
MONTH_SHARDS = 8
CONCURRENCY = 64
FETCH_SIZE = 5_000

_BIRD_COLUMNS = "observation_id, common_name, scientific_name, observed_on, latitude, longitude"
_DATACENTER_COLUMNS = (
    "external_id, name, operator, opened_on, latitude, longitude, country, footprint_m2, levels"
)
_POWER_ESTIMATE_COLUMNS = "external_id, country, year, basis, it_power_mw, energy_gwh"
_WEATHER_METRICS = (
    "temperature_mean_c",
    "temperature_max_c",
    "temperature_min_c",
    "precipitation_mm",
    "wind_speed_max_kmh",
    "relative_humidity_mean_pct",
)


def id_bucket(observation_id: int) -> int:
    return observation_id // ID_BUCKET_SIZE


def _to_date(value: Date | date | None) -> date | None:
    return value.date() if isinstance(value, Date) else value


def _to_day(value: Date | date) -> date:
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


def _month(day: date | None) -> str | None:
    return f"{day:%Y-%m}" if day is not None else None


def _months(start: date, end: date) -> list[str]:
    """Every month from `start` to `end` (inclusive), as "YYYY-MM"."""
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


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
        self._insert_by_month = session.prepare(
            "INSERT INTO bird_observations_by_month (month, shard, observation_id, common_name, "
            "scientific_name, observed_on, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._delete_by_month = session.prepare(
            "DELETE FROM bird_observations_by_month "
            "WHERE month = ? AND shard = ? AND observation_id = ?"
        )
        self._select_month = session.prepare(
            f"SELECT {_BIRD_COLUMNS} FROM bird_observations_by_month WHERE month = ? AND shard = ?"
        )
        self._select_month.fetch_size = FETCH_SIZE
        self._stored_of = session.prepare(
            "SELECT observation_id, geohash, observed_on FROM bird_observations "
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

    def _stored(self, ids: list[int]) -> dict[int, tuple[str | None, str | None]]:
        """(geohash cell, month) each already stored observation is indexed under."""
        by_bucket: dict[int, list[int]] = defaultdict(list)
        for observation_id in ids:
            by_bucket[id_bucket(observation_id)].append(observation_id)
        args = [
            (bucket, bucket_ids[i : i + IN_CHUNK])
            for bucket, bucket_ids in by_bucket.items()
            for i in range(0, len(bucket_ids), IN_CHUNK)
        ]
        results = execute_concurrent_with_args(
            get_session(), self._stored_of, args, concurrency=CONCURRENCY, raise_on_first_error=True
        )
        return {
            row.observation_id: (row.geohash, _month(_to_date(row.observed_on)))
            for _, rows in results
            for row in rows
        }

    def save_many(self, observations: list[BirdObservation]) -> int:
        if not observations:
            return 0
        observations = list({o.id: o for o in observations}.values())
        cells = {o.id: _cell(o) for o in observations}
        months = {o.id: _month(o.observed_on) for o in observations}
        stored = self._stored(list(cells))
        # An observation whose location (or date) changed leaves a row in its previous
        # cell (or month).
        _run(
            self._delete_by_cell,
            ((old, i) for i, (old, _) in stored.items() if old is not None and old != cells[i]),
        )
        _run(
            self._delete_by_month,
            (
                (old, i % MONTH_SHARDS, i)
                for i, (_, old) in stored.items()
                if old is not None and old != months[i]
            ),
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
        _run(
            self._insert_by_month,
            (
                (
                    months[o.id],
                    o.id % MONTH_SHARDS,
                    o.id,
                    o.common_name,
                    o.scientific_name,
                    o.observed_on,
                    o.location.latitude if o.location else None,
                    o.location.longitude if o.location else None,
                )
                for o in observations
                if o.observed_on is not None
            ),
        )
        return len(observations)

    def iter_observed_between(
        self, observed_from: date, observed_to: date
    ) -> Iterator[BirdObservation]:
        """Stream the observations dated `observed_from`..`observed_to`, reading only
        those months' partitions (concurrently).
        """
        args = [
            (month, shard)
            for month in _months(observed_from, observed_to)
            for shard in range(MONTH_SHARDS)
        ]
        results = execute_concurrent_with_args(
            get_session(),
            self._select_month,
            args,
            concurrency=CONCURRENCY,
            raise_on_first_error=True,
            results_generator=True,
        )
        for _, rows in results:
            for row in rows:
                observed_on = _to_day(row.observed_on)
                if observed_from <= observed_on <= observed_to:
                    yield _to_observation(row)

    def list_observed_between(
        self, observed_from: date, observed_to: date
    ) -> list[BirdObservation]:
        return list(self.iter_observed_between(observed_from, observed_to))

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
            f"INSERT INTO datacenters ({_DATACENTER_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                    d.country,
                    d.footprint_m2,
                    d.levels,
                )
                for d in datacenters
            ),
        )
        return len(datacenters)

    def list_all(self) -> list[Datacenter]:
        statement = SimpleStatement(
            f"SELECT {_DATACENTER_COLUMNS} FROM datacenters", fetch_size=FETCH_SIZE
        )
        return [
            Datacenter(
                external_id=row.external_id,
                name=row.name,
                operator=row.operator,
                opened_on=_to_date(row.opened_on),
                location=GeoPoint(latitude=row.latitude, longitude=row.longitude),
                country=row.country,
                footprint_m2=row.footprint_m2,
                levels=row.levels,
            )
            for row in get_session().execute(statement)
        ]


class CassandraDatacenterPowerEstimateRepository(DatacenterPowerEstimateRepository):
    def __init__(self) -> None:
        self._insert = get_session().prepare(
            f"INSERT INTO datacenter_power_estimates ({_POWER_ESTIMATE_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )

    def save_many(self, estimates: list[DatacenterPowerEstimate]) -> int:
        _run(
            self._insert,
            (
                (e.external_id, e.country, e.year, e.basis, e.it_power_mw, e.energy_gwh)
                for e in estimates
            ),
        )
        return len(estimates)

    def list_all(self) -> list[DatacenterPowerEstimate]:
        statement = SimpleStatement(
            f"SELECT {_POWER_ESTIMATE_COLUMNS} FROM datacenter_power_estimates",
            fetch_size=FETCH_SIZE,
        )
        return [
            DatacenterPowerEstimate(
                external_id=row.external_id,
                country=row.country,
                year=row.year,
                basis=row.basis,
                it_power_mw=row.it_power_mw,
                energy_gwh=row.energy_gwh,
            )
            for row in get_session().execute(statement)
        ]


class CassandraDailyWeatherRepository(DailyWeatherRepository):
    def __init__(self) -> None:
        session = get_session()
        metrics = ", ".join(_WEATHER_METRICS)
        self._insert = session.prepare(
            f"INSERT INTO weather_daily (region, day, latitude, longitude, {metrics}) "
            f"VALUES (?, ?, ?, ?, {', '.join('?' * len(_WEATHER_METRICS))})"
        )
        self._select_region = session.prepare(
            f"SELECT day, {metrics} FROM weather_daily WHERE region = ?"
        )
        self._first_day = session.prepare(
            "SELECT day FROM weather_daily WHERE region = ? ORDER BY day ASC LIMIT 1"
        )
        self._last_day = session.prepare(
            "SELECT day FROM weather_daily WHERE region = ? ORDER BY day DESC LIMIT 1"
        )

    def save_many(self, days: list[DailyWeather]) -> int:
        _run(
            self._insert,
            (
                (
                    d.region.key,
                    d.day,
                    d.region.center.latitude,
                    d.region.center.longitude,
                    *(getattr(d, metric) for metric in _WEATHER_METRICS),
                )
                for d in days
            ),
        )
        return len(days)

    def day_bounds(self, region: GridCell) -> tuple[date, date] | None:
        session = get_session()
        first = session.execute(self._first_day, (region.key,)).one()
        if first is None:
            return None
        last = session.execute(self._last_day, (region.key,)).one()
        return _to_day(first.day), _to_day(last.day)

    def list_for_region(self, region: GridCell) -> list[DailyWeather]:
        return [
            DailyWeather(
                region=region,
                day=_to_day(row.day),
                **{metric: getattr(row, metric) for metric in _WEATHER_METRICS},
            )
            for row in get_session().execute(self._select_region, (region.key,))
        ]
