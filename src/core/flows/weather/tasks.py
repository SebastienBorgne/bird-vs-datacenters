"""Celery tasks for the weather flow — the unit of work Celery Beat / a worker
executes.

`@shared_task` (rather than importing the `Celery` app instance directly)
avoids a hard dependency on `core.frameworks.celery_app`, so this module
stays importable without pulling in Django/Celery app configuration.
"""

from __future__ import annotations

from celery import shared_task

from . import use_cases


@shared_task
def run(max_requests: int | None = None) -> str:
    """Execute the weather flow. Called directly for a synchronous run, or
    by a Celery worker when queued via `trigger()` (or a Celery Beat schedule).
    """
    return use_cases.run(max_requests)


def trigger(max_requests: int | None = None) -> str:
    """Enqueue the weather flow on Celery (RabbitMQ) for a worker to run
    asynchronously.

    Returns the queued task's id.
    """
    # pylint: disable-next=import-outside-toplevel,unused-import
    from core.frameworks.celery_app.app import app as celery_app  # noqa: F401

    return run.delay(max_requests).id
