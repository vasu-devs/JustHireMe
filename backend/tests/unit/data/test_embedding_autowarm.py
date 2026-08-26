"""ensure_onnx_model() makes real ONNX semantics default-on with zero setup, but must
respect the user's provider choice and fail safe offline."""

from __future__ import annotations

from unittest import mock

import data.vector.embeddings as emb


def test_ensure_onnx_downloads_when_preferred_and_missing():
    calls = {"download": 0}

    def fake_download(*, force=False):
        calls["download"] += 1
        return {"status": "ok", "path": "/tmp/model"}

    with mock.patch.object(emb, "_configured_provider", return_value="onnx"), \
         mock.patch.object(emb, "_onnx_model_ready", return_value=False), \
         mock.patch.object(emb, "download_onnx_model", new=fake_download), \
         mock.patch.object(emb, "reset_onnx_session"), \
         mock.patch.object(emb, "_load_onnx_session", return_value=True):
        assert emb.ensure_onnx_model() is True
    assert calls["download"] == 1


def test_ensure_onnx_is_noop_when_user_chose_hash():
    with mock.patch.object(emb, "_configured_provider", return_value="hash"), \
         mock.patch.object(emb, "download_onnx_model") as dl:
        assert emb.ensure_onnx_model() is False
    dl.assert_not_called()


def test_ensure_onnx_is_noop_when_keyed_openai():
    with mock.patch.object(emb, "_configured_provider", return_value="openai"), \
         mock.patch.object(emb, "_openai_api_key", return_value="sk-xxx"), \
         mock.patch.object(emb, "download_onnx_model") as dl:
        assert emb.ensure_onnx_model() is False
    dl.assert_not_called()


def test_ensure_onnx_fails_safe_when_download_errors():
    with mock.patch.object(emb, "_configured_provider", return_value="onnx"), \
         mock.patch.object(emb, "_onnx_model_ready", return_value=False), \
         mock.patch.object(emb, "download_onnx_model", side_effect=OSError("offline")):
        assert emb.ensure_onnx_model() is False  # no raise; hash fallback stays
