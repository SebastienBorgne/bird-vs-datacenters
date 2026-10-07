"""ORM models for the Geodata context.

Each table also has a database-generated `location geography(Point, 4326)`
column, added in the initial migration and deliberately left out of the
models: the ORM never writes it, PostGIS keeps it in sync with
`latitude`/`longitude`, and spatial queries use it via raw SQL.
"""

from __future__ import annotations

from django.db import models


class BirdObservationModel(models.Model):
    observation_id = models.BigIntegerField(primary_key=True)
    common_name = models.CharField(max_length=255, null=True, blank=True)
    scientific_name = models.CharField(max_length=255, null=True, blank=True)
    observed_on = models.DateField(null=True, blank=True, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "geodata_bird_observation"
        verbose_name = "bird observation"

    def __str__(self) -> str:
        return f"{self.common_name or self.scientific_name} ({self.observed_on})"


class DatacenterModel(models.Model):
    external_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    operator = models.CharField(max_length=255, null=True, blank=True)
    opened_on = models.DateField(null=True, blank=True, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "geodata_datacenter"
        verbose_name = "datacenter"

    def __str__(self) -> str:
        return self.name
