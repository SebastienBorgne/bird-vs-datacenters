"""Value objects for the Scheduling bounded context.

Value objects are immutable and compared by value, not identity. They
carry no framework dependency.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID


class JobStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ExecutionId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TaskReference:
    """Identifies the unit of work a job runs, e.g. the Celery task name
    "billing.tasks.generate_invoice". The domain only stores the
    reference; resolving it to actual code is an infrastructure concern.
    """

    dotted_path: str

    def __post_init__(self) -> None:
        if not self.dotted_path or "." not in self.dotted_path:
            raise ValueError(f"Invalid task reference: {self.dotted_path!r}")


class Schedule(ABC):
    """A rule that determines when a job is due to run next."""

    @abstractmethod
    def next_run_after(self, moment: datetime) -> datetime | None:
        """Return the next UTC datetime the job is due after `moment`, or
        None if the schedule has no further occurrences.
        """


@dataclass(frozen=True, slots=True)
class IntervalSchedule(Schedule):
    """Runs every fixed interval, e.g. every 15 minutes."""

    every: timedelta

    def __post_init__(self) -> None:
        if self.every <= timedelta(0):
            raise ValueError("Interval must be positive")

    def next_run_after(self, moment: datetime) -> datetime:
        return moment + self.every


@dataclass(frozen=True, slots=True)
class CronSchedule(Schedule):
    """Runs on a cron expression, e.g. "*/5 * * * *".

    Computing occurrences needs a cron-parsing library (croniter), which
    is a technical concern, not a domain one. This value object only
    validates the expression's shape; actual occurrence calculation is
    delegated to the `CronCalculator` port (see `services.py`) so the
    domain stays dependency-free.
    """

    expression: str

    def __post_init__(self) -> None:
        if len(self.expression.split()) != 5:
            raise ValueError(f"Invalid cron expression: {self.expression!r}")

    def next_run_after(self, moment: datetime) -> datetime | None:
        raise NotImplementedError(
            "CronSchedule.next_run_after requires a CronCalculator adapter; "
            "use it via the application layer instead of calling this directly."
        )
