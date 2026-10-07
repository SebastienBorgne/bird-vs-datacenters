"""Domain events for the Scheduling bounded context.

Events are immutable facts published after an aggregate changes state.
The application layer collects them (via `pull_events()`) and hands them
to an `EventPublisher` port (e.g. published on RabbitMQ, or just logged).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .value_objects import ExecutionId, JobId


@dataclass(frozen=True, slots=True)
class DomainEvent:
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class JobCreated(DomainEvent):
    job_id: JobId


@dataclass(frozen=True, slots=True)
class JobPaused(DomainEvent):
    job_id: JobId


@dataclass(frozen=True, slots=True)
class JobResumed(DomainEvent):
    job_id: JobId


@dataclass(frozen=True, slots=True)
class JobRescheduled(DomainEvent):
    job_id: JobId


@dataclass(frozen=True, slots=True)
class JobTriggeredManually(DomainEvent):
    job_id: JobId


@dataclass(frozen=True, slots=True)
class ExecutionStarted(DomainEvent):
    execution_id: ExecutionId
    job_id: JobId


@dataclass(frozen=True, slots=True)
class ExecutionSucceeded(DomainEvent):
    execution_id: ExecutionId
    job_id: JobId


@dataclass(frozen=True, slots=True)
class ExecutionFailed(DomainEvent):
    execution_id: ExecutionId
    job_id: JobId
    error_message: str


@dataclass(frozen=True, slots=True)
class ExecutionCancelled(DomainEvent):
    execution_id: ExecutionId
    job_id: JobId
