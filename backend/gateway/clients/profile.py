from __future__ import annotations

import base64

from gateway.clients.base import BaseServiceClient


class ProfileHttpClient(BaseServiceClient):
    service_name = "profile"
    timeout = 120.0

    async def get_profile(self) -> dict:
        return await self._request("GET", "/internal/v1/profile", timeout=60.0)

    async def update_candidate(self, n: str, s: str) -> dict:
        return await self._request("PUT", "/internal/v1/profile/candidate", json={"n": n, "s": s})

    async def update_identity(self, identity: dict) -> dict:
        return await self._request("PUT", "/internal/v1/profile/identity", json=identity)

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

    async def add_education(self, title: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/education", json={"title": title})

    async def add_certification(self, title: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/certification", json={"title": title})

    async def add_achievement(self, title: str) -> dict:
        return await self._request("POST", "/internal/v1/profile/achievement", json={"title": title})

    async def ingest_resume(self, raw: str = "", pdf_path: str | None = None):
        return await self._request("POST", "/internal/v1/profile/ingest/resume", json={"raw": raw, "pdf_path": pdf_path}, timeout=180.0)

    async def ingest_github(self, username: str, *, token: str | None = None, max_repos: int = 100) -> dict:
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
