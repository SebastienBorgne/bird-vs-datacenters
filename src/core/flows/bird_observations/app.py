"""bird_observations — Typer CLI for manual/local runs, thin wrapper around tasks."""

from __future__ import annotations

import typer

from . import tasks

app = typer.Typer(
    no_args_is_help=True,
    help="bird_observations — run the bird observations flow (manual/local runs).",
)


@app.command()
def run() -> None:
    """Run the bird observations flow synchronously, bypassing Celery — useful for local
    testing.
    """
    typer.echo(tasks.run())


@app.command()
def trigger() -> None:
    """Enqueue the bird observations flow on Celery (RabbitMQ) and let a worker run it."""
    task_id = tasks.trigger()
    typer.echo(f"Queued bird_observations task: {task_id}")
