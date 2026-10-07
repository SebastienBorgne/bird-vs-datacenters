"""template — Typer CLI for manual/local runs, thin wrapper around tasks."""

from __future__ import annotations

import typer

from . import tasks

app = typer.Typer(
    no_args_is_help=True, help="template — run the template flow (manual/local runs)."
)


@app.command()
def run() -> None:
    """Run the template flow synchronously, bypassing Celery — useful for local testing."""
    typer.echo(tasks.run())


@app.command()
def trigger() -> None:
    """Enqueue the template flow on Celery (RabbitMQ) and let a worker run it."""
    task_id = tasks.trigger()
    typer.echo(f"Queued template task: {task_id}")
