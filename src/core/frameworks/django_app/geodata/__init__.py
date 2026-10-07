"""Django app for the Geodata context: models, admin, ORM-backed repositories.

Tables live in PostGIS. Each one stores plain `latitude`/`longitude`
columns (what the ORM reads/writes) plus a `location geography(Point)`
column generated from them by the database and GiST-indexed (see the
initial migration), so distance queries (`ST_DWithin`, `ST_Distance`)
run in SQL without requiring GeoDjango's GDAL/GEOS system libraries.
"""
