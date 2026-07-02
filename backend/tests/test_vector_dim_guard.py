"""A dimension mismatch on a single-item vector write must NOT wipe the table.

Regression guard for the data-loss path: after an embedding-provider switch, an
add_skill/add_project write embeds at the new dim; put_vec_rows must skip it
(preserving the other embeddings) rather than drop+recreate the table from just
that one row. Only a full rebuild (allow_recreate=True) may recreate.
"""

from __future__ import annotations

import data.graph.profile_vectors as pv


class FakeTable:
    def merge_insert(self, *_a, **_k):
        raise NotImplementedError

    def add(self, *_a, **_k):
        return None


class FakeStore:
    available = True

    def __init__(self) -> None:
        self.dropped: list[str] = []
        self.created: list[tuple[str, int]] = []

    def drop_table(self, name):
        self.dropped.append(name)

    def create_table(self, name, data=None):
        self.created.append((name, len(data or [])))

    def open_table(self, _name):
        return FakeTable()


def _wire(monkeypatch, store, *, have_dim, want_dim):
    monkeypatch.setattr(pv, "_vec", lambda: store)
    monkeypatch.setattr(pv, "vec_table_names", lambda: ["skills"])
    monkeypatch.setattr(pv, "_existing_vector_dim", lambda _s, _t: have_dim)
    monkeypatch.setattr(pv, "_incoming_vector_dim", lambda _rows: want_dim)


def test_single_item_write_does_not_drop_on_dim_mismatch(monkeypatch):
    store = FakeStore()
    _wire(monkeypatch, store, have_dim=384, want_dim=1536)
    # add_skill-style single-row write at the NEW dim against an OLD-dim table.
    pv.put_vec_rows("skills", [{"id": "s1", "vector": [0.0] * 1536}])
    assert store.dropped == [], "a partial write must never drop a dim-mismatched table"
    assert store.created == [], "and must not recreate it from a single row"


def test_full_rebuild_recreates_on_dim_mismatch(monkeypatch):
    store = FakeStore()
    _wire(monkeypatch, store, have_dim=384, want_dim=1536)
    rows = [{"id": f"s{i}", "vector": [0.0] * 1536} for i in range(30)]
    pv.put_vec_rows("skills", rows, allow_recreate=True)
    assert store.dropped == ["skills"]
    assert store.created == [("skills", 30)], "full rebuild recreates from the complete row set"


def test_add_profile_vec_recreate_rebuilds_profile_table(monkeypatch):
    # The full-rebuild aggregate write (allow_recreate=True) must recreate the
    # 'profile' table at the new dim, not skip it (round-2 regression).
    store = FakeStore()
    monkeypatch.setattr(pv, "_vec", lambda: store)
    monkeypatch.setattr(pv, "vec_table_names", lambda: ["profile"])
    monkeypatch.setattr(pv, "_existing_vector_dim", lambda _s, _t: 384)
    monkeypatch.setattr(pv, "_incoming_vector_dim", lambda _rows: 1536)
    import data.vector.embeddings as emb
    monkeypatch.setattr(emb, "embed_texts", lambda texts: [[0.0] * 1536 for _ in texts])
    pv.add_profile_vec("profile:default", "Complete profile", "text", allow_recreate=True)
    assert store.dropped == ["profile"], "full rebuild must recreate the profile table at the new dim"


def test_add_profile_vec_default_skips_on_mismatch(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(pv, "_vec", lambda: store)
    monkeypatch.setattr(pv, "vec_table_names", lambda: ["profile"])
    monkeypatch.setattr(pv, "_existing_vector_dim", lambda _s, _t: 384)
    monkeypatch.setattr(pv, "_incoming_vector_dim", lambda _rows: 1536)
    import data.vector.embeddings as emb
    monkeypatch.setattr(emb, "embed_texts", lambda texts: [[0.0] * 1536 for _ in texts])
    pv.add_profile_vec("profile:default", "Complete profile", "text")  # single-item default
    assert store.dropped == [], "a single-item profile write must not wipe the table"


def test_add_skill_vec_uses_partial_write(monkeypatch):
    # The single-item convenience wrapper must inherit the safe (non-recreating) path.
    store = FakeStore()
    _wire(monkeypatch, store, have_dim=384, want_dim=1536)
    monkeypatch.setattr(pv, "embed_texts", lambda texts: [[0.0] * 1536 for _ in texts], raising=False)
    # Patch embed_texts where embed_rows imports it.
    import data.vector.embeddings as emb
    monkeypatch.setattr(emb, "embed_texts", lambda texts: [[0.0] * 1536 for _ in texts])
    pv.add_skill_vec("s1", "Python", "language")
    assert store.dropped == [], "add_skill_vec must not wipe a dim-mismatched table"
