"""Django settings for ordy.

Minimal configuration to run Django admin and django-celery-beat (the
source of truth for Celery Beat schedules). All environment-specific
values come from env vars so the same module works locally, in Docker
and in CI. The database connection is read via `core.settings.config`
(see that module); everything else reads `os.environ` directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.flows import FLOW_NAMES
from core.settings import config

BASE_DIR = Path(__file__).resolve().parents[5]

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_beat",
    "django_celery_results",
    "core.frameworks.django_app.geodata",
] + [f"core.flows.{name}" for name in FLOW_NAMES]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.frameworks.django_app.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.frameworks.django_app.config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config.database.NAME,
        "USER": config.database.USER,
        "PASSWORD": config.database.PASSWORD,
        "HOST": config.database.HOST,
        "PORT": config.database.PORT,
    }
}

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery — broker is RabbitMQ, schedules are read from django-celery-beat's
# DatabaseScheduler (PeriodicTask rows managed via Django admin). Results
# are stored via django-celery-results (TaskResult rows, also in admin)
# instead of RabbitMQ's rpc:// backend, so past runs stay queryable.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "django-db")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
