from __future__ import annotations
import logging
import json
import time
from pathlib import Path
from core.logging import get_logger

_log = get_logger(__name__)

_BUNDLED = Path(__file__).parent.parent / "data" / "selectors.json"
_CACHE_KEY = "selectors_json"
_CACHE_TS_KEY = "selectors_fetched_at"
_TTL = 86400  # 24 hours


def _load_bundled() -> dict:
    with open(_BUNDLED, encoding="utf-8") as f:
        return json.load(f)


def get_selectors() -> dict:
    """Return selectors config. Uses cache if fresh, else fetches remote,
    else falls back to bundled default. Never raises."""
    from data.repository import create_repository
    import httpx

    repo = create_repository()
    get_setting = repo.settings.get_setting
    save_settings = repo.settings.save_settings

    remote_url = get_setting("selectors_url", "")
    cached_json = get_setting(_CACHE_KEY, "")
    cached_at = float(get_setting(_CACHE_TS_KEY, "0") or "0")
    now = time.time()

    if cached_json and (now - cached_at) < _TTL:
        try:
            return json.loads(cached_json)
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/selectors.py:get_selectors: %s', log_exc)
            pass

    if remote_url:
        try:
            resp = httpx.get(remote_url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            save_settings({_CACHE_KEY: json.dumps(data), _CACHE_TS_KEY: str(now)})
            _log.info("selectors refreshed from %s (v%s)", remote_url, data.get("version"))
            return data
        except Exception as exc:
            _log.warning("selectors remote fetch failed: %s — using cache/bundled", exc)

    if cached_json:
        try:
            return json.loads(cached_json)
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/selectors.py:get_selectors: %s', log_exc)
            pass

    return _load_bundled()


def detect_platform(url: str, selectors: dict) -> str | None:
    """Return platform key if url matches a known platform, else None."""
    url_lower = url.lower()
    for platform, cfg in selectors.get("platforms", {}).items():
        for pattern in cfg.get("detect", []):
            if pattern in url_lower:
                return platform
    return None


def get_platform_fields(url: str, selectors: dict) -> list[dict]:
    """Return ordered list of {selector, type} for the given URL.
    Platform-specific fields come first, then generic fields are appended
    for types not already covered."""
    platform = detect_platform(url, selectors)
    covered_types: set[str] = set()
    fields: list[dict] = []

    if platform:
        for f in selectors["platforms"][platform]["fields"]:
            fields.append(f)
            covered_types.add(f["type"])

    for f in selectors.get("generic", []):
        if f["type"] not in covered_types:
            fields.append(f)

    return fields
