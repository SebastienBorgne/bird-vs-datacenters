"""Geodata use cases: incremental ingestion of bird observations and datacenters."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.domain.geodata.repositories import BirdObservationRepository, DatacenterRepository

from .ports import BirdObservationSource, DatacenterSource, ObservationPage, SourceUnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BirdIngestionReport:
    saved: int
    pages: int
    id_bounds: tuple[int, int] | None
    interrupted: bool = False


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
