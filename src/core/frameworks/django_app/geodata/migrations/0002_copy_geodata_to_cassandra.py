"""Copy bird observations and datacenters to Cassandra, before 0003 drops these tables.

Fails (and so stops before 0003) if any row is missing from Cassandra after
the copy. The Cassandra schema must exist: the compose `init` service
creates it before running Django migrations. A database with no geodata
rows (fresh install) doesn't touch Cassandra at all.
"""

from django.db import migrations


def copy_to_cassandra(apps, schema_editor):  # pylint: disable=unused-argument
    # pylint: disable=import-outside-toplevel
    from core.domain.geodata.entities import BirdObservation, Datacenter
    from core.domain.geodata.value_objects import GeoPoint
    from core.infrastructure.persistence.cassandra.repositories import (
        CassandraBirdObservationRepository,
        CassandraDatacenterRepository,
    )
    from core.infrastructure.persistence.transfer import transfer_geodata

    bird_model = apps.get_model("geodata", "BirdObservationModel")
    datacenter_model = apps.get_model("geodata", "DatacenterModel")
    if not bird_model.objects.exists() and not datacenter_model.objects.exists():
        return

    def point(row):
        if row.latitude is None or row.longitude is None:
            return None
        return GeoPoint(latitude=row.latitude, longitude=row.longitude)

    birds = (
        BirdObservation(
            id=row.observation_id,
            common_name=row.common_name,
            scientific_name=row.scientific_name,
            observed_on=row.observed_on,
            location=point(row),
        )
        for row in bird_model.objects.order_by("observation_id").iterator(chunk_size=5_000)
    )
    datacenters = (
        Datacenter(
            external_id=row.external_id,
            name=row.name,
            location=point(row),
            operator=row.operator,
            opened_on=row.opened_on,
        )
        for row in datacenter_model.objects.iterator(chunk_size=5_000)
    )
    report = transfer_geodata(
        birds, datacenters, CassandraBirdObservationRepository(), CassandraDatacenterRepository()
    )
    print(
        f"\n    Copied {report.bird_observations} bird observations and "
        f"{report.datacenters} datacenters to Cassandra (verified)."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("geodata", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_to_cassandra, reverse_code=migrations.RunPython.noop),
    ]
