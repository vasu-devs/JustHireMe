"""Secret masking for settings round-trips.

The UI never receives a real key: reads replace every secret with ``MASK``, and
writes that echo a mask back are resolved to the stored value. The legacy masks
exist because older builds sent bullet characters (and mojibake-mangled copies
of them) — a write echoing one of those must not overwrite a real key with
literal bullets.
"""

from __future__ import annotations


MASK = "__JHM_SECRET_SET__"
LEGACY_BULLET_MASK = "•" * 20
LEGACY_MOJIBAKE_BULLET_MASK = "â€¢" * 20
LEGACY_DOUBLE_ENCODED_BULLET_MASK = "Ã¢â‚¬Â¢" * 20
LEGACY_MASKS = {
    MASK,
    LEGACY_BULLET_MASK,
    LEGACY_MOJIBAKE_BULLET_MASK,
    LEGACY_DOUBLE_ENCODED_BULLET_MASK,
}


def sensitive_keys(settings: dict) -> set:
    fixed = {"anthropic_key", "linkedin_cookie", "x_bearer_token", "custom_connector_headers"}
    dynamic = {key for key in settings if key.endswith("_api_key") or key.endswith("_key") or key.endswith("_token")}
    return fixed | dynamic


def mask_secrets(settings: dict) -> dict:
    masked = dict(settings)
    for key in sensitive_keys(masked):
        if masked.get(key):
            masked[key] = MASK
    return masked


def resolve_masked(payload: dict, stored: dict) -> dict:
    """Replace any masked value in an incoming write with the stored secret."""
    resolved = dict(payload)
    for key in sensitive_keys({**stored, **resolved}):
        if resolved.get(key) in LEGACY_MASKS:
            resolved[key] = stored.get(key, "")
    return resolved


__all__ = [
    "LEGACY_BULLET_MASK",
    "LEGACY_DOUBLE_ENCODED_BULLET_MASK",
    "LEGACY_MASKS",
    "LEGACY_MOJIBAKE_BULLET_MASK",
    "MASK",
    "mask_secrets",
    "resolve_masked",
    "sensitive_keys",
]
