"""Domain layer.

Pure business logic: entities, value objects, domain events and
repository interfaces. This layer has zero dependency on Django, Celery,
RabbitMQ or PostgreSQL — nothing here imports from `core.frameworks`.

Organized by bounded context (one subpackage per context, e.g.
`scheduling`). Add new contexts as siblings, not by mixing concepts
inside an existing one.
"""
