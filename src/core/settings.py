"""App-wide settings read from `.env`, exposed as a plain dict.

Most framework settings (Celery, Django secrets/hosts) read individual env
vars directly via `os.environ` (see `frameworks/django_app/config/settings.py`)
so they work identically whether values come from a real `.env` file or from
Docker's `environment:`. The database connection is the exception: Django's
`DATABASES` is built from `config.database` here, so it's defined once and
shared with anything else in the app that needs a db connection outside of
Django. Real process env vars (Docker, CI, ...) take precedence over what's
in the `.env` file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parents[2]

env: dict[str, str | None] = {**dotenv_values(BASE_DIR / ".env"), **os.environ}


class DjangoSettings:
    DJANGO_SUPERUSER_USERNAME = env.get("APP_RUN__DJANGO_USER_NAME")
    DJANGO_SUPERUSER_PASSWORD = env.get("APP_RUN__DJANGO_USER_PASSWORD")


class DatabaseSettings:
    NAME = env.get("POSTGRES_DB", "ordy")
    USER = env.get("POSTGRES_USER", "ordy")
    PASSWORD = env.get("POSTGRES_PASSWORD", "ordy")
    HOST = env.get("POSTGRES_HOST", "localhost")
    PORT = env.get("POSTGRES_PORT", "5432")


class BirdApiSettings:
    BIRD_API_URL = env.get(
        "BIRD_API_URL", "https://api.inaturalist.org/v1/observations?taxon_id=3&per_page=50"
    )


class DatacenterApiSettings:
    # Public OpenStreetMap Overpass API — free, no key. Mirrors, e.g.
    # https://overpass.private.coffee/api/interpreter, can be swapped in.
    OVERPASS_API_URL = env.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
    # Comma-separated ISO 3166-1 alpha-2 codes, queried one at a time to keep each
    # Overpass request small. Empty means a single worldwide query.
    DATACENTER_COUNTRIES = env.get("DATACENTER_COUNTRIES", "US,FR,BE,NL,DE,IE,GB")


class Settings:
    django: DjangoSettings = DjangoSettings()
    database: DatabaseSettings = DatabaseSettings()
    bird_api: BirdApiSettings = BirdApiSettings()
    datacenter_api: DatacenterApiSettings = DatacenterApiSettings()


config = Settings()
