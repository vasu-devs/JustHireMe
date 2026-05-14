from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ProfileIngestResumeRequest(BaseModel):
    raw: str = ""
    pdf_path: str | None = None


class ProfileIngestGithubRequest(BaseModel):
    username: str
    token: str | None = None
    max_repos: int = 100


class ProfileIngestLinkedInRequest(BaseModel):
    zip_b64: str


class ProfileIngestPortfolioRequest(BaseModel):
    url: str
    auto_import: bool = False


class ProfileImportRequest(BaseModel):
    payload: dict[str, Any]
