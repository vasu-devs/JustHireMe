from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from discovery.sources.common import retry_after_seconds


@dataclass
class BoardScanResult:
    leads: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def run_actor(actor: str, inp: dict, token: str) -> list:
    async with httpx.AsyncClient(timeout=60) as cx:
        response = await cx.post(
            f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
            params={"token": token},
            json=inp,
        )
        if response.status_code == 429:
            retry_after = retry_after_seconds(response.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            response.raise_for_status()
        response.raise_for_status()
        return response.json()


def run_board_scan(urls: list[str], cfg: dict) -> BoardScanResult:
    from automation.source_adapters import run_apify_scout

    result = run_apify_scout(
        urls=urls,
        apify_token=cfg.get("apify_token") or None,
        apify_actor=cfg.get("apify_actor") or None,
    )
    return BoardScanResult(
        leads=result.leads,
        usage=result.usage,
        errors=result.errors,
    )
