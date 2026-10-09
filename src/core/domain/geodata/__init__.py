"""Geodata bounded context.

Owns geolocated facts the app compares: `BirdObservation`s (where/when a
bird was seen) and `Datacenter`s (where/when one opened). Both carry a
`GeoPoint` so they can be matched by distance and date, e.g. bird
sightings around a datacenter before vs. after its opening. `DailyWeather`
describes the region (`GridCell`) around datacenters, day by day.
`DatacenterPowerEstimate`s size each datacenter's electricity use from
per-country `CountryEnergyBenchmark`s.
"""
