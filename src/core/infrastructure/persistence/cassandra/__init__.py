"""Cassandra persistence adapter for the Geodata context: session, schema, repositories.

Cassandra stores the geodata (bird observations, datacenters): append-heavy,
keyed data that grows without bound. Postgres keeps the application data
(Django, Celery Beat schedules and results). Tables are designed per query,
see `schema.py`.
"""
