"""The Celery application.

Beat schedules are not hardcoded here: Celery Beat runs with
django-celery-beat's `DatabaseScheduler` (configured via
`CELERY_BEAT_SCHEDULER` in Django settings), which reads `PeriodicTask`
rows managed from the Django admin. Tasks themselves are discovered from
every flow package under `core.flows` (see `core.flows.FLOW_NAMES`).
"""

from __future__ import annotations

import os

import django
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.frameworks.django_app.config.settings")
django.setup()

from core.flows import FLOW_NAMES

app = Celery("ordy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: [f"core.flows.{name}" for name in FLOW_NAMES], related_name="tasks")
