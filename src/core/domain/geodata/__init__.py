"""Geodata bounded context.

Owns geolocated facts the app compares: `BirdObservation`s (where/when a
bird was seen) and `Datacenter`s (where/when one opened). Both carry a
`GeoPoint` so they can be matched by distance and date, e.g. bird
sightings around a datacenter before vs. after its opening.
"""
