"""The main Typer application.

Mounts every flow's Typer app (`core.flows.<flow_name>.app`) as a
subcommand group: `birdy <flow> run` / `birdy <flow> trigger`. Flows are
discovered from `core.flows.FLOW_NAMES`, so adding a flow package is
enough to expose it on the CLI.
"""

from __future__ import annotations

import os
from importlib import import_module

import django
import typer

# Flows run use cases synchronously from the CLI, which may hit the Django
# ORM — set Django up before importing them, as the Celery app does.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.frameworks.django_app.config.settings")
django.setup()

from core.flows import FLOW_NAMES

app = typer.Typer(no_args_is_help=True, help="birdy — interact with the app from the CLI.")

for name in FLOW_NAMES:
    app.add_typer(import_module(f"core.flows.{name}").app, name=name)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
