"""bird_observations — Typer CLI for manual/local runs, thin wrapper around tasks."""

from __future__ import annotations

from typing import Annotated

import typer

from . import tasks

app = typer.Typer(
    no_args_is_help=True,
    help="bird_observations — run the bird observations flow (manual/local runs).",
)


MaxPages = Annotated[
    int | None,
    typer.Option(help="Pages of 200 observations to fetch (default: BIRD_API_MAX_PAGES)."),
]


@app.command()
def run(max_pages: MaxPages = None) -> None:
    """Run the bird observations flow synchronously, bypassing Celery — useful for local
    testing.
    """
    typer.echo(tasks.run(max_pages))


@app.command()
def trigger(max_pages: MaxPages = None) -> None:
    """Enqueue the bird observations flow on Celery (RabbitMQ) and let a worker run it."""
    task_id = tasks.trigger(max_pages)
    typer.echo(f"Queued bird_observations task: {task_id}")
