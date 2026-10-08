"""Django app for the Geodata context — migration history only.

Bird observations and datacenters used to live in PostGIS tables here; they
now live in Cassandra (`core.infrastructure.persistence.cassandra`).
Migration 0002 copies the rows over and 0003 drops the tables, so the app
stays installed for those migrations to run on existing databases.
"""
