from __future__ import annotations

from data.repository import Repository, create_repository


class AutomationRepository:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    def settings(self) -> dict:
        return self.repo.settings.get_settings()
