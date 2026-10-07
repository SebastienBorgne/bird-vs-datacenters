"""Repository interfaces (ports) for the Scheduling bounded context.

Defined in the domain layer because the domain dictates what persistence
operations it needs. Concrete implementations (Django ORM, in-memory for
tests, ...) live in `core.frameworks` and depend on these interfaces —
never the other way around.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .entities import Execution, Job
from .value_objects import ExecutionId, JobId, JobStatus


class JobRepository(ABC):
    @abstractmethod
    def get(self, job_id: JobId) -> Job | None: ...

    @abstractmethod
    def save(self, job: Job) -> None: ...

    @abstractmethod
    def list_by_status(self, status: JobStatus) -> list[Job]: ...

    @abstractmethod
    def delete(self, job_id: JobId) -> None: ...


class ExecutionRepository(ABC):
    @abstractmethod
    def get(self, execution_id: ExecutionId) -> Execution | None: ...

    @abstractmethod
    def save(self, execution: Execution) -> None: ...

    @abstractmethod
    def list_for_job(self, job_id: JobId, limit: int = 50) -> list[Execution]: ...

    @abstractmethod
    def list_pending_before(self, moment: datetime) -> list[Execution]: ...
