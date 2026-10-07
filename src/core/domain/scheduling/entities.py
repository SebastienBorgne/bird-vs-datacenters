"""Entities and aggregates for the Scheduling bounded context.

Two aggregate roots:

- `Job`: a recurring unit of work and its schedule.
- `Execution`: one run of a Job, kept as its own aggregate (referencing
  `job_id`) so execution history can grow without bloating the Job
  aggregate or forcing every read of a Job to load its whole history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .events import (
    DomainEvent,
    ExecutionCancelled,
    ExecutionFailed,
    ExecutionStarted,
    ExecutionSucceeded,
    JobCreated,
    JobPaused,
    JobRescheduled,
    JobResumed,
    JobTriggeredManually,
)
from .exceptions import ExecutionAlreadyFinishedError, JobNotActiveError
from .value_objects import (
    ExecutionId,
    ExecutionStatus,
    JobId,
    JobStatus,
    Schedule,
    TaskReference,
)


@dataclass(slots=True)
class Job:
    """Aggregate root: a unit of recurring work with its own schedule."""

    id: JobId
    name: str
    task: TaskReference
    schedule: Schedule
    status: JobStatus = JobStatus.DRAFT
    created_at: datetime | None = None
    max_retries: int = 0
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls, id: JobId, name: str, task: TaskReference, schedule: Schedule, now: datetime
    ) -> Job:
        job = cls(
            id=id, name=name, task=task, schedule=schedule, status=JobStatus.ACTIVE, created_at=now
        )
        job._events.append(JobCreated(job_id=id, occurred_at=now))
        return job

    def pause(self, now: datetime) -> None:
        if self.status != JobStatus.ACTIVE:
            raise JobNotActiveError(self.id)
        self.status = JobStatus.PAUSED
        self._events.append(JobPaused(job_id=self.id, occurred_at=now))

    def resume(self, now: datetime) -> None:
        self.status = JobStatus.ACTIVE
        self._events.append(JobResumed(job_id=self.id, occurred_at=now))

    def reschedule(self, schedule: Schedule, now: datetime) -> None:
        self.schedule = schedule
        self._events.append(JobRescheduled(job_id=self.id, occurred_at=now))

    def trigger_manually(self, now: datetime) -> None:
        if self.status != JobStatus.ACTIVE:
            raise JobNotActiveError(self.id)
        self._events.append(JobTriggeredManually(job_id=self.id, occurred_at=now))

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events


@dataclass(slots=True)
class Execution:
    """Aggregate root: one run of a Job."""

    id: ExecutionId
    job_id: JobId
    scheduled_for: datetime
    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    attempt: int = 1
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def schedule(cls, id: ExecutionId, job_id: JobId, scheduled_for: datetime) -> Execution:
        return cls(id=id, job_id=job_id, scheduled_for=scheduled_for)

    def start(self, now: datetime) -> None:
        if self.status != ExecutionStatus.PENDING:
            raise ExecutionAlreadyFinishedError(self.id)
        self.status = ExecutionStatus.RUNNING
        self.started_at = now
        self._events.append(
            ExecutionStarted(execution_id=self.id, job_id=self.job_id, occurred_at=now)
        )

    def mark_succeeded(self, now: datetime) -> None:
        self.status = ExecutionStatus.SUCCEEDED
        self.finished_at = now
        self._events.append(
            ExecutionSucceeded(execution_id=self.id, job_id=self.job_id, occurred_at=now)
        )

    def mark_failed(self, now: datetime, error_message: str) -> None:
        self.status = ExecutionStatus.FAILED
        self.finished_at = now
        self.error_message = error_message
        self._events.append(
            ExecutionFailed(
                execution_id=self.id,
                job_id=self.job_id,
                occurred_at=now,
                error_message=error_message,
            )
        )

    def cancel(self, now: datetime) -> None:
        if self.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED):
            raise ExecutionAlreadyFinishedError(self.id)
        self.status = ExecutionStatus.CANCELLED
        self.finished_at = now
        self._events.append(
            ExecutionCancelled(execution_id=self.id, job_id=self.job_id, occurred_at=now)
        )

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
