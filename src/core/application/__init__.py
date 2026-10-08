"""Application layer: use cases orchestrating the domain through ports.

Depends only on `core.domain`. Adapters implementing the ports live in
`core.infrastructure`; entry points (flows, CLI, dashboard) wire them in.
"""
