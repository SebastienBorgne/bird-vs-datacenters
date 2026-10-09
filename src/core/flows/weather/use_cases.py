"""Weather flow: wires Open-Meteo and Cassandra into the daily weather ingestion use case."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from core.application.geodata.use_cases import WeatherUseCases
from core.infrastructure.persistence.cassandra.repositories import (
    CassandraDailyWeatherRepository,
    CassandraDatacenterRepository,
)
from core.infrastructure.sources.open_meteo import OpenMeteoSource
from core.settings import config


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def run(max_requests: int | None = None) -> str:
    settings = config.weather_api
    # Days are UTC, as requested from Open-Meteo.
    end = datetime.now(UTC).date() - timedelta(days=settings.WEATHER_API_LAG_DAYS)
    start = _years_before(end, settings.WEATHER_API_YEARS) + timedelta(days=1)
    use_cases = WeatherUseCases(CassandraDatacenterRepository(), CassandraDailyWeatherRepository())
    report = use_cases.ingest_daily_weather(
        OpenMeteoSource(), start, end, max_requests or settings.WEATHER_API_MAX_REQUESTS
    )
    status = " (stopped early: source unavailable)" if report.interrupted else ""
    return (
        f"Stored {report.saved_days} weather days in {report.requests} request(s){status}; "
        f"{report.complete_regions}/{report.regions} regions complete for {start}..{end}."
    )
