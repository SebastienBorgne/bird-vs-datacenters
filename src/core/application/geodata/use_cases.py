"""Geodata use cases: incremental ingestion of bird observations, datacenters and weather,
and datacenter power estimates.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from core.domain.geodata.entities import (
    CountryEnergyBenchmark,
    Datacenter,
    DatacenterPowerEstimate,
)
from core.domain.geodata.repositories import (
    BirdObservationRepository,
    DailyWeatherRepository,
    DatacenterPowerEstimateRepository,
    DatacenterRepository,
)
from core.domain.geodata.value_objects import GridCell, PowerEstimateBasis

from .ports import (
    BirdObservationSource,
    DatacenterSource,
    EnergyBenchmarkSource,
    ObservationPage,
    SourceUnavailableError,
    WeatherSource,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BirdIngestionReport:
    saved: int
    pages: int
    id_bounds: tuple[int, int] | None
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class WeatherIngestionReport:
    saved_days: int
    requests: int
    regions: int
    # Regions with every day of the window stored, after this run.
    complete_regions: int
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class PowerEstimationReport:
    saved: int
    by_basis: dict[str, int]
    # Benchmarked countries without any stored datacenter.
    unmatched_countries: list[str]


class GeodataUseCases:
    def __init__(
        self,
        bird_observations: BirdObservationRepository,
        datacenters: DatacenterRepository,
    ) -> None:
        self.bird_observations = bird_observations
        self.datacenters = datacenters

    def ingest_bird_observations(
        self, source: BirdObservationSource, max_pages: int
    ) -> BirdIngestionReport:
        """Fetch up to `max_pages` pages, growing the stored id range on both ends.

        - forward: observations newer than the highest stored id, with at most half
          the page budget so a backlog of new ones never starves the backfill;
        - backfill: observations older than the lowest stored id, with the rest.

        The cursor is derived from the stored ids, and each page is saved as soon
        as it is fetched, so an interrupted run loses nothing.
        """
        saved, pages = 0, 0
        bounds = self.bird_observations.id_bounds()

        def store(page: ObservationPage) -> list[int]:
            nonlocal saved, pages
            self.bird_observations.save_many(page.observations)
            pages, saved = pages + 1, saved + len(page.observations)
            return [o.id for o in page.observations]

        try:
            if bounds is not None:
                high = bounds[1]
                while pages < max(1, max_pages // 2):
                    page = source.newer_than(high)
                    high = max([high, *store(page)])
                    if not page.has_more:
                        break  # caught up with the newest observations
                logger.info("Forward: %d new observations after %d page(s).", saved, pages)

            low = bounds[0] if bounds is not None else None
            while pages < max_pages:
                page = source.older_than(low)
                ids = store(page)
                low = min(ids) if ids else low
                logger.info("Backfill page %d/%d, below id %s.", pages, max_pages, low)
                if not page.has_more:
                    break  # reached the oldest observation
        except SourceUnavailableError as e:
            logger.warning("Stopping early, source unavailable: %s", e)
            return BirdIngestionReport(saved, pages, self.bird_observations.id_bounds(), True)

        logger.info("Stored %d bird observations in %d page(s).", saved, pages)
        return BirdIngestionReport(saved, pages, self.bird_observations.id_bounds())

    def ingest_datacenters(self, source: DatacenterSource) -> int:
        """Fetch every datacenter from the source and upsert them; returns how many."""
        saved = self.datacenters.save_many(source.fetch_all())
        logger.info("Stored %d datacenters.", saved)
        return saved


def _chunks(
    start: date, end: date, size_days: int, newest_first: bool
) -> Iterator[tuple[date, date]]:
    """Split `start`..`end` (inclusive) into ranges of at most `size_days` days."""
    if newest_first:
        while end >= start:
            chunk_start = max(start, end - timedelta(days=size_days - 1))
            yield chunk_start, end
            end = chunk_start - timedelta(days=1)
    else:
        while start <= end:
            chunk_end = min(end, start + timedelta(days=size_days - 1))
            yield start, chunk_end
            start = chunk_end + timedelta(days=1)


def missing_ranges(
    bounds: tuple[date, date] | None, start: date, end: date, chunk_days: int
) -> list[tuple[date, date]]:
    """Ranges of `start`..`end` not covered by the stored `bounds`, as request-sized chunks.

    Stored days are assumed contiguous (each chunk is saved whole, growing the
    range on either end): new days after the last stored one come first, then
    the backfill towards `start`, newest first.
    """
    if bounds is None:
        return list(_chunks(start, end, chunk_days, newest_first=True))
    first, last = bounds
    forward = list(_chunks(max(start, last + timedelta(days=1)), end, chunk_days, False))
    backfill = list(_chunks(start, min(end, first - timedelta(days=1)), chunk_days, True))
    return forward + backfill


class WeatherUseCases:
    def __init__(
        self, datacenters: DatacenterRepository, daily_weather: DailyWeatherRepository
    ) -> None:
        self.datacenters = datacenters
        self.daily_weather = daily_weather

    def datacenter_regions(self) -> list[GridCell]:
        """Grid cells holding at least one datacenter, the most crowded first."""
        counts = Counter(GridCell.containing(d.location) for d in self.datacenters.list_all())
        return [cell for cell, _ in counts.most_common()]

    def _missing(
        self, region: GridCell, start: date, end: date, chunk_days: int
    ) -> list[tuple[date, date]]:
        return missing_ranges(self.daily_weather.day_bounds(region), start, end, chunk_days)

    def _fetch(
        self, source: WeatherSource, planned: list[tuple[GridCell, tuple[date, date]]]
    ) -> tuple[int, int, bool]:
        """Fetch and store each planned chunk; returns (days saved, requests, interrupted)."""
        saved = 0
        for requests, (region, (chunk_start, chunk_end)) in enumerate(planned):
            try:
                days = source.fetch_daily(region, chunk_start, chunk_end)
            except SourceUnavailableError as e:
                logger.warning("Stopping early, source unavailable: %s", e)
                return saved, requests, True
            saved += self.daily_weather.save_many(days)
            logger.info(
                "Weather %s %s..%s: %d day(s), request %d/%d.",
                region.key,
                chunk_start,
                chunk_end,
                len(days),
                requests + 1,
                len(planned),
            )
        return saved, len(planned), False

    def ingest_daily_weather(
        self,
        source: WeatherSource,
        start: date,
        end: date,
        max_requests: int,
        chunk_days: int = 366,
    ) -> WeatherIngestionReport:
        """Fill `start`..`end` with daily weather for every datacenter region.

        Spends at most `max_requests` source requests per run, one region and
        up to `chunk_days` days each, so a long backfill spreads over several
        runs. The cursor is derived from the stored days and each chunk is
        saved as soon as it is fetched, so an interrupted run loses nothing.
        """
        regions = self.datacenter_regions()
        planned = [
            (region, chunk)
            for region in regions
            for chunk in self._missing(region, start, end, chunk_days)
        ][:max_requests]

        saved, requests, interrupted = self._fetch(source, planned)

        complete = sum(1 for r in regions if not self._missing(r, start, end, chunk_days))
        logger.info(
            "Stored %d weather day(s) in %d request(s); %d/%d regions complete.",
            saved,
            requests,
            complete,
            len(regions),
        )
        return WeatherIngestionReport(saved, requests, len(regions), complete, interrupted)


@dataclass(frozen=True, slots=True)
class _Scale:
    """Energy per reporting datacenter and per m2 of floor, and IT power per unit of energy."""

    energy_per_site_gwh: float
    energy_per_m2_gwh: float | None
    mw_per_gwh: float


class PowerUseCases:
    def __init__(
        self, datacenters: DatacenterRepository, estimates: DatacenterPowerEstimateRepository
    ) -> None:
        self.datacenters = datacenters
        self.estimates = estimates

    @staticmethod
    def _country_scale(benchmark: CountryEnergyBenchmark, sites: list[Datacenter]) -> _Scale:
        """A mapped site of average floor area gets the energy of an average reporting site."""
        per_site = benchmark.energy_gwh / benchmark.reporting_datacenters
        areas = [a for d in sites if (a := d.floor_area_m2)]
        per_m2 = per_site / (sum(areas) / len(areas)) if areas else None
        return _Scale(per_site, per_m2, benchmark.it_power_mw / benchmark.energy_gwh)

    @staticmethod
    def _overall_scale(
        benchmarks: list[CountryEnergyBenchmark], allocated_gwh: float, area_m2: float
    ) -> _Scale:
        """Every benchmarked country together, for datacenters of the other countries:
        `allocated_gwh` is the energy given to the `area_m2` of floor of their datacenters.
        """
        energy = sum(b.energy_gwh for b in benchmarks)
        return _Scale(
            energy / sum(b.reporting_datacenters for b in benchmarks),
            allocated_gwh / area_m2 if area_m2 else None,
            sum(b.it_power_mw for b in benchmarks) / energy,
        )

    def estimate_datacenter_power(self, source: EnergyBenchmarkSource) -> PowerEstimationReport:
        """Estimate every stored datacenter's IT power and yearly energy use.

        Benchmarks only give totals per country, so each country's energy per
        reporting datacenter is spread over its stored datacenters by floor area:
        one of average floor area gets the average energy, one twice as large twice
        as much. Datacenters without a floor area get the average. Countries without
        a benchmark use the energy per m2 and per site of all benchmarked countries.
        IT power follows energy, at the country's ratio. Rough by design: good to
        rank and compare sites, not to state any one site's consumption.
        """
        benchmarks = {b.country: b for b in source.fetch_all()}
        if not benchmarks:
            logger.warning("No energy benchmarks, nothing to estimate.")
            return PowerEstimationReport(0, {}, [])
        year = max(b.year for b in benchmarks.values())
        by_country: dict[str | None, list[Datacenter]] = defaultdict(list)
        for datacenter in self.datacenters.list_all():
            by_country[datacenter.country].append(datacenter)

        estimates: list[DatacenterPowerEstimate] = []
        allocated_gwh, area_m2 = 0.0, 0.0

        def add(d: Datacenter, scale: _Scale, basis: PowerEstimateBasis, energy: float) -> None:
            estimates.append(
                DatacenterPowerEstimate(
                    external_id=d.external_id,
                    country=d.country,
                    year=year,
                    basis=basis.value,
                    it_power_mw=energy * scale.mw_per_gwh,
                    energy_gwh=energy,
                )
            )

        for country, benchmark in benchmarks.items():
            sites = by_country.get(country, [])
            scale = self._country_scale(benchmark, sites)
            for d in sites:
                area = d.floor_area_m2
                if area and scale.energy_per_m2_gwh is not None:
                    energy = area * scale.energy_per_m2_gwh
                    allocated_gwh, area_m2 = allocated_gwh + energy, area_m2 + area
                    add(d, scale, PowerEstimateBasis.FLOOR_AREA, energy)
                else:
                    add(d, scale, PowerEstimateBasis.COUNTRY_AVERAGE, scale.energy_per_site_gwh)

        overall = self._overall_scale(list(benchmarks.values()), allocated_gwh, area_m2)
        for country, sites in by_country.items():
            if country in benchmarks:
                continue
            for d in sites:
                area = d.floor_area_m2
                if area and overall.energy_per_m2_gwh is not None:
                    energy = area * overall.energy_per_m2_gwh
                    add(d, overall, PowerEstimateBasis.BENCHMARK_FLOOR_AREA, energy)
                else:
                    energy = overall.energy_per_site_gwh
                    add(d, overall, PowerEstimateBasis.BENCHMARK_AVERAGE, energy)

        saved = self.estimates.save_many(estimates)
        by_basis = dict(Counter(e.basis for e in estimates))
        unmatched = sorted(c for c in benchmarks if c not in by_country)
        logger.info("Stored %d power estimates (%s).", saved, by_basis)
        return PowerEstimationReport(saved, by_basis, unmatched)
