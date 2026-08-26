"""Stable filesystem anchors for the test suite.

Tests are grouped into ``unit/<layer>/`` and ``regression/`` subdirectories, so a
test module's own depth below ``tests/`` varies. Deriving roots from
``Path(__file__).parents[N]`` therefore breaks the moment a file is regrouped —
and worse, the modules that point ``JHM_APP_DATA_DIR`` at their own directory
would each get a *different* app-data dir, silently splitting shared test state.

Import these constants instead of counting parents.
"""

from __future__ import annotations

from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = TESTS_ROOT.parent
REPO_ROOT = BACKEND_ROOT.parent
