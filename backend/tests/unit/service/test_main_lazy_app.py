# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for C1: main.py must not eagerly build a second gateway app.

The module-level ``app = build_gateway_app(...)`` created a scheduler + app that
uvicorn never used, leaking resources and double-initializing the scheduler.
``app`` is now built lazily via PEP 562 ``__getattr__`` and cached as a singleton.
"""

import ast
from pathlib import Path

import main
from paths import BACKEND_ROOT

BACKEND = BACKEND_ROOT


def test_main_has_no_module_level_app_assignment():
    """No top-level ``app = ...`` assignment should remain in main.py."""
    tree = ast.parse((BACKEND / "main.py").read_text(encoding="utf-8"))
    top_level_targets = [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert "app" not in top_level_targets


def test_app_is_lazy_singleton():
    """Accessing ``main.app`` repeatedly returns the same cached instance."""
    first = main.app
    second = main.app
    assert first is second
    assert type(first).__name__ == "FastAPI"


def test_unknown_attribute_still_raises_attribute_error():
    """__getattr__ must not swallow genuinely missing attributes."""
    try:
        main.does_not_exist  # noqa: B018
    except AttributeError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected AttributeError for unknown attribute")
