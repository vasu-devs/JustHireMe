import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# ── Must run before any backend module is imported ───────────────────────────
os.environ["LOCALAPPDATA"] = str(Path(__file__).resolve().parent)
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


def _install_storage_fakes():
    sys.modules.setdefault(
        "kuzu",
        types.SimpleNamespace(
            Database=lambda _path: object(),
            Connection=lambda _db: _FakeConnection(),
        ),
    )
    sys.modules["sqlite3"] = types.SimpleNamespace(
        connect=lambda _path: _FakeSqlConnection()
    )
    sys.modules.setdefault(
        "lancedb",
        types.SimpleNamespace(
            LanceDBConnection=_FakeVectorStore,
            connect=lambda _path: _FakeVectorStore(),
        ),
    )


_install_storage_fakes()

from graph import build_eval_graph, PipelineState  # noqa: E402


# ── Shared fake eval result used across tests ─────────────────────────────────

_EVAL_RESULT = {
    "score": 75,
    "reason": "Good stack match.",
    "match_points": ["Stack overlap: Python 80/100"],
    "gaps": [],
}

_GEN_RESULT = {
    "resume": "",
    "cover_letter": "",
    "selected_projects": [],
    "keyword_coverage": {},
}


class TestGraphStructure(unittest.TestCase):
    def test_graph_compiles(self):
        graph = build_eval_graph()
        self.assertIsNotNone(graph)

    def test_graph_has_evaluate_node(self):
        graph = build_eval_graph()
        # LangGraph compiled graphs expose nodes via .nodes (Pregel attribute)
        nodes = getattr(graph, "nodes", {})
        self.assertIn("evaluate", nodes)

    def test_vector_label_guard_rejects_error_rows(self):
        from graph_service.helpers import is_bad_vector_label

        self.assertTrue(is_bad_vector_label("404: NOT_FOUND Code: NOT_FOUND"))
        self.assertTrue(is_bad_vector_label("Failed to fetch project metadata"))
        self.assertFalse(is_bad_vector_label("DryRunVisualised"))


class TestGraphInvoke(unittest.TestCase):
    def setUp(self):
        self.patches = []

        p_eval = mock.patch("ranking.evaluator.score", return_value=_EVAL_RESULT)
        p_gen = mock.patch("generation.generator.run_package", return_value=_GEN_RESULT)
        p_update = mock.patch("data.sqlite.leads.update_lead_score")
        p_save = mock.patch("data.sqlite.leads.save_asset_package")

        for p in (p_eval, p_gen, p_update, p_save):
            self.patches.append(p)
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _make_state(self, **overrides) -> PipelineState:
        base: PipelineState = {
            "job_id": "test-job-001",
            "lead": {
                "job_id": "test-job-001",
                "title": "Software Engineer",
                "company": "Acme",
                "url": "https://example.com/job/001",
                "description": "We need a great engineer.",
            },
            "profile": {
                "candidate": {"n": "Test User", "s": "engineer"},
                "skills": [],
                "projects": [],
                "experience": [],
            },
            "cfg": {"auto_generate_threshold": 60},
            "score": 0,
            "reason": "",
            "match_points": [],
            "gaps": [],
            "asset_path": "",
            "cover_letter_path": "",
            "error": None,
        }
        base.update(overrides)
        return base

    def test_invoke_returns_state_dict(self):
        graph = build_eval_graph()
        result = graph.invoke(self._make_state())
        self.assertIsInstance(result, dict)

    def test_invoke_result_has_required_keys(self):
        graph = build_eval_graph()
        result = graph.invoke(self._make_state())
        for key in ("score", "reason", "match_points", "gaps", "error"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_invoke_score_in_valid_range(self):
        graph = build_eval_graph()
        result = graph.invoke(self._make_state())
        score = result.get("score", -1)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_error_field_is_none_or_string(self):
        graph = build_eval_graph()
        result = graph.invoke(self._make_state())
        error = result.get("error")
        self.assertTrue(error is None or isinstance(error, str))

    def test_generate_skipped_when_score_below_threshold(self):
        # Patch evaluator to return score=30 (below the default threshold of 60).
        # generate_node returns early without importing run_package, so the
        # gen mock must never be called.
        low_eval = {
            "score": 30,
            "reason": "Weak match.",
            "match_points": [],
            "gaps": ["domain mismatch"],
        }

        # Re-patch evaluator inside this test with a lower score.
        with mock.patch("ranking.evaluator.score", return_value=low_eval) as _eval_mock, \
             mock.patch("generation.generator.run_package") as gen_mock:
            graph = build_eval_graph()
            result = graph.invoke(self._make_state())
            gen_mock.assert_not_called()

        self.assertLessEqual(result.get("score", 100), 59)


if __name__ == "__main__":
    unittest.main()
