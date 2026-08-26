"""OPT-IN real-browser test for portfolio click-to-reveal.

The pure reveal-merge / reference logic is covered in test_portfolio_modal_refs.py.
This one proves the part those can't: that the in-page JS actually *clicks* a
project card, captures the modal that opens (including its off-site YouTube /
case-study links), and closes it — running inside a real headless Chromium.

Gated behind JHM_LIVE_BROWSER so it is skipped by default and wherever Chromium
isn't installed. Run it with:

    cd backend && JHM_LIVE_BROWSER=1 uv run python -m pytest tests/test_portfolio_modal_live.py -v
"""

from __future__ import annotations

import os

import pytest

_OPT_IN = os.environ.get("JHM_LIVE_BROWSER", "").strip().lower() in {"1", "true", "yes", "on"}

pytestmark = pytest.mark.skipif(
    not _OPT_IN,
    reason="opt-in real-browser test: set JHM_LIVE_BROWSER=1 (needs Playwright Chromium)",
)

# A minimal SPA-style page: a clickable project card with no href that opens a
# modal (hidden until clicked) containing a demo video + case-study link — the
# exact shape that a single static scrape misses.
_PAGE_HTML = """
<!doctype html><html><head><title>Asha Verma</title></head>
<body>
  <h1>Asha Verma — Featured Projects</h1>
  <div class="card" role="button" style="cursor:pointer" onclick="document.getElementById('m').style.display='block'">
    Vaani — open project
  </div>
  <div id="m" role="dialog" class="modal"
       style="display:none;width:600px;height:400px;opacity:1">
    <h2>Vaani</h2>
    <p>Real-time multilingual voice assistant. Built with Python and FastAPI.</p>
    <a href="https://youtu.be/demo123">Watch the demo</a>
    <a href="https://medium.com/@asha/vaani-case-study">Read the case study</a>
    <button aria-label="Close" onclick="document.getElementById('m').style.display='none'">x</button>
  </div>
</body></html>
"""


@pytest.mark.asyncio
async def test_modal_click_captures_offsite_links_in_real_browser():
    from playwright.async_api import async_playwright

    from automation.browser_runtime import launch_chromium
    from profile.portfolio_crawl import _expand_page_modals

    async with async_playwright() as pw:
        browser = await launch_chromium(pw, headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(_PAGE_HTML, wait_until="domcontentloaded")
            reveals = await _expand_page_modals(page)
        finally:
            await browser.close()

    assert reveals, "clicking the project card revealed nothing"
    all_text = " ".join(r["text"] for r in reveals)
    all_links = {link["href"] for r in reveals for link in r["links"]}
    assert "voice assistant" in all_text.lower()
    assert "https://youtu.be/demo123" in all_links, f"demo video link not captured; got {all_links}"
    assert "https://medium.com/@asha/vaani-case-study" in all_links, f"case-study link not captured; got {all_links}"
