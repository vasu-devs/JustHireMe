from __future__ import annotations

from data.repository import Repository, create_repository


class RankingRepository:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    def feedback_examples(self) -> list[dict]:
        return self.repo.feedback.get_feedback_training_examples()
