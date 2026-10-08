"""Copy geodata between stores, then check nothing was lost.

Used once, to move bird observations and datacenters from the legacy
Postgres tables to Cassandra (Django migration `geodata.0002`). Writes go
through the domain repository ports, so this is store-agnostic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import islice

from core.domain.geodata.entities import BirdObservation, Datacenter
from core.domain.geodata.repositories import BirdObservationRepository, DatacenterRepository

logger = logging.getLogger(__name__)


class TransferVerificationError(Exception):
    """Some source rows are missing from the target after the copy."""


@dataclass(frozen=True, slots=True)
class TransferReport:
    bird_observations: int
    datacenters: int


def _batches[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def transfer_geodata(
    bird_observations: Iterable[BirdObservation],
    datacenters: Iterable[Datacenter],
    bird_observation_target: BirdObservationRepository,
    datacenter_target: DatacenterRepository,
    batch_size: int = 5_000,
) -> TransferReport:
    """Upsert everything into the targets (idempotent: safe to re-run), then verify
    every source id is there. Raises `TransferVerificationError` otherwise.
    """
    bird_ids: set[int] = set()
    for batch in _batches(bird_observations, batch_size):
        bird_observation_target.save_many(batch)
        bird_ids.update(o.id for o in batch)
        logger.info("Copied %d bird observations…", len(bird_ids))

    datacenter_ids: set[str] = set()
    for dc_batch in _batches(datacenters, batch_size):
        datacenter_target.save_many(dc_batch)
        datacenter_ids.update(d.external_id for d in dc_batch)
    logger.info("Copied %d datacenters.", len(datacenter_ids))

    missing_birds = bird_ids - {o.id for o in bird_observation_target.list_all()}
    missing_datacenters = datacenter_ids - {d.external_id for d in datacenter_target.list_all()}
    if missing_birds or missing_datacenters:
        raise TransferVerificationError(
            f"{len(missing_birds)} bird observation(s) and {len(missing_datacenters)} "
            f"datacenter(s) missing from the target, e.g. "
            f"{sorted(missing_birds)[:5]} {sorted(missing_datacenters)[:5]}"
        )
    return TransferReport(len(bird_ids), len(datacenter_ids))
