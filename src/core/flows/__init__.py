"""Registry of flows.

A flow is a self-contained, schedulable unit of work:

    flows/<flow_name>/app.py        Typer app — manual/local run + trigger from the CLI
    flows/<flow_name>/tasks.py      Celery task — wraps use_cases for scheduled runs
    flows/<flow_name>/use_cases.py  the actual business logic (no Celery/Typer import)
    flows/<flow_name>/__init__.py   re-exports `app` from app.py

`FLOW_NAMES` is discovered from the subpackages present here so the CLI
(`core.frameworks.typer_app.typer_app`), Celery (`core.frameworks.celery_app.app`) and Django
(`INSTALLED_APPS`, see `django_app/config/settings.py`) all pick up new
flows automatically — no hand-maintained import list. Being a Django app
is what lets a flow ship its own `models.py`/`admin.py` later; flows with
neither are registered as apps with no models, which Django allows.
"""

from __future__ import annotations

import pkgutil
from pathlib import Path

FLOW_NAMES = sorted(
    name for _, name, is_pkg in pkgutil.iter_modules([str(Path(__file__).parent)]) if is_pkg
)
