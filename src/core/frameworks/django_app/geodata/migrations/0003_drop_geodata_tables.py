"""Drop the legacy Postgres geodata tables: Cassandra is the geodata store now (see 0002)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("geodata", "0002_copy_geodata_to_cassandra"),
    ]

    operations = [
        migrations.DeleteModel(name="BirdObservationModel"),
        migrations.DeleteModel(name="DatacenterModel"),
    ]
