"""Open-Meteo historical weather adapter for `WeatherSource`.

Queries the archive API for the center of a region (1° grid cell), one
request per region and date range. Days are UTC (`timezone=GMT`) so they
line up with the other stored dates.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.application.geodata.ports import WeatherSource
from core.domain.geodata.entities import DailyWeather
from core.domain.geodata.value_objects import GridCell
from core.settings import config

from .http import ThrottledJsonClient

# Open-Meteo daily variable -> `DailyWeather` field.
DAILY_VARIABLES = {
    "temperature_2m_mean": "temperature_mean_c",
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "precipitation_sum": "precipitation_mm",
    "wind_speed_10m_max": "wind_speed_max_kmh",
    "relative_humidity_2m_mean": "relative_humidity_mean_pct",
}


def to_daily_weather(region: GridCell, payload: dict[str, Any]) -> list[DailyWeather]:
    """Map the API's column-oriented `daily` block to one entity per day."""
    daily = payload.get("daily") or {}
    columns = {field: daily.get(variable) or [] for variable, field in DAILY_VARIABLES.items()}
    days = []
    for i, day in enumerate(daily.get("time") or []):
        metrics = {
            field: float(values[i]) if i < len(values) and values[i] is not None else None
            for field, values in columns.items()
        }
        days.append(DailyWeather(region=region, day=date.fromisoformat(day), **metrics))
    return days


class OpenMeteoSource(WeatherSource):
    def __init__(self, retries: int = 4, backoff_s: float = 10.0):
        self.api_url = config.weather_api.WEATHER_API_URL
        # Throttled to stay under Open-Meteo's per-minute limit.
        self.client = ThrottledJsonClient(
            "Open-Meteo", config.weather_api.WEATHER_API_DELAY_S, retries, backoff_s, timeout_s=60
        )

    def fetch_daily(self, region: GridCell, start: date, end: date) -> list[DailyWeather]:
        center = region.center
        payload = self.client.get(
            self.api_url,
            {
                "latitude": center.latitude,
                "longitude": center.longitude,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": ",".join(DAILY_VARIABLES),
                "timezone": "GMT",
            },
        )
        return to_daily_weather(region, payload)
