from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway.clients.base import BaseServiceClient


@dataclass(frozen=True)
class GenerationResult:
    package: dict[str, Any]
    contact_lookup: dict[str, Any] | None = None


class GenerationHttpClient(BaseServiceClient):
    service_name = "generation"
    timeout = 240.0

    async def generate_with_contacts(self, lead: dict, *, template: str = "", include_contacts: bool = True) -> GenerationResult:
        data = await self._request(
            "POST",
            "/internal/v1/generation/package",
            json={"lead": lead, "template": template, "include_contacts": include_contacts},
            timeout=240.0,
        )
        return GenerationResult(package=data.get("package") or {}, contact_lookup=data.get("contact_lookup"))

    async def generate_package(self, lead: dict, template: str = "") -> dict:
        result = await self.generate_with_contacts(lead, template=template, include_contacts=False)
        return result.package
