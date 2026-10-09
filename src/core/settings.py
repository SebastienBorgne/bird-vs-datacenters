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
    # iNaturalist observations endpoint; its query string holds the filters (taxon 3 = birds,
    # geo=true = only geolocated ones). Paging params are added by `INaturalistSource`.
    # Changing the filters on a non-empty db leaves older rows that don't match them.
    BIRD_API_URL = (
        env.get("BIRD_API_URL") or "https://api.inaturalist.org/v1/observations?taxon_id=3&geo=true"
    )
    # Pages (of 200 observations) fetched per run. iNaturalist asks for <= 1 request/s and
    # ~10k requests/day, so keep MAX_PAGES x runs/day under that.
    BIRD_API_MAX_PAGES = int(env.get("BIRD_API_MAX_PAGES") or 50)
    BIRD_API_DELAY_S = float(env.get("BIRD_API_DELAY_S") or 1.0)


class DatacenterApiSettings:
    # Public OpenStreetMap Overpass API — free, no key. Mirrors, e.g.
    # https://overpass.private.coffee/api/interpreter, can be swapped in.
    OVERPASS_API_URL = env.get("OVERPASS_API_URL") or "https://overpass-api.de/api/interpreter"
    # Comma-separated ISO 3166-1 alpha-2 codes, queried one at a time to keep each
    # Overpass request small. Empty means a single worldwide query.
    DATACENTER_COUNTRIES = env.get("DATACENTER_COUNTRIES", "US,FR,BE,NL,DE,IE,GB")


class WeatherApiSettings:
    # Open-Meteo historical weather API (ERA5 reanalysis and others): free for
    # non-commercial use, no key. Daily metrics are fetched for the center of each
    # datacenter region (1° grid cell).
    WEATHER_API_URL = env.get("WEATHER_API_URL") or "https://archive-api.open-meteo.com/v1/archive"
    # Window kept in store: the last YEARS years, up to LAG_DAYS ago (the archive
    # lags a few days behind real time).
    WEATHER_API_YEARS = int(env.get("WEATHER_API_YEARS") or 5)
    WEATHER_API_LAG_DAYS = int(env.get("WEATHER_API_LAG_DAYS") or 5)
    # Open-Meteo counts a request as (days / 14) x (variables / 10) calls: one region-year
    # of the 6 daily metrics ~ 16 calls. Its free limits are 600 calls/min, 5,000/hour and
    # 10,000/day, so 250 requests (~4,000 calls) per run, at most twice a day, stays under.
    WEATHER_API_MAX_REQUESTS = int(env.get("WEATHER_API_MAX_REQUESTS") or 250)
    # ~16 calls per request: 2 s between requests is ~480 calls/min.
    WEATHER_API_DELAY_S = float(env.get("WEATHER_API_DELAY_S") or 2.0)


class CassandraSettings:
    HOSTS = tuple(h.strip() for h in (env.get("CASSANDRA_HOSTS") or "localhost").split(","))
    PORT = int(env.get("CASSANDRA_PORT") or 9042)
    KEYSPACE = env.get("CASSANDRA_KEYSPACE") or "birdy"
    LOCAL_DC = env.get("CASSANDRA_LOCAL_DC") or "datacenter1"
    # 1 for the single dev node; raise it (and the strategy) for a real cluster.
    REPLICATION_FACTOR = int(env.get("CASSANDRA_REPLICATION_FACTOR") or 1)


class Settings:
    django: DjangoSettings = DjangoSettings()
    database: DatabaseSettings = DatabaseSettings()
    bird_api: BirdApiSettings = BirdApiSettings()
    datacenter_api: DatacenterApiSettings = DatacenterApiSettings()
    weather_api: WeatherApiSettings = WeatherApiSettings()
    cassandra: CassandraSettings = CassandraSettings()


config = Settings()
