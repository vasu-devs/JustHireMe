"""Unit tests for graph_service/helpers.py.

These helpers became load-bearing when the /api/v1/graph endpoint stopped
carrying its own private copies of them. The embedding-space projection is what
the Knowledge page renders, so a silent failure here shows up as a blank canvas.
"""

import types

import pytest

from graph_service import helpers


def _repo(tables, rows_by_table=None):
    rows_by_table = rows_by_table or {}

    class Table:
        def __init__(self, name):
            self._name = name

        def to_arrow(self):
            raise AttributeError("no arrow")

        def to_pandas(self):
            raise AttributeError("no pandas")

    class Vec:
        def list_tables(self):
            return tables

        def open_table(self, name):
            table = Table(name)
            rows = rows_by_table.get(name, [])
            table.to_arrow = lambda: types.SimpleNamespace(to_pylist=lambda: rows)
            return table

    return types.SimpleNamespace(vector=types.SimpleNamespace(vec=Vec()))


# --------------------------------------------------------------- table-name normalising


@pytest.mark.parametrize(
    "raw, expected",
    [
        (["skills", "projects"], ["skills", "projects"]),
        ([["skills"], ["projects"]], ["skills", "projects"]),        # nested-list rows
        ([{"name": "skills"}, {"table": "projects"}], ["skills", "projects"]),
        ({"tables": ["skills"]}, ["skills"]),
        (None, []),
        ([], []),
    ],
)
def test_vector_table_names_normalises_every_lancedb_shape(raw, expected):
    assert helpers.vector_table_names(types.SimpleNamespace(list_tables=lambda: raw)) == expected


# --------------------------------------------------------------- label / type mapping


@pytest.mark.parametrize(
    "label, bad",
    [
        ("Python", False),
        ("", True),
        ("   ", True),
        ("404: Not Found", True),
        ("Failed to fetch", True),
        ("Traceback (most recent call last)", True),
    ],
)
def test_is_bad_vector_label(label, bad):
    assert helpers.is_bad_vector_label(label) is bad


@pytest.mark.parametrize(
    "table, row, expected",
    [
        ("profile", {}, "Profile"),
        ("candidates", {}, "Candidate"),
        ("skills", {}, "Skill"),
        ("projects", {}, "Project"),
        ("experiences", {}, "Experience"),
        ("credentials", {"kind": "certification"}, "Certification"),
        ("credentials", {}, "Credential"),
        ("something_else", {}, "Something_Else"),
    ],
)
def test_vector_type(table, row, expected):
    assert helpers.vector_type(table, row) == expected


# --------------------------------------------------------------- projection


def test_project_vector_is_deterministic_and_non_degenerate():
    vector = [0.1, 0.9, -0.4, 0.7]
    first = helpers.project_vector(vector)
    assert first == helpers.project_vector(vector)
    assert any(abs(axis) > 0 for axis in first)


def test_project_vector_returns_the_origin_for_an_all_zero_vector():
    assert helpers.project_vector([0.0, 0.0, 0.0]) == (0.0, 0.0, 0.0)


def test_project_vector_skips_non_numeric_entries():
    assert helpers.project_vector(["nope", None, 0.5]) == helpers.project_vector([0, 0, 0.5])


# --------------------------------------------------------------- embedding space


def test_embedding_space_projects_rows_onto_the_unit_sphere():
    rows = [{"id": "s1", "label": "Python", "vector": [0.3, 0.4, 0.5], "cat": "language"}]
    space = helpers.embedding_space(_repo(["skills"], {"skills": rows}))

    assert space["available"] is True
    assert space["error"] == ""
    point = space["points"][0]
    assert point["label"] == "Python"
    assert point["type"] == "Skill"
    assert point["subtitle"] == "language"
    assert pytest.approx(point["x"] ** 2 + point["y"] ** 2 + point["z"] ** 2, rel=1e-6) == 1.0


def test_embedding_space_drops_junk_labels_and_short_vectors():
    rows = [
        {"id": "a", "label": "404: Not Found", "vector": [0.3, 0.4]},
        {"id": "b", "label": "Real Skill", "vector": [0.1]},          # too few dims
        {"id": "c", "label": "Kept", "vector": [0.3, 0.4, 0.5]},
    ]
    space = helpers.embedding_space(_repo(["skills"], {"skills": rows}))
    assert [point["label"] for point in space["points"]] == ["Kept"]


def test_embedding_space_ignores_tables_outside_the_profile_set():
    rows = {"skills": [{"id": "a", "label": "Kept", "vector": [0.3, 0.4]}],
            "job_leads": [{"id": "b", "label": "Leaked", "vector": [0.3, 0.4]}]}
    space = helpers.embedding_space(_repo(["skills", "job_leads"], rows))
    assert [point["label"] for point in space["points"]] == ["Kept"]


def test_embedding_space_honours_the_limit():
    rows = [{"id": str(i), "label": f"S{i}", "vector": [0.3, 0.4, 0.5]} for i in range(50)]
    space = helpers.embedding_space(_repo(["skills"], {"skills": rows}), limit=5)
    assert len(space["points"]) == 5


def test_embedding_space_reports_an_unavailable_store_instead_of_raising():
    class Broken:
        def list_tables(self):
            raise RuntimeError("LanceDB not installed")

    repo = types.SimpleNamespace(vector=types.SimpleNamespace(vec=Broken()))
    space = helpers.embedding_space(repo)

    assert space["available"] is False
    assert space["points"] == []
    assert "LanceDB not installed" in space["error"]


# --------------------------------------------------------------- safe_graph_step


def test_safe_graph_step_returns_the_value_on_success():
    errors: list[str] = []
    assert helpers.safe_graph_step(lambda: {"status": "ok"}, "step", errors) == {"status": "ok"}
    assert errors == []


def test_safe_graph_step_records_the_failure_and_returns_the_default():
    errors: list[str] = []

    def boom():
        raise RuntimeError("graph locked")

    assert helpers.safe_graph_step(boom, "counts", errors, default={}) == {}
    assert errors == ["counts: graph locked"]


def test_safe_graph_step_without_a_default_reports_an_error_payload():
    errors: list[str] = []

    def boom():
        raise RuntimeError("graph locked")

    result = helpers.safe_graph_step(boom, "sync", errors)
    assert result == {"status": "error", "error": "graph locked"}
