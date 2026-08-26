"""The Common layer's environment registry — the one place env vars are read.

Every environment variable the application understands is declared here with its
name, type and default, and is reached through a named accessor. Nothing else in
the codebase calls ``os.environ`` / ``os.getenv``; that is enforced by
``tests/unit/architecture/test_import_boundaries.py::test_environment_is_read_only_through_core_env``.

Why it matters: env reads scattered across twelve modules meant the real
configuration surface was undiscoverable — you could not answer "what can be
configured?" without grepping, defaults drifted between call sites, and
``.env.example`` had no mechanical relationship to the code.

Reads are intentionally **live** (not captured at import): tests monkeypatch
these variables, and the sidecar's app-data directory is set by the shell after
some modules are already imported.
"""

from __future__ import annotations

import os

FALSEY = frozenset({"0", "false", "no", "off", ""})
TRUTHY = frozenset({"1", "true", "yes", "on"})


# --------------------------------------------------------------------------- names
# Grouped by purpose. Keep in sync with .env.example — test_env_example_documents_
# every_supported_variable fails if a JHM_* variable here is undocumented.

# Paths / runtime layout
APP_DATA_DIR = "JHM_APP_DATA_DIR"
APP_DATA_BASE_DIR = "JHM_APP_DATA_BASE_DIR"
APP_VERSION = "JHM_APP_VERSION"
LOG_LEVEL = "JHM_LOG_LEVEL"
LOCAL_APP_DATA = "LOCALAPPDATA"
ROAMING_APP_DATA = "APPDATA"
XDG_DATA_HOME = "XDG_DATA_HOME"

# Feature switches
AUTO_APPLY = "JHM_AUTO_APPLY"
FIT_ENGINE = "JHM_FIT_ENGINE"
PORTFOLIO_LLM = "JHM_PORTFOLIO_LLM"
LOCAL_ERROR_TELEMETRY = "JHM_LOCAL_ERROR_TELEMETRY"

# Optional runtime pack
RUNTIME_PACK_URL = "JHM_RUNTIME_PACK_URL"
BUNDLED_RUNTIME_PACK_URL = "JHM_BUNDLED_RUNTIME_PACK_URL"
RUNTIME_PACK_VERSION = "JHM_RUNTIME_PACK_VERSION"
VECTOR_RUNTIME_DIR = "JHM_VECTOR_RUNTIME_DIR"
VECTOR_RUNTIME_URL = "JHM_VECTOR_RUNTIME_URL"
RELEASE_RUNTIME_PACK_URL = "JHM_RELEASE_RUNTIME_PACK_URL"
BROWSER_RUNTIME_DIR = "JHM_BROWSER_RUNTIME_DIR"
BROWSER_RUNTIME_URL = "JHM_BROWSER_RUNTIME_URL"
PLAYWRIGHT_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"
PLAYWRIGHT_CHROMIUM_EXECUTABLE = "PLAYWRIGHT_CHROMIUM_EXECUTABLE"

# Third-party credentials (settings take precedence; env is the fallback)
OPENAI_API_KEY = "OPENAI_API_KEY"
GOOGLE_API_KEY = "GOOGLE_API_KEY"
AZURE_OPENAI_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
OPENAI_COMPAT_BASE_URL = "OPENAI_COMPAT_BASE_URL"
HUNTER_API_KEY = "HUNTER_API_KEY"
PROXYCURL_API_KEY = "PROXYCURL_API_KEY"
X_BEARER_TOKEN = "X_BEARER_TOKEN"
TWITTER_BEARER_TOKEN = "TWITTER_BEARER_TOKEN"
CLAUDE_CODE_OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
CODEX_REASONING = "JHM_CODEX_REASONING"
ERRORS_JSONL = "JHM_ERRORS_JSONL"
GEMINI_API_KEY = "GEMINI_API_KEY"
COPILOT_TOKEN_NAMES = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


# ---------------------------------------------------------------------- accessors

def get(name: str, default: str = "") -> str:
    """Raw value for a variable whose name is only known at runtime.

    Used for the provider-keyed lookups (`_ENV_NAMES[provider]`) where the name
    is data, not a constant.
    """
    return os.environ.get(name, default) or default


def text(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default).strip()


def flag(name: str, default: bool = False) -> bool:
    """Truthy check with the app's shared vocabulary (1/true/yes/on)."""
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in TRUTHY


def first(*names: str, default: str = "") -> str:
    """First variable in `names` that has a value — for aliased vars."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def is_set(name: str) -> bool:
    return bool(os.environ.get(name))


def snapshot() -> dict[str, str]:
    """A copy of the whole environment, for handing to a subprocess."""
    return dict(os.environ)


def set_value(name: str, value: str) -> None:
    """Set a variable for child processes (Playwright's browser path)."""
    os.environ[name] = value


# ------------------------------------------------------------ named conveniences

def log_level() -> str:
    return text(LOG_LEVEL, "INFO")


def auto_apply_enabled() -> bool:
    return flag(AUTO_APPLY, False)


def fit_engine() -> str:
    return text(FIT_ENGINE).lower()


def portfolio_llm_disabled() -> bool:
    """JHM_PORTFOLIO_LLM opts *out*: unset means enabled."""
    return text(PORTFOLIO_LLM).lower() in FALSEY - {""}


def openai_api_key() -> str:
    return text(OPENAI_API_KEY)


def google_api_key() -> str:
    return text(GOOGLE_API_KEY)


def azure_openai_endpoint() -> str:
    return text(AZURE_OPENAI_ENDPOINT)


def hunter_api_key() -> str:
    return text(HUNTER_API_KEY)


def proxycurl_api_key() -> str:
    return text(PROXYCURL_API_KEY)


def local_error_telemetry_enabled() -> bool:
    return flag(LOCAL_ERROR_TELEMETRY, False)


def codex_reasoning(default: str = "low") -> str:
    return text(CODEX_REASONING) or default


def openai_compat_base_url() -> str:
    return text(OPENAI_COMPAT_BASE_URL)


def any_set(*names: str) -> bool:
    return any(os.environ.get(name) for name in names)


def x_bearer_token() -> str:
    """X/Twitter accepts either name; X_BEARER_TOKEN wins."""
    return first(X_BEARER_TOKEN, TWITTER_BEARER_TOKEN)


#: Every JHM_* variable, for documentation checks and diagnostics.
JHM_VARIABLES = tuple(sorted(
    value for name, value in list(globals().items())
    if name.isupper() and isinstance(value, str) and value.startswith("JHM_")
))
