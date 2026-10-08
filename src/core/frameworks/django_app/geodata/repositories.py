"""Django ORM implementations of the Geodata repository ports."""

from __future__ import annotations

from datetime import date

from django.db.models import Max, Min

from core.domain.geodata.entities import BirdObservation, Datacenter
from core.domain.geodata.repositories import BirdObservationRepository, DatacenterRepository
from core.domain.geodata.value_objects import GeoPoint

from .models import BirdObservationModel, DatacenterModel


def _to_point(latitude: float | None, longitude: float | None) -> GeoPoint | None:
    if latitude is None or longitude is None:
        return None
    return GeoPoint(latitude=latitude, longitude=longitude)


def _to_observation(row: BirdObservationModel) -> BirdObservation:
    return BirdObservation(
        id=row.observation_id,
        common_name=row.common_name,
        scientific_name=row.scientific_name,
        observed_on=row.observed_on,
        location=_to_point(row.latitude, row.longitude),
    )


class DjangoBirdObservationRepository(BirdObservationRepository):
    def save_many(self, observations: list[BirdObservation]) -> int:
        rows = [
            BirdObservationModel(
                observation_id=o.id,
                common_name=o.common_name,
                scientific_name=o.scientific_name,
                observed_on=o.observed_on,
                latitude=o.location.latitude if o.location else None,
                longitude=o.location.longitude if o.location else None,
            )
            for o in observations
        ]
        BirdObservationModel.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["observation_id"],
            update_fields=[
                "common_name",
                "scientific_name",
                "observed_on",
                "latitude",
                "longitude",
                "updated_at",
            ],
        )
        return len(rows)

    def list_all(self) -> list[BirdObservation]:
        return [_to_observation(row) for row in BirdObservationModel.objects.all()]

    def id_bounds(self) -> tuple[int, int] | None:
        bounds = BirdObservationModel.objects.aggregate(
            low=Min("observation_id"), high=Max("observation_id")
        )
        return None if bounds["low"] is None else (bounds["low"], bounds["high"])

    def list_near(
        self,
        center: GeoPoint,
        radius_m: float,
        observed_from: date | None = None,
        observed_to: date | None = None,
    ) -> list[BirdObservation]:
        sql = (
            f"SELECT * FROM {BirdObservationModel._meta.db_table} "
            "WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
        )
        params: list[object] = [center.longitude, center.latitude, radius_m]
        if observed_from is not None:
            sql += " AND observed_on >= %s"
            params.append(observed_from)
        if observed_to is not None:
            sql += " AND observed_on <= %s"
            params.append(observed_to)
        return [_to_observation(row) for row in BirdObservationModel.objects.raw(sql, params)]


class DjangoDatacenterRepository(DatacenterRepository):
    def save_many(self, datacenters: list[Datacenter]) -> int:
        rows = [
            DatacenterModel(
                external_id=d.external_id,
                name=d.name,
                operator=d.operator,
                opened_on=d.opened_on,
                latitude=d.location.latitude,
                longitude=d.location.longitude,
            )
            for d in datacenters
        ]
        DatacenterModel.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["external_id"],
            update_fields=["name", "operator", "opened_on", "latitude", "longitude", "updated_at"],
        )
        return len(rows)

    def list_all(self) -> list[Datacenter]:
        return [
            Datacenter(
                external_id=row.external_id,
                name=row.name,
                operator=row.operator,
                opened_on=row.opened_on,
                location=GeoPoint(latitude=row.latitude, longitude=row.longitude),
            )
            for row in DatacenterModel.objects.all()
        ]
