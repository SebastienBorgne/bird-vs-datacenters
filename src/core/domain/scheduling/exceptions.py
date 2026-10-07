"""Domain exceptions for the Scheduling bounded context."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .value_objects import ExecutionId, JobId


class SchedulingDomainError(Exception):
    """Base class for all Scheduling domain errors."""


class JobNotActiveError(SchedulingDomainError):
    def __init__(self, job_id: JobId) -> None:
        super().__init__(f"Job {job_id} is not active")
        self.job_id = job_id


class ExecutionAlreadyFinishedError(SchedulingDomainError):
    def __init__(self, execution_id: ExecutionId) -> None:
        super().__init__(f"Execution {execution_id} is already finished")
        self.execution_id = execution_id
