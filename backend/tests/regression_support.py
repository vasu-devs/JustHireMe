import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


os.environ["LOCALAPPDATA"] = str(Path(__file__).resolve().parent)
os.environ["JHM_APP_DATA_DIR"] = str(Path(__file__).resolve().parent)
os.makedirs = lambda *_args, **_kwargs: None


class _FakeResult:
    def has_next(self):
        return False

    def get_next(self):
        return [0]


class _FakeConnection:
    def execute(self, *_args, **_kwargs):
        return _FakeResult()


class _FakeSqlConnection:
    def executescript(self, *_args, **_kwargs):
        return self

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        return None

    def close(self):
        return None


class _FakeVectorStore:
    def list_tables(self):
        return []

    def create_table(self, *_args, **_kwargs):
        return None

    def open_table(self, *_args, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None


class _FakeSemanticSearch:
    def __init__(self, rows):
        self.rows = list(rows)
        self._limit = len(self.rows)

    def metric(self, *_args, **_kwargs):
        return self

    def where(self, clause, *_args, **_kwargs):
        self.rows = [row for row in self.rows if f"'{row['id']}'" in clause]
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def to_list(self):
        return self.rows[: self._limit]


class _FakeSemanticTable:
    def __init__(self, rows):
        self.rows = rows

    def search(self, *_args, **_kwargs):
        return _FakeSemanticSearch(self.rows)


class _FakeSemanticStore:
    def __init__(self, tables):
        self.tables = tables

    def list_tables(self):
        return list(self.tables)

    def open_table(self, name):
        return _FakeSemanticTable(self.tables[name])


def _install_storage_fakes():
    sys.modules.setdefault("kuzu", types.SimpleNamespace(Database=lambda _path: object(), Connection=lambda _db: _FakeConnection()))
    sys.modules["sqlite3"] = types.SimpleNamespace(connect=lambda _path: _FakeSqlConnection())
    sys.modules.setdefault(
        "lancedb",
        types.SimpleNamespace(LanceDBConnection=_FakeVectorStore, connect=lambda _path: _FakeVectorStore()),
    )


_install_storage_fakes()


def _sample_scoring_profile():
    return {
        "n": "Candidate",
        "s": "Full Stack AI Engineer based in India",
        "skills": [
            {"n": "Python"},
            {"n": "FastAPI"},
            {"n": "React"},
            {"n": "Next.js"},
            {"n": "TypeScript"},
            {"n": "PostgreSQL"},
            {"n": "LangGraph"},
            {"n": "Qdrant"},
        ],
        "projects": [
            {
                "title": "Waldo",
                "stack": ["Python", "FastAPI", "React", "Qdrant", "LangGraph"],
                "impact": "Production-grade agentic RAG pipeline.",
            },
            {
                "title": "Vaani",
                "stack": ["Python", "FastAPI", "LiveKit Agents", "Deepgram"],
                "impact": "Voice AI debt recovery command center.",
            },
            {
                "title": "BranchGPT",
                "stack": ["Next.js", "TypeScript", "Drizzle ORM", "Neon Postgres"],
                "impact": "Conversation DAG product.",
            },
        ],
        "exp": [
            {
                "role": "Full-Stack Engineer",
                "co": "Freelance",
                "period": "Mar 2026-Apr 2026",
                "d": "Built financial reporting platform with Next.js, TypeScript, PostgreSQL, Prisma.",
            }
        ],
    }


__all__ = [
    "Path",
    "_FakeSemanticStore",
    "_install_storage_fakes",
    "_sample_scoring_profile",
    "mock",
    "tempfile",
    "unittest",
]
