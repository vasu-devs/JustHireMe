import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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
