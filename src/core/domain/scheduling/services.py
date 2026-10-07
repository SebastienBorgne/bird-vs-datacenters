"""Domain service interfaces (ports) for the Scheduling context.

These are capabilities the domain needs but cannot implement itself
without an external dependency. The domain declares the contract here;
`core.frameworks` provides the concrete implementation (e.g. via the
`croniter` library) and it gets injected wherever it's needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .value_objects import CronSchedule


class CronCalculator(ABC):
    """Computes the next occurrence of a cron expression."""

    @abstractmethod
    def next_run_after(self, schedule: CronSchedule, moment: datetime) -> datetime | None: ...
