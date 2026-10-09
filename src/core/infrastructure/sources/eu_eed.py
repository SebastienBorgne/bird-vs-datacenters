"""EU Energy Efficiency Directive (EED) reporting adapter for `EnergyBenchmarkSource`.

Datacenters of at least 500 kW installed IT power report their yearly energy use
to the European database (Delegated Regulation (EU) 2024/1364). Per-site figures
stay confidential; the Commission only publishes aggregates per Member State, in
a dashboard without an API and in reports. So the figures below are transcribed
from the Commission's July 2025 report on the first reporting period (2024,
covering calendar year 2023), "Assessment of the energy performance and
sustainability of data centres in EU" (EY, AIT, Borderstep):
https://op.europa.eu/o/opportal-service/download-handler?identifier=83be4c3e-5c79-11f0-a9d0-01aa75ed71a1&format=PDF&language=en&productionSystem=cellar

- installed IT power and energy use: Table 24 (totals of all reporting datacenters);
- reporting datacenters: Table 19 (sites that reported both total and IT energy
  use, the closest published count to the sites behind the energy totals).

Countries without any reporting datacenter (CY, CZ, EE, RO, SK, SI) are absent.
Update when the Commission publishes a newer year (dashboard linked from
https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficiency-targets-directive-and-rules/energy-efficiency-directive/energy-performance-data-centres_en).
"""

from __future__ import annotations

from core.application.geodata.ports import EnergyBenchmarkSource
from core.domain.geodata.entities import CountryEnergyBenchmark

YEAR = 2023

# country: (reporting datacenters, installed IT power in MW, energy use in GWh)
_BENCHMARKS: dict[str, tuple[int, float, float]] = {
    "AT": (10, 16.14, 111.10),
    "BE": (15, 236.13, 1070.95),
    "BG": (3, 4.11, 20.14),
    "DE": (319, 946.87, 4608.53),
    "DK": (17, 193.74, 731.28),
    "EL": (4, 1.78, 36.90),
    "ES": (36, 101.03, 603.63),
    "FI": (25, 219.67, 1091.18),
    "FR": (124, 1311.43, 2416.90),
    "HR": (1, 0.88, 7.71),
    "HU": (1, 0.53, 6.52),
    "IE": (18, 315.92, 1411.76),
    "IT": (22, 92.02, 350.24),
    "LT": (3, 2.30, 18.00),
    "LU": (1, 11.20, 53.22),
    "LV": (1, 0.70, 6.30),
    "MT": (1, 0.64, 7.95),
    "NL": (54, 102.76, 574.87),
    "PL": (32, 59.05, 276.55),
    "PT": (4, 7.67, 48.75),
    "SE": (4, 114.30, 635.53),
}

# The EU writes Greece "EL"; OpenStreetMap and ISO 3166-1 use "GR".
_ISO_CODES = {"EL": "GR"}


class EedReportSource(EnergyBenchmarkSource):
    def fetch_all(self) -> list[CountryEnergyBenchmark]:
        return [
            CountryEnergyBenchmark(
                country=_ISO_CODES.get(code, code),
                year=YEAR,
                reporting_datacenters=sites,
                it_power_mw=it_power_mw,
                energy_gwh=energy_gwh,
            )
            for code, (sites, it_power_mw, energy_gwh) in _BENCHMARKS.items()
        ]
