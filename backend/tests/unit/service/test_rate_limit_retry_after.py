# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for M3: rate limiter exposes Retry-After to clients."""

import pytest
from fastapi import HTTPException

from api.rate_limit import RateLimiter, require_rate_limit


def test_retry_after_zero_when_slot_available():
    limiter = RateLimiter(max_calls=2, window_seconds=60)
    assert limiter.retry_after() == 0
    assert limiter.allow() is True
    assert limiter.retry_after() == 0  # still one slot free


def test_retry_after_positive_when_exhausted():
    limiter = RateLimiter(max_calls=1, window_seconds=60)
    assert limiter.allow() is True
    assert limiter.allow() is False
    wait = limiter.retry_after()
    assert 1 <= wait <= 60


def test_require_rate_limit_sets_retry_after_header_and_message():
    limiter = RateLimiter(max_calls=1, window_seconds=30)
    require_rate_limit(limiter)  # first call passes
    with pytest.raises(HTTPException) as exc_info:
        require_rate_limit(limiter)
    exc = exc_info.value
    assert exc.status_code == 429
    assert "Retry-After" in exc.headers
    retry_after = int(exc.headers["Retry-After"])
    assert 1 <= retry_after <= 30
    assert "wait" in exc.detail.lower()
    assert str(retry_after) in exc.detail
