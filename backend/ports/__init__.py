"""Ports — the interfaces the business layer depends on.

The business layer talks to these Protocols, never to a concrete store. Today the
adapters are the SQLite/Kùzu/LanceDB modules under ``data/``; in the web build
they become tenant-scoped Postgres repositories constructed with a
``TenantContext``. Nothing in ``discovery/``, ``ranking/``, ``leads/`` … needs to
change when that swap happens, because they only ever knew the port.

Interfaces are segregated by capability (reader vs writer) so a component that
only reads cannot be handed something that writes.
"""

from ports.repositories import (
    EventStore,
    FeedbackStore,
    GraphStore,
    LeadReader,
    LeadStore,
    LeadWriter,
    ProfileStore,
    SettingsReader,
    SettingsStore,
    SettingsWriter,
    TemplateStore,
    VectorStore,
)

__all__ = [
    "EventStore",
    "FeedbackStore",
    "GraphStore",
    "LeadReader",
    "LeadStore",
    "LeadWriter",
    "ProfileStore",
    "SettingsReader",
    "SettingsStore",
    "SettingsWriter",
    "TemplateStore",
    "VectorStore",
]
