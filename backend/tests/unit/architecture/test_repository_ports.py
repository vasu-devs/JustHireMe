"""The concrete stores must satisfy the ports the business layer depends on.

Without this the Protocols are documentation. With it, renaming or dropping a
store method fails the build at the seam instead of at runtime in a router.

This is also the Stage 2 tripwire: when the SQLite modules are replaced by
tenant-scoped Postgres repositories, these same assertions must still pass
against the new adapters — that is what makes the swap safe.
"""

from __future__ import annotations

import pytest

from data.repository import create_repository
from ports import (
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
)

#: Every port, and the repository attribute expected to satisfy it.
PORT_BINDINGS = [
    ("leads", LeadReader),
    ("leads", LeadWriter),
    ("leads", LeadStore),
    ("settings", SettingsReader),
    ("settings", SettingsWriter),
    ("settings", SettingsStore),
    ("events", EventStore),
    ("profile", ProfileStore),
    ("graph", GraphStore),
    ("feedback", FeedbackStore),
    ("resume_templates", TemplateStore),
]


@pytest.mark.parametrize("attribute, port", PORT_BINDINGS, ids=lambda v: getattr(v, "__name__", v))
def test_the_live_store_satisfies_its_port(attribute, port):
    store = getattr(create_repository(), attribute)
    missing = [
        name for name in port.__protocol_attrs__
        if not hasattr(store, name)
    ]
    assert not missing, f"repo.{attribute} is missing {port.__name__} members: {sorted(missing)}"


def test_the_vector_store_exposes_its_handle():
    # VectorStore declares `vec` as a property, which runtime_checkable cannot
    # verify structurally on a module, so assert the attribute directly.
    assert hasattr(create_repository().vector, "vec")


def test_reader_and_writer_are_genuinely_separate_capabilities():
    """Interface segregation: a read-only consumer must not gain write methods."""
    read_only = set(LeadReader.__protocol_attrs__)
    write_only = set(LeadWriter.__protocol_attrs__)
    assert not (read_only & write_only), "a method cannot be on both sides of the split"
    assert "save_lead" in write_only and "save_lead" not in read_only
    assert "get_all_leads" in read_only and "get_all_leads" not in write_only


def test_ports_never_take_a_tenant_argument():
    """Tenancy is injected at construction, never passed by a caller.

    If a port method grew a `tenant_id` parameter, business code could name
    another tenant — the exact confidentiality bug the scoped-repository layer
    exists to make unrepresentable.
    """
    import inspect

    offenders: list[str] = []
    for port in (LeadReader, LeadWriter, SettingsReader, SettingsWriter, EventStore,
                 ProfileStore, GraphStore, FeedbackStore, TemplateStore):
        for name in port.__protocol_attrs__:
            member = getattr(port, name, None)
            if not callable(member):
                continue
            params = inspect.signature(member).parameters
            if any(p in params for p in ("tenant", "tenant_id", "user_id")):
                offenders.append(f"{port.__name__}.{name}")

    assert not offenders, f"tenancy must be constructor-injected, not a parameter: {offenders}"
