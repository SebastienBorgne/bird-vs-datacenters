"""Datacenter power flow: wires the EU EED country benchmarks and Cassandra into the power
estimation use case. Run it after the datacenters flow, which stores the floor areas and
countries it relies on.
"""

from __future__ import annotations

from core.application.geodata.use_cases import PowerUseCases
from core.infrastructure.persistence.cassandra.repositories import (
    CassandraDatacenterPowerEstimateRepository,
    CassandraDatacenterRepository,
)
from core.infrastructure.sources.eu_eed import EedReportSource


def run() -> str:
    use_cases = PowerUseCases(
        CassandraDatacenterRepository(), CassandraDatacenterPowerEstimateRepository()
    )
    report = use_cases.estimate_datacenter_power(EedReportSource())
    bases = ", ".join(f"{count} by {basis}" for basis, count in sorted(report.by_basis.items()))
    unmatched = (
        f"; no datacenter stored for {', '.join(report.unmatched_countries)}"
        if report.unmatched_countries
        else ""
    )
    return f"Stored {report.saved} power estimates ({bases}){unmatched}."
