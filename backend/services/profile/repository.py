from __future__ import annotations

from data.repository import Repository, create_repository


class ProfileRepository:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    def get_profile(self) -> dict:
        return self.repo.profile.get_profile()
