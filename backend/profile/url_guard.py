"""Backwards-compatible re-export of the SSRF URL guard.

The guard moved to ``core.url_guard`` so non-profile packages (discovery, llm)
can reuse it without crossing the profile package boundary. Existing imports
``from profile.url_guard import ...`` keep working through this shim.
"""

from __future__ import annotations

from core.url_guard import (
    BlockedUrlError,
    assert_public_url,
    is_public_host,
)

__all__ = ["BlockedUrlError", "assert_public_url", "is_public_host"]
