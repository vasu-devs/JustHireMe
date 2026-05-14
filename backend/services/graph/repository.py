from __future__ import annotations

from data.repository import Repository, create_repository


class GraphRepository:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    def counts(self) -> dict:
        return self.repo.graph.graph_counts()
