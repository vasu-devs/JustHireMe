from __future__ import annotations

import os
from urllib.parse import urlparse

from data.repository import Repository
from gateway.discovery_config import free_sources_enabled, has_x_token, job_targets, truthy


def startup_warnings(repo: Repository) -> list[str]:
    cfg = repo.settings.get_settings()
    warnings: list[str] = []

    if truthy(cfg.get("x_enabled", "false")) and not has_x_token(cfg):
        warnings.append("X scanning is enabled but x_bearer_token is missing.")

    if free_sources_enabled(cfg) and not (cfg.get("free_source_targets") or cfg.get("job_boards")):
        warnings.append("Free-source scanning is enabled but no free source targets or job boards are configured.")

    if truthy(cfg.get("custom_connectors_enabled", "false")) and not str(cfg.get("custom_connectors") or "").strip():
        warnings.append("Custom connectors are enabled but custom_connectors is empty.")

    provider = str(cfg.get("llm_provider") or "ollama").strip().lower()
    if provider and provider != "ollama":
        from llm import _ENV_NAMES, _KEY_NAMES

        key_name = _KEY_NAMES.get(provider, "")
        env_name = _ENV_NAMES.get(provider, "")
        if not (cfg.get(key_name) or os.environ.get(env_name or "")):
            warnings.append(f"LLM provider '{provider}' is selected but no API key is configured.")

    for target in job_targets(cfg.get("job_boards", ""), cfg.get("job_market_focus", "global")):
        lower = target.lower()
        if lower.startswith(("site:", "ats:", "github:", "hn:", "reddit:", "http://", "https://")):
            if lower.startswith(("http://", "https://")) and not urlparse(target).netloc:
                warnings.append(f"Job target looks like an invalid URL: {target}")
            continue
        if "." not in target and " " not in target:
            warnings.append(f"Job target may be invalid or too broad: {target}")

    return warnings


def log_startup_warnings(repo: Repository, logger) -> list[str]:
    warnings = startup_warnings(repo)
    for warning in warnings:
        logger.warning("startup config: %s", warning)
    return warnings
