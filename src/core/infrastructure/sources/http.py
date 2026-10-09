"""Throttled JSON GET with retries, shared by the source adapters."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.exceptions import RequestException

from core.application.geodata.ports import SourceUnavailableError

logger = logging.getLogger(__name__)

USER_AGENT = "birdy/0.1 (bird-vs-datacenters)"


class ThrottledJsonClient:
    """Waits `delay_s` between requests and retries failures with exponential backoff,
    then raises `SourceUnavailableError`.
    """

    def __init__(
        self, name: str, delay_s: float, retries: int, backoff_s: float, timeout_s: float = 30
    ) -> None:
        self.name = name
        self.delay_s = delay_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s
        self._last_request_at = 0.0

    def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self.retries + 1):
            time.sleep(max(0.0, self._last_request_at + self.delay_s - time.monotonic()))
            self._last_request_at = time.monotonic()
            try:
                response = requests.get(
                    url, params=params, headers={"User-Agent": USER_AGENT}, timeout=self.timeout_s
                )
                response.raise_for_status()
                return response.json()
            except (RequestException, ValueError) as e:
                logger.warning("%s request failed (attempt %d): %s", self.name, attempt, e)
                if attempt == self.retries:
                    raise SourceUnavailableError(f"{self.name}: {e}") from e
                time.sleep(self.backoff_s * 2 ** (attempt - 1))
        raise AssertionError("unreachable")
