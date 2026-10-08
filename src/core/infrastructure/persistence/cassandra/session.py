"""Shared Cassandra session.

Created lazily, once per process: Celery's prefork workers must not inherit
a session opened in the parent (the driver's connections and threads don't
survive a fork), so nothing connects at import time.
"""

from __future__ import annotations

from functools import cache

from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile, Session
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy
from core.settings import config


@cache
def get_cluster() -> Cluster:
    settings = config.cassandra
    profile = ExecutionProfile(
        load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(settings.LOCAL_DC)),
        request_timeout=30,
    )
    return Cluster(
        contact_points=settings.HOSTS,
        port=settings.PORT,
        execution_profiles={EXEC_PROFILE_DEFAULT: profile},
    )


@cache
def get_session() -> Session:
    """Session bound to the geodata keyspace (which `schema.py` creates)."""
    return get_cluster().connect(config.cassandra.KEYSPACE)
