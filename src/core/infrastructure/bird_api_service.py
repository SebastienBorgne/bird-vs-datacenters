"""Service to interact with  the API and retrieve data."""

from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException

from core.settings import config

load_dotenv()


class BirdApiService:
    def __init__(self):
        self.api_url = config.bird_api.BIRD_API_URL

    def extract_data(self):
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            print(f"Error fetching data from API: {e}")
            return []

    def transform_data(self, payload: dict[str, Any]) -> pd.DataFrame:
        observations = payload.get("results", []) if isinstance(payload, dict) else []
        records = []

        for observation in observations:
            taxon = observation.get("taxon") or {}
            coordinates = (observation.get("geojson") or {}).get("coordinates") or []
            longitude = coordinates[0] if len(coordinates) >= 2 else None
            latitude = coordinates[1] if len(coordinates) >= 2 else None

            records.append(
                {
                    "observation_id": observation.get("id"),
                    "common_name": taxon.get("preferred_common_name")
                    or observation.get("species_guess"),
                    "scientific_name": taxon.get("name"),
                    "observed_on": observation.get("observed_on"),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        return pd.DataFrame.from_records(
            records,
            columns=[
                "observation_id",
                "common_name",
                "scientific_name",
                "observed_on",
                "latitude",
                "longitude",
            ],
        )
