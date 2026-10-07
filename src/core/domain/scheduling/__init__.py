"""Scheduling bounded context.

Owns the concept of a `Job` (a recurring unit of work) and its
`Execution`s (individual runs). This is the core domain of the
ordonnanceur: everything else (Django admin, Celery, RabbitMQ) is an
adapter around it.
"""
