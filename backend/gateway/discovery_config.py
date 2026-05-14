from __future__ import annotations

from importlib import import_module


def _targets():
    return import_module("discovery.targets")


def free_sources_enabled(cfg: dict) -> bool:
    return _targets().free_sources_enabled(cfg)


def has_x_token(cfg: dict) -> bool:
    return _targets().has_x_token(cfg)


def int_cfg(cfg: dict, key: str, default: int, min_value: int, max_value: int) -> int:
    return _targets().int_cfg(cfg, key, default, min_value, max_value)


def job_targets(raw: str, market_focus: str = "global") -> list[str]:
    return _targets().job_targets(raw, market_focus)


def profile_for_discovery(profile: dict | None, cfg: dict) -> dict:
    return _targets().profile_for_discovery(profile, cfg)


def truthy(value) -> bool:
    return _targets().truthy(value)
