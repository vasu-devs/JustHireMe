from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

import httpx

from discovery.service import DiscoveryRunResult
from generation.service import GenerationResult
from ranking.service import ReevaluationResult


@dataclass(frozen=True)
class ServiceEndpoint:
    name: str
    base_url: str
    token: str
    status: str = "starting"


class ServiceRegistry:
    def __init__(self, endpoints: dict[str, ServiceEndpoint] | None = None):
        self._endpoints = endpoints or {}

    def set(self, endpoint: ServiceEndpoint) -> None:
        self._endpoints[endpoint.name] = endpoint

    def get(self, name: str) -> ServiceEndpoint | None:
        return self._endpoints.get(name)

    def snapshot(self) -> dict[str, dict]:
        return {
            name: {
                "name": endpoint.name,
                "base_url": endpoint.base_url,
                "status": endpoint.status,
            }
            for name, endpoint in self._endpoints.items()
        }


_registry: ServiceRegistry | None = None


def set_service_registry(registry: ServiceRegistry | None) -> None:
    global _registry
    _registry = registry


def get_service_registry() -> ServiceRegistry | None:
    return _registry


class ServiceRequestError(RuntimeError):
    pass


class BaseServiceClient:
    service_name = ""
    timeout = 60.0

    def __init__(self, endpoint: ServiceEndpoint):
        self.endpoint = endpoint

    async def _request(self, method: str, path: str, *, json: dict | None = None, timeout: float | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.endpoint.token}"}
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response = await client.request(method, f"{self.endpoint.base_url}{path}", headers=headers, json=json)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            raise ServiceRequestError(f"{self.service_name} service unavailable: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise ServiceRequestError(f"{self.service_name} service returned {response.status_code}: {detail}")
        return response.json()


class GenerationHttpClient(BaseServiceClient):
    service_name = "generation"
    timeout = 180.0

    async def generate_with_contacts(self, lead: dict, *, template: str = "", include_contacts: bool = True) -> GenerationResult:
        data = await self._request(
            "POST",
            "/internal/v1/generation/package",
            json={"lead": lead, "template": template, "include_contacts": include_contacts},
            timeout=180.0,
        )
        return GenerationResult(package=data.get("package") or {}, contact_lookup=data.get("contact_lookup"))

    async def generate_package(self, lead: dict, template: str = "") -> dict:
        result = await self.generate_with_contacts(lead, template=template, include_contacts=False)
        return result.package


class RankingHttpClient(BaseServiceClient):
    service_name = "ranking"
    timeout = 90.0

    async def evaluate_lead(self, lead: dict, profile: dict) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/score", json={"lead": lead, "profile": profile}, timeout=90.0)
        return data.get("result") or {}

    async def deterministic_score(self, lead: dict | str, profile: dict) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/deterministic-score", json={"lead": lead, "profile": profile}, timeout=60.0)
        return data.get("result") or {}

    async def semantic_match(self, lead: dict | str, profile: dict) -> dict | None:
        data = await self._request("POST", "/internal/v1/ranking/semantic-match", json={"lead": lead, "profile": profile}, timeout=60.0)
        return data.get("result") or None

    async def apply_feedback(self, lead: dict, examples: list[dict]) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/apply-feedback", json={"lead": lead, "examples": examples}, timeout=60.0)
        return data.get("result") or lead

    async def reevaluate_all(self, leads: list[dict], profile: dict, *, stop_event: asyncio.Event | None = None) -> ReevaluationResult:
        result = ReevaluationResult(total=len(leads))
        for lead in leads:
            if stop_event and stop_event.is_set():
                break
            try:
                scored = await self.evaluate_lead(lead, profile)
                result.scored += 1
                result.items.append({**lead, **scored})
            except Exception:
                result.failed += 1
        return result


class DiscoveryHttpClient(BaseServiceClient):
    service_name = "discovery"
    timeout = 180.0

    async def plan_board_targets(self, profile: dict, raw_urls: list[str], market_focus: str = "global") -> list[str]:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/plan",
            json={"profile": profile, "raw_urls": raw_urls, "market_focus": market_focus},
        )
        return list(data.get("urls") or [])

    async def scan_job_boards(self, urls: list[str], cfg: dict) -> DiscoveryRunResult:
        data = await self._request("POST", "/internal/v1/discovery/scan", json={"urls": urls, "cfg": cfg}, timeout=240.0)
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])

    async def scan_free_sources(self, cfg: dict, *, kind_filter: str | None = None, profile: dict | None = None, force: bool = False) -> DiscoveryRunResult:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/free-sources",
            json={"cfg": cfg, "profile": profile, "kind_filter": kind_filter, "force": force},
            timeout=180.0,
        )
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])

    async def scan_x(self, cfg: dict, *, kind_filter: str = "job", profile: dict | None = None) -> DiscoveryRunResult:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/x",
            json={"cfg": cfg, "profile": profile, "kind_filter": kind_filter},
            timeout=180.0,
        )
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])


class GraphHttpClient(BaseServiceClient):
    service_name = "graph"
    timeout = 60.0

    async def stats(self, *, repair: bool = False) -> dict:
        return await self._request("POST", "/internal/v1/graph/stats", json={"repair": repair}, timeout=60.0)


class AutomationHttpClient(BaseServiceClient):
    service_name = "automation"
    timeout = 120.0

    async def read_form(self, url: str, identity: dict, *, cover_letter: str = "") -> dict:
        return await self._request(
            "POST",
            "/internal/v1/automation/form-read",
            json={"url": url, "identity": identity, "cover_letter": cover_letter},
            timeout=120.0,
        )

    async def preview_application(self, lead: dict, asset: str) -> dict:
        return await self._request("POST", "/internal/v1/automation/preview-apply", json={"lead": lead, "asset": asset}, timeout=120.0)

    async def refresh_selectors(self) -> dict:
        return await self._request("POST", "/internal/v1/automation/selectors/refresh", json={}, timeout=60.0)

    async def get_lead_for_fire(self, job_id: str):
        from automation.service import get_lead_for_fire_sync
        from data.repository import create_repository

        return await asyncio.to_thread(get_lead_for_fire_sync, job_id, create_repository())

    async def submit_application(self, lead: dict, asset: str) -> bool:
        from automation.service import actuate

        return await asyncio.to_thread(actuate, lead, asset)

    async def mark_applied(self, job_id: str) -> None:
        from data.repository import create_repository

        repo = create_repository()
        await asyncio.to_thread(repo.leads.mark_applied, job_id)


def generation_client() -> GenerationHttpClient | None:
    endpoint = _registry.get("generation") if _registry else None
    return GenerationHttpClient(endpoint) if endpoint else None


def ranking_client() -> RankingHttpClient | None:
    endpoint = _registry.get("ranking") if _registry else None
    return RankingHttpClient(endpoint) if endpoint else None


def discovery_client() -> DiscoveryHttpClient | None:
    endpoint = _registry.get("discovery") if _registry else None
    return DiscoveryHttpClient(endpoint) if endpoint else None


def graph_client() -> GraphHttpClient | None:
    endpoint = _registry.get("graph") if _registry else None
    return GraphHttpClient(endpoint) if endpoint else None


def automation_client() -> AutomationHttpClient | None:
    endpoint = _registry.get("automation") if _registry else None
    return AutomationHttpClient(endpoint) if endpoint else None


class ProfileHttpClient(BaseServiceClient):
    service_name = "profile"
    timeout = 120.0

    async def get_profile(self) -> dict:
        return await self._request("GET", "/internal/v1/profile")

    async def update_candidate(self, n: str, s: str) -> dict:
        return await self._request("PUT", "/internal/v1/profile/candidate", json={"n": n, "s": s})

    async def add_skill(self, n: str, cat: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/skill", json={"n": n, "cat": cat})

    async def update_skill(self, sid: str, n: str, cat: str) -> dict:
        return await self._request("PUT", f"/internal/v1/profile/skill/{sid}", json={"n": n, "cat": cat})

    async def delete_skill(self, sid: str) -> dict:
        return await self._request("DELETE", f"/internal/v1/profile/skill/{sid}")

    async def add_experience(self, role: str, co: str, period: str, d: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/experience", json={"role": role, "co": co, "period": period, "d": d})

    async def update_experience(self, eid: str, role: str, co: str, period: str, d: str) -> dict:
        return await self._request("PUT", f"/internal/v1/profile/experience/{eid}", json={"role": role, "co": co, "period": period, "d": d})

    async def delete_experience(self, eid: str) -> dict:
        return await self._request("DELETE", f"/internal/v1/profile/experience/{eid}")

    async def add_project(self, title: str, stack: str, repo: str, impact: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/project", json={"title": title, "stack": stack, "repo": repo, "impact": impact})

    async def update_project(self, pid: str, title: str, stack: str, repo: str, impact: str) -> dict:
        return await self._request("PUT", f"/internal/v1/profile/project/{pid}", json={"title": title, "stack": stack, "repo": repo, "impact": impact})

    async def delete_project(self, pid: str) -> dict:
        return await self._request("DELETE", f"/internal/v1/profile/project/{pid}")

    async def ingest_resume(self, raw: str = "", pdf_path: str | None = None):
        return await self._request("POST", "/internal/v1/profile/ingest/resume", json={"raw": raw, "pdf_path": pdf_path}, timeout=180.0)

    async def ingest_github(self, username: str, *, token: str | None = None, max_repos: int = 12) -> dict:
        return await self._request("POST", "/internal/v1/profile/ingest/github", json={"username": username, "token": token, "max_repos": max_repos}, timeout=180.0)

    async def ingest_linkedin(self, zip_bytes: bytes) -> dict:
        zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
        return await self._request("POST", "/internal/v1/profile/ingest/linkedin", json={"zip_b64": zip_b64}, timeout=180.0)

    async def ingest_portfolio(self, url: str, *, auto_import: bool = False) -> dict:
        return await self._request("POST", "/internal/v1/profile/ingest/portfolio", json={"url": url, "auto_import": auto_import}, timeout=180.0)

    async def import_profile_data(self, payload) -> dict:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        return await self._request("POST", "/internal/v1/profile/import", json={"payload": payload}, timeout=120.0)


def profile_client() -> ProfileHttpClient | None:
    endpoint = _registry.get("profile") if _registry else None
    return ProfileHttpClient(endpoint) if endpoint else None
