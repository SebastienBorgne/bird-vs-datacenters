"""weather — Typer CLI for manual/local runs, thin wrapper around tasks."""

from __future__ import annotations

from typing import Annotated

import typer

from . import tasks

app = typer.Typer(
    no_args_is_help=True,
    help="weather — run the daily weather flow of datacenter regions (manual/local runs).",
)


MaxRequests = Annotated[
    int | None,
    typer.Option(
        help="Open-Meteo requests to spend, one region-year each "
        "(default: WEATHER_API_MAX_REQUESTS)."
    ),
]


@app.command()
def run(max_requests: MaxRequests = None) -> None:
    """Run the weather flow synchronously, bypassing Celery — useful for local
    testing.
    """
    typer.echo(tasks.run(max_requests))


@app.command()
def trigger(max_requests: MaxRequests = None) -> None:
    """Enqueue the weather flow on Celery (RabbitMQ) and let a worker run it."""
    task_id = tasks.trigger(max_requests)
    typer.echo(f"Queued weather task: {task_id}")
