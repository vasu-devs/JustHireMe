from __future__ import annotations

import os
import platform
from pathlib import Path

from data.vector.runtime import browser_runtime_dir, browser_runtime_ready, install_vector_runtime
from core import env


_RELEASE_DOWNLOAD_BASE = "https://github.com/vasu-devs/JustHireMe/releases/latest/download"


def sys_platform() -> str:
    return platform.system().lower()


def browser_runtime_asset_name() -> str:
    system = sys_platform()
    if system == "windows":
        return "JustHireMe-browser-runtime-windows.zip"
    if system == "darwin":
        return "JustHireMe-browser-runtime-macos.zip"
    return "JustHireMe-browser-runtime-linux.zip"


def browser_runtime_url() -> str:
    return env.get(
        env.BROWSER_RUNTIME_URL,
        f"{_RELEASE_DOWNLOAD_BASE}/{browser_runtime_asset_name()}",
    )


def _runtime_chromium_executable() -> str | None:
    root = browser_runtime_dir()
    if not root.exists():
        return None

    system = sys_platform()
    if system == "windows":
        patterns = ["chromium-*/chrome-win*/chrome.exe", "chromium-*/chrome.exe"]
    elif system == "darwin":
        patterns = ["chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"]
    else:
        patterns = ["chromium-*/chrome-linux*/chrome", "chromium-*/chrome"]

    for pattern in patterns:
        for candidate in sorted(root.glob(pattern)):
            if candidate.exists():
                return str(candidate)
    return None


def _system_browser_candidates() -> list[str]:
    """Return platform-specific paths to Chrome, Chromium, Edge, and Brave."""
    system = sys_platform()
    if system == "windows":
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
    if system == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    # Linux
    return [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/usr/bin/brave-browser",
        "/usr/bin/brave-browser-stable",
        "/snap/bin/chromium",
        "/usr/local/bin/chromium",
    ]


def chromium_executable() -> str | None:
    candidates = [
        env.text(env.PLAYWRIGHT_CHROMIUM_EXECUTABLE),
        _runtime_chromium_executable() or "",
        *_system_browser_candidates(),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def ensure_browser_runtime() -> Path:
    runtime_dir = browser_runtime_dir()
    if browser_runtime_ready(runtime_dir):
        return runtime_dir

    install_vector_runtime()

    if not browser_runtime_ready(runtime_dir):
        raise RuntimeError("Required runtime pack installation finished, but Playwright Chromium was not found.")
    return runtime_dir


async def launch_chromium(playwright, *, headless: bool = True, **kwargs):
    runtime_launch_error: Exception | None = None
    if "executable_path" not in kwargs:
        executable = _runtime_chromium_executable()
        if executable:
            try:
                return await playwright.chromium.launch(
                    headless=headless,
                    executable_path=executable,
                    **kwargs,
                )
            except Exception as exc:
                runtime_launch_error = exc

    try:
        return await playwright.chromium.launch(headless=headless, **kwargs)
    except Exception as exc:
        message = f"{runtime_launch_error or ''} {exc}".lower()
        if "executable" in message or "chromium" in message or "browser" in message:
            executable = chromium_executable()
            if executable:
                return await playwright.chromium.launch(
                    headless=headless,
                    executable_path=executable,
                    **kwargs,
                )
            runtime_dir = ensure_browser_runtime()
            env.set_value(env.PLAYWRIGHT_BROWSERS_PATH, str(runtime_dir))
            return await playwright.chromium.launch(headless=headless, **kwargs)

        executable = chromium_executable()
        if not executable:
            raise
        return await playwright.chromium.launch(
            headless=headless,
            executable_path=executable,
            **kwargs,
        )
