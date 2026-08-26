"""Tenant identity — the Common-layer primitive the whole isolation model rests on.

Design rules, in order of importance:

1. **A ``TenantContext`` is only ever built from an authenticated session.** There
   is deliberately no ``TenantContext.from_request_header`` or
   ``from_query_param``; a tenant id that a client can name is not a tenant id.
2. **It is injected into an adapter's constructor, never passed to a method.**
   Business code therefore has no way to name a different tenant — the leak is
   unrepresentable rather than merely unlikely.
   (Enforced by ``tests/unit/architecture/test_repository_ports.py``.)
3. **The desktop build has exactly one tenant.** ``LOCAL_TENANT`` keeps the
   local-first app working unchanged while the web build grows real tenants, so
   this migration never needs a "is this hosted?" branch in domain code.

The relational stores scope by ``tenant_id`` column + Postgres RLS. Kùzu and
LanceDB have no row-level security, so they scope by *namespace* — a separate
store per tenant, resolved by :func:`core.paths.tenant_data_dir`. A filter bug in
a vector search is silent and unauditable; a wrong directory is neither.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: The single tenant the local desktop app runs as. A real UUID (not "local" or
#: "default") so the same column type and RLS predicate work in both builds and
#: a desktop database can be imported into the hosted one unchanged.
LOCAL_TENANT_ID: Final = "00000000-0000-0000-0000-000000000001"

_TENANT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class InvalidTenantError(ValueError):
    """A tenant id that is not a UUID. Never surfaced to a client verbatim."""


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Who the current work belongs to.

    Frozen: a request's tenant cannot be reassigned halfway through handling it.
    """

    tenant_id: str

    def __post_init__(self) -> None:
        if not _TENANT_ID_RE.match(str(self.tenant_id or "").lower()):
            # Deliberately does not echo the offending value — it reaches this
            # path from a session, and session material does not belong in logs.
            raise InvalidTenantError("tenant id must be a UUID")

    @property
    def is_local(self) -> bool:
        """True for the single-tenant desktop build."""
        return self.tenant_id == LOCAL_TENANT_ID

    @property
    def namespace(self) -> str:
        """Filesystem-safe directory name for stores without row-level security."""
        return self.tenant_id

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"tenant:{self.tenant_id[:8]}"


#: The desktop app's tenant. The hosted build never uses this.
LOCAL_TENANT: Final = TenantContext(LOCAL_TENANT_ID)


def local_tenant() -> TenantContext:
    return LOCAL_TENANT
