from __future__ import annotations

from functools import lru_cache

from automation.service import AutomationService, create_automation_service


@lru_cache
def get_automation_service() -> AutomationService:
    return create_automation_service()
