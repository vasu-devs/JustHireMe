"""Lead lifecycle business layer.

Owns everything that happens to a lead after discovery and before automation:
listing and filtering, status transitions, feedback, follow-ups, generated
asset versions, CSV export, manually pasted leads, and the activity log.

The API layer calls this; this calls the repository. Never the other way round.
"""

from leads.service import LeadService, create_lead_service

__all__ = ["LeadService", "create_lead_service"]
