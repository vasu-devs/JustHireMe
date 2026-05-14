from __future__ import annotations

import asyncio
import base64


def _content(value: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(value.encode()).decode()}


def test_github_ingestor_imports_all_repos_and_enriches_top_without_token(monkeypatch):
    import profile.github_ingestor as gh

    repos = [
        {
            "name": f"repo-{index}",
            "full_name": f"vasu/repo-{index}",
            "html_url": f"https://github.com/vasu/repo-{index}",
            "description": f"Production project {index}",
            "language": "Python" if index == 0 else "TypeScript",
            "topics": ["fastapi", "react"] if index == 0 else ["nextjs"],
            "stargazers_count": 100 - index,
            "forks_count": index,
            "watchers_count": 0,
            "pushed_at": "2026-05-01T00:00:00Z",
            "homepage": "",
            "archived": False,
            "fork": False,
        }
        for index in range(25)
    ]

    async def fake_fetch(url: str, token: str | None):
        if url.endswith("/users/vasu"):
            return {
                "login": "vasu",
                "name": "Vasu",
                "bio": "Builder",
                "public_repos": 25,
                "followers": 7,
                "html_url": "https://github.com/vasu",
            }
        if "/users/vasu/repos" in url:
            return repos
        if "/git/trees/" in url:
            return {
                "tree": [
                    {"type": "blob", "path": "package.json"},
                    {"type": "blob", "path": "pyproject.toml"},
                    {"type": "blob", "path": "docs/package.json"},
                    {"type": "blob", "path": "docs/deep/package.json"},
                    {"type": "blob", "path": "src/main.py"},
                ]
            }
        if url.endswith("/languages"):
            return {"Python": 6000, "TypeScript": 3000}
        if url.endswith("/readme"):
            return _content("# Repo\nBuilt a dashboard API workflow with database sync.")
        if url.endswith("/contents/package.json"):
            return _content('{"dependencies":{"react":"latest","next":"latest","tailwindcss":"latest"}}')
        if url.endswith("/contents/pyproject.toml"):
            return _content('dependencies = ["fastapi", "pydantic", "httpx"]')
        return None

    async def fake_extract(repo, readme, languages, manifest_summary, inferred_skills):
        return None

    monkeypatch.setattr(gh, "_fetch", fake_fetch)
    monkeypatch.setattr(gh, "_extract_project", fake_extract)

    result = asyncio.run(gh.ingest_github("vasu", max_repos=25))

    assert result["github_user"]["login"] == "vasu"
    assert result["stats"]["repos_fetched"] == 25
    assert result["stats"]["projects_extracted"] == 25
    assert result["stats"]["repos_enriched"] == 20
    assert result["stats"]["file_indexes_read"] == 20
    assert result["stats"]["readmes_read"] == 20
    assert result["stats"]["languages_read"] == 20
    assert result["stats"]["manifests_read"] == 40
    assert result["stats"]["llm_projects"] == 6
    assert any(skill["n"] == "FastAPI" for skill in result["skills"])
    assert any(skill["n"] == "React" for skill in result["skills"])
    assert "Add a GitHub token" in result["errors"][0]


def test_github_ingestor_token_enriches_all_requested_repos(monkeypatch):
    import profile.github_ingestor as gh

    repos = [
        {
            "name": f"app-{index}",
            "full_name": f"vasu/app-{index}",
            "html_url": f"https://github.com/vasu/app-{index}",
            "description": "Full-stack app",
            "language": "TypeScript",
            "topics": ["nextjs"],
            "stargazers_count": 1,
            "forks_count": 0,
            "watchers_count": 0,
            "pushed_at": "2026-05-01T00:00:00Z",
            "homepage": "",
            "archived": False,
            "fork": False,
        }
        for index in range(3)
    ]

    async def fake_fetch(url: str, token: str | None):
        assert token == "ghp_test"
        if url.endswith("/users/vasu"):
            return {"login": "vasu", "public_repos": 3, "html_url": "https://github.com/vasu"}
        if "/users/vasu/repos" in url:
            return repos
        if url.endswith("/languages"):
            return {"TypeScript": 5000}
        if url.endswith("/readme"):
            return _content("Built production Next.js workflows with React dashboards.")
        return None

    async def fake_extract(repo, readme, languages, manifest_summary, inferred_skills):
        return None

    monkeypatch.setattr(gh, "_fetch", fake_fetch)
    monkeypatch.setattr(gh, "_extract_project", fake_extract)

    result = asyncio.run(gh.ingest_github("vasu", token="ghp_test", max_repos=3))

    assert result["stats"]["repos_fetched"] == 3
    assert result["stats"]["projects_extracted"] == 3
    assert result["stats"]["repos_enriched"] == 3
    assert result["errors"] == []


def test_github_ingestor_does_not_label_rate_limit_as_missing_user(monkeypatch):
    import profile.github_ingestor as gh

    async def fake_fetch(url: str, token: str | None):
        raise gh.GitHubFetchError("GitHub API rate limit reached. Add a GitHub token and try again.", status_code=429)

    monkeypatch.setattr(gh, "_fetch", fake_fetch)

    result = asyncio.run(gh.ingest_github("vasu-devs", max_repos=10))

    assert result["error_kind"] == "github_unavailable"
    assert result["status_code"] == 429
    assert "not found" not in result["error"].lower()
