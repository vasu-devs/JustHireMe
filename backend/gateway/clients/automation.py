from __future__ import annotations

from gateway.clients.base import BaseServiceClient


class AutomationHttpClient(BaseServiceClient):
    service_name = "automation"
    timeout = 180.0

    async def read_form(self, url: str, identity: dict, *, cover_letter: str = "") -> dict:
        return await self._request(
            "POST",
            "/internal/v1/automation/form-read",
            json={"url": url, "identity": identity, "cover_letter": cover_letter},
            timeout=180.0,
        )

    async def preview_application(self, lead: dict, asset: str) -> dict:
        return await self._request("POST", "/internal/v1/automation/preview-apply", json={"lead": lead, "asset": asset}, timeout=180.0)

    async def submit_application(self, lead: dict, asset: str) -> bool:
        data = await self._request("POST", "/internal/v1/automation/fire", json={"lead": lead, "asset": asset}, timeout=180.0)
        return bool(data.get("ok"))

    async def refresh_selectors(self) -> dict:
        return await self._request("POST", "/internal/v1/automation/selectors/refresh", json={}, timeout=90.0)
