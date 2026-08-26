# Backend test suite

Tests are grouped to mirror the layered architecture (see [docs/LAYERS.md](../../docs/LAYERS.md)),
so the tests for a layer sit next to each other and a layer can be exercised alone.

```
tests/
  conftest.py            app-data isolation, sys.path, autouse resets
  paths.py               TESTS_ROOT / BACKEND_ROOT / REPO_ROOT anchors
  unit/
    common/              core/            config, paths, telemetry, url guard
    data/                data/, models/   SQLite, Kùzu, LanceDB, embeddings
    adapter/             llm/             providers, catalog, retry, subscriptions
    business/            discovery, ranking, generation, profile, automation, learning
    service/             api/             routers, websocket auth, rate limiting
    architecture/        the layering contract itself
  regression/            behaviour that was broken once and must not break again
    regression_support.py  shared fakes (imported by `from regression_support import *`)
```

## Running

```bash
cd backend
uv run python -m pytest tests -q                    # everything
uv run python -m pytest tests/unit -q               # unit only
uv run python -m pytest tests/unit/business -q      # one layer
uv run python -m pytest tests/regression -q         # regression only
uv run python -m pytest tests/unit/architecture -q  # the layer contract
uv run python -m pytest tests -q --cov=. --cov-report=term-missing
```

## Rules

- **Never anchor paths with `Path(__file__).parents[N]`.** Import `TESTS_ROOT`,
  `BACKEND_ROOT` or `REPO_ROOT` from `paths` instead. Files move between groups;
  parent-counting silently breaks when they do, and modules that point
  `JHM_APP_DATA_DIR` at their own directory would each get a *different* app-data
  dir, splitting shared test state.
- **Test file names stay unique across the whole tree.** The groups have no
  `__init__.py`, so pytest identifies modules by basename alone.
- **A new endpoint's test goes in `unit/service/`; its logic test goes in
  `unit/business/`.** If a test needs the real SQLite/Kùzu (the in-process suite
  installs a global fake), run it in a subprocess — see
  `regression/test_project_skill_linking.py` for the pattern.
- **Fixing a reported bug?** Add the test to `regression/`, named for the fix.
