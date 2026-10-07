"""Flux template"""

import logging
import time

logger = logging.getLogger(__name__)


def run() -> str:
    time.sleep(5)  # Simulate a long-running task
    logger.info("Flux template run completed.")
    return "ok"
