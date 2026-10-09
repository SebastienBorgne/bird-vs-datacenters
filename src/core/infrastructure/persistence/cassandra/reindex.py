"""Rebuild the bird observation lookup tables from `bird_observations` — idempotent.

Re-saves every stored observation through the repository, which (re)writes
`bird_observations_by_cell` and `bird_observations_by_month`. Run it once
after adding a lookup table, once the code writing it is deployed:
`python -m core.infrastructure.persistence.cassandra.reindex`.
"""

from __future__ import annotations

import logging
from itertools import islice

from .repositories import CassandraBirdObservationRepository

logger = logging.getLogger(__name__)

BATCH_SIZE = 5_000


def reindex_bird_observations() -> int:
    repository = CassandraBirdObservationRepository()
    observations = repository.iter_all()
    done = 0
    while batch := list(islice(observations, BATCH_SIZE)):
        done += repository.save_many(batch)
        logger.info("Reindexed %d bird observations…", done)
    return done


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Done: %d bird observations reindexed.", reindex_bird_observations())
