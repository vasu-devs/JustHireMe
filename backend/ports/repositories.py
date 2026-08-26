"""Repository ports.

Every method here is one the application actually calls today — the surface was
derived from real `repo.<store>.<method>` call sites, not invented. Adding a
method to a store means adding it here first; that is the point.

**Tenancy note (Stage 2).** These are the seams where `tenant_id` gets injected.
The scoping will live in the *adapter's constructor*, never in a method
parameter, so a caller cannot forget to pass it:

    class PostgresLeadRepository(LeadStore):
        def __init__(self, conn: Connection, tenant: TenantContext) -> None: ...

Keeping the port signatures free of `tenant_id` is deliberate: business code
must not be able to name another tenant.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# --------------------------------------------------------------------- leads


@runtime_checkable
class LeadReader(Protocol):
    """Read side of the lead store. Handed to anything that must not write."""

    def get_all_leads(self) -> list[dict]: ...
    def get_lead_by_id(self, job_id: str) -> dict | None: ...
    def get_discovered_leads(self) -> list[dict]: ...
    def get_due_followups(self, limit: int, now: str) -> list[dict]: ...
    def get_job_leads_for_evaluation(self, *args: Any, **kwargs: Any) -> list[dict]: ...
    def get_leads_for_learning(self, limit: int) -> list[dict]: ...
    def get_lead_for_fire(self, *args: Any, **kwargs: Any) -> Any: ...
    def get_resume_version(self, *args: Any, **kwargs: Any) -> Any: ...
    def url_exists(self, url: str) -> bool: ...


@runtime_checkable
class LeadWriter(Protocol):
    """Write side of the lead store."""

    def save_lead(self, lead: dict) -> Any: ...
    def delete_lead(self, job_id: str) -> Any: ...
    def update_lead_status(self, job_id: str, status: str) -> Any: ...
    def update_lead_score(self, *args: Any, **kwargs: Any) -> Any: ...
    def update_lead_followup(self, job_id: str, now: str, due: str) -> Any: ...
    def update_learning_scores(self, *args: Any, **kwargs: Any) -> Any: ...
    def update_outreach_fields(self, job_id: str, fields: dict) -> Any: ...
    def save_lead_feedback(self, job_id: str, feedback: str, note: str) -> Any: ...
    def save_asset_package(self, *args: Any, **kwargs: Any) -> Any: ...
    def save_generated_asset_version(self, *args: Any, **kwargs: Any) -> Any: ...
    def save_contact_lookup(self, job_id: str, contacts: dict) -> Any: ...
    def mark_applied(self, job_id: str) -> Any: ...
    def cleanup_bad_leads(self, limit: int, dry_run: bool) -> dict: ...


@runtime_checkable
class LeadStore(LeadReader, LeadWriter, Protocol):
    """Both sides, for components that genuinely need read and write."""


# ------------------------------------------------------------------ settings


@runtime_checkable
class SettingsReader(Protocol):
    def get_settings(self) -> dict: ...
    def get_setting(self, key: str, default: str = "") -> Any: ...


@runtime_checkable
class SettingsWriter(Protocol):
    def save_settings(self, payload: dict) -> Any: ...


@runtime_checkable
class SettingsStore(SettingsReader, SettingsWriter, Protocol):
    """Application settings. Per-tenant in the web build."""


# -------------------------------------------------------------------- events


@runtime_checkable
class EventStore(Protocol):
    """The activity log."""

    def get_events(self, limit: int, job_id: str | None = None) -> list[dict]: ...
    def record_event(self, *args: Any, **kwargs: Any) -> Any: ...


# ------------------------------------------------------------------- profile


@runtime_checkable
class ProfileStore(Protocol):
    """The candidate graph.

    Kùzu has no row-level security, so tenancy here is **namespace isolation** —
    one graph per tenant, resolved centrally in `core/paths.py`. A filter bug in
    a graph query would be silent and unauditable; a wrong path is not.
    """

    def get_profile(self) -> dict: ...


# --------------------------------------------------------------------- graph


@runtime_checkable
class GraphStore(Protocol):
    def graph_available(self) -> bool: ...
    def graph_counts(self) -> dict: ...
    def graph_error(self) -> str: ...
    def graph_snapshot(self) -> dict: ...
    def sync_job_leads(self, leads: list[dict]) -> dict: ...
    def sync_profile_relationships(self) -> dict: ...


# -------------------------------------------------------------------- vectors


@runtime_checkable
class VectorStore(Protocol):
    """LanceDB. Same namespace-isolation reasoning as ProfileStore."""

    @property
    def vec(self) -> Any: ...


# ------------------------------------------------------------------- feedback


@runtime_checkable
class FeedbackStore(Protocol):
    def get_feedback_training_examples(self) -> list[dict]: ...
    def rank_lead_by_feedback(self, *args: Any, **kwargs: Any) -> Any: ...


# ------------------------------------------------------------------ templates


@runtime_checkable
class TemplateStore(Protocol):
    def list_templates(self) -> list[dict]: ...
    def get_template(self, template_id: str) -> dict | None: ...
    def create_template(self, name: str, content: str, filename: str, make_default: bool | None = None) -> dict: ...
    def set_default_template(self, template_id: str) -> bool: ...
    def delete_template(self, template_id: str) -> bool: ...
    def resolve_template_content(self, template_id: str) -> str: ...
