import os
import sys
import tempfile
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# HARD app-data isolation for the whole test process, set BEFORE any backend
# module can resolve app_data_dir(). Without this, module-level telemetry
# (core.telemetry.record_error, scan metrics) resolved DEFAULT_DB_PATH to the
# REAL installed app's crm.db — pytest sessions wrote phantom error rows into
# a live user database and overwrote its last-scan metrics with test residue.
# setdefault so an explicit externally-provided dir (or a subprocess real-DB
# test that passes its own db_path) still behaves as intended.
os.environ.setdefault("JHM_APP_DATA_DIR", tempfile.mkdtemp(prefix="jhm-test-appdata-"))


collect_ignore_glob = ["tmp*"]


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear per-process rate-limit budgets before each test.

    The FastAPI app and its limiters are module-cached, so without this a test
    that exhausts a limiter would make later tests fail with 429.
    """
    try:
        from api.rate_limit import reset_all_rate_limiters

        reset_all_rate_limiters()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_embedding_runtime_state():
    """Clear the module-global embedding runtime-degradation flag between tests.

    ``data.vector.embeddings._openai_runtime_error`` is a sticky process global
    (it self-heals in production on the next success). A test that exercises the
    openai fallback would otherwise leak the degraded state into a later test that
    asserts the healthy 'openai' status. Reset ONLY if the module is already
    imported so tests that never touch embeddings pay no import cost.
    """
    yield
    emb = sys.modules.get("data.vector.embeddings")
    if emb is not None:
        emb._openai_runtime_error = ""
        emb._onnx_runtime_error = ""


def pytest_configure(config):
    """Redirect pytest's temp root if the default one is inaccessible.

    On some Windows machines the default basetemp parent
    (``%TEMP%/pytest-of-<user>``) can end up owned by another context with a
    deny ACL, which makes every ``tmp_path``-using test error with
    ``PermissionError: [WinError 5]``. When that happens, fall back to a clean
    project-local basetemp so the suite runs locally. Healthy environments
    (e.g. CI) keep pytest's default — this only triggers on the broken case.
    """
    import getpass
    import os
    import tempfile

    if getattr(config.option, "basetemp", None):
        return
    default_root = os.path.join(tempfile.gettempdir(), f"pytest-of-{getpass.getuser()}")
    try:
        os.listdir(default_root)
    except FileNotFoundError:
        return  # default root not created yet — let pytest use it
    except OSError:
        config.option.basetemp = str(BACKEND_ROOT / ".pytest-basetemp")
