"""Subscription-CLI LLM provider: power JustHireMe from the user's EXISTING
Claude / ChatGPT subscriptions instead of a pay-per-token API key.

It shells out to the locally-installed CLI the user has already logged into:
  • claude_cli → `claude -p --system-prompt <s> --output-format json [--model M]`  (user text on stdin)
  • codex_cli  → `codex exec - --skip-git-repo-check --sandbox read-only --ephemeral
                  --output-last-message <file>`  (prompt on stdin, clean final message read from file)

Auth comes from the CLI's own subscription OAuth (~/.claude, ~/.codex/auth.json).
CRITICAL: a stray ANTHROPIC_API_KEY / OPENAI_API_KEY in the child environment
silently switches the CLI to pay-per-token API billing — so we SCRUB them.

This is the user's own local automation against their own subscription. It is
opt-in and disclosed in settings; it is not a hosted login offering.

Zero heavy deps (stdlib + pydantic only inside complete_structured) so it stays
importable and testable without the rest of the llm package.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

# Codex's own default model (chosen by the user's `codex` config / ChatGPT plan)
# is the only reliable choice for subscription auth. JustHireMe's hardcoded
# "gpt-5-codex" default is REJECTED for ChatGPT accounts ("model is not supported
# when using Codex with a ChatGPT account"), so we must not forward it.
_CODEX_REJECTED_MODELS = {"", "gpt-5-codex"}

# Env vars that force pay-per-token billing if present — never leak to the child.
_SCRUB = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY")
_DEFAULT_TIMEOUT = 120

# substrings that classify a failure (checked case-insensitively, login first)
_LOGIN_HINTS = ("not logged in", "please run /login", "/login", "invalid api key",
                "unauthor", "authenticate", "sign in", "log in", "run `claude login`",
                "run codex login", "no credentials")
_CREDIT_HINTS = ("usage limit", "credit", "quota", "exceeded", "insufficient",
                 "out of", "limit reached", "upgrade your plan")


class CliError(Exception):
    """Base error for subscription-CLI failures."""


class CliNotInstalled(CliError):
    """The CLI executable isn't on PATH."""


class CliNotLoggedIn(CliError):
    """The CLI is installed but the user isn't authenticated (needs login)."""


class CliCreditExhausted(CliError):
    """The subscription's usage/credit for headless use is exhausted."""


class CliTimeout(CliError):
    """The CLI call exceeded its timeout — often a cold start, so worth one retry."""


def _exe(provider: str) -> str:
    return "claude" if provider == "claude_cli" else "codex"


def _child_env() -> dict:
    env = dict(os.environ)
    for k in _SCRUB:
        env.pop(k, None)
    return env


def _classify(text: str) -> CliError:
    t = (text or "").lower()
    if any(h in t for h in _LOGIN_HINTS):
        return CliNotLoggedIn(text.strip()[:300] or "not logged in")
    if any(h in t for h in _CREDIT_HINTS):
        return CliCreditExhausted(text.strip()[:300] or "credit exhausted")
    return CliError(text.strip()[:300] or "CLI call failed")


def _strip_fences(s: str) -> str:
    s = (s or "").strip()
    if "```" in s:
        m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
        if m:
            s = m.group(1).strip()
    # if prose surrounds the JSON, keep just the outermost object/array
    first = min([i for i in (s.find("{"), s.find("[")) if i != -1], default=-1)
    if first > 0:
        last = max(s.rfind("}"), s.rfind("]"))
        if last > first:
            s = s[first:last + 1]
    return s.strip()


def _codex_exec(exe_path: str, prompt: str, *, model, timeout: int) -> str:
    """Run `codex exec` non-interactively and return its final message.

    The prompt (incl. any embedded JSON schema) goes on STDIN — never argv — so
    it can't be mangled by the Windows `codex.cmd` shim / cmd.exe or hit the
    ~32K command-line limit. We read the clean final message from
    --output-last-message rather than scraping the agent's streamed stdout.
    --skip-git-repo-check lets it run from the sidecar's app-data cwd (not a git
    repo); --sandbox read-only keeps any model-issued command harmless.
    """
    out_fd, out_path = tempfile.mkstemp(suffix="-codex.txt")
    os.close(out_fd)
    argv = [
        exe_path, "exec", "-",
        "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
        "--output-last-message", out_path,
    ]
    # Only forward an explicit, account-compatible model override; never the
    # rejected default (see _CODEX_REJECTED_MODELS).
    if model and str(model) not in _CODEX_REJECTED_MODELS:
        argv += ["-m", str(model)]
    try:
        r = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=_child_env(), timeout=timeout,
        )
        if r.returncode != 0:
            raise _classify(r.stderr or r.stdout)
        try:
            with open(out_path, encoding="utf-8") as handle:
                message = handle.read().strip()
        except OSError:
            message = (r.stdout or "").strip()
        if not message:
            raise _classify(r.stderr or "codex returned no output")
        return message
    except subprocess.TimeoutExpired as exc:
        raise CliTimeout(f"codex_cli timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise CliNotInstalled("codex CLI vanished from PATH") from exc
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def complete_text(provider: str, system: str, user: str, *, model=None, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Return a free-form completion from the user's subscription CLI."""
    exe_path = shutil.which(_exe(provider))
    if not exe_path:
        raise CliNotInstalled(
            f"{_exe(provider)} CLI not found on PATH — install it and log in to use the {provider} provider"
        )

    if provider == "codex_cli":
        prompt = (system + "\n\n" + user) if system else user
        return _codex_exec(exe_path, prompt, model=model, timeout=timeout)

    # claude_cli: system prompt as a flag, user content on stdin, JSON output.
    argv = [exe_path, "-p", "--system-prompt", system, "--output-format", "json"]
    if model:
        argv += ["--model", model]
    try:
        r = subprocess.run(
            argv, input=user, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=_child_env(), timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeout(f"{provider} timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise CliNotInstalled(f"{_exe(provider)} CLI vanished from PATH") from exc

    if r.returncode != 0:
        raise _classify(r.stderr or r.stdout)
    try:
        j = json.loads(r.stdout)
    except (ValueError, TypeError) as exc:
        raise CliError("unparseable claude output: " + (r.stdout or r.stderr or "")[:200]) from exc
    if j.get("is_error"):
        raise _classify((j.get("result") or "") + " " + (r.stderr or ""))
    return str(j.get("result") or "")


def complete_structured(provider: str, system: str, user: str, model_cls, *, model=None, timeout: int = _DEFAULT_TIMEOUT):
    """Return a parsed Pydantic model. The CLI returns text, so we instruct it to
    emit JSON matching the schema, then validate (mirrors the perplexity path)."""
    schema = json.dumps(model_cls.model_json_schema())
    system2 = (
        (system or "") +
        "\n\nReturn ONLY minified JSON matching this exact schema — no prose, no code fences:\n" + schema
    )
    txt = _strip_fences(complete_text(provider, system2, user, model=model, timeout=timeout))
    try:
        return model_cls.model_validate_json(txt)
    except Exception as exc:
        # A flaky CLI can emit prose instead of schema JSON. Surface it as a
        # CliError so the caller's subscription-failure handler falls back,
        # rather than a raw pydantic.ValidationError crashing the step.
        raise CliError(f"{provider} returned output not matching the expected schema: {str(exc)[:200]}") from exc


def _claude_auth_status(path: str) -> dict | None:
    """Rich Claude login state via `claude auth status` (JSON). None on any failure."""
    try:
        r = subprocess.run([path, "auth", "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=_child_env(), timeout=20)
        j = json.loads(r.stdout)
        return {"logged_in": bool(j.get("loggedIn")), "email": j.get("email"),
                "plan": j.get("subscriptionType"), "method": j.get("authMethod")}
    except Exception:
        return None


def _codex_logged_in(path: str) -> bool:
    try:
        r = subprocess.run([path, "login", "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=_child_env(), timeout=20)
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode == 0 and any(w in out for w in ("logged in", "signed in", "authenticated")):
            return True
    except Exception:
        pass
    return os.path.exists(os.path.join(os.path.expanduser("~"), ".codex", "auth.json"))


def status(provider: str) -> dict:
    """Install + login state for the settings UI. For Claude, uses `claude auth
    status` (rich: email + plan); falls back to credential-file heuristics."""
    exe = _exe(provider)
    path = shutil.which(exe)
    info = {"provider": provider, "installed": bool(path), "logged_in": False,
            "exe": path, "email": None, "plan": None}
    if not path:
        return info
    if provider == "claude_cli":
        rich = _claude_auth_status(path)
        if rich is not None:
            info.update(rich)
        else:
            home = os.path.expanduser("~")
            info["logged_in"] = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) \
                or os.path.exists(os.path.join(home, ".claude", ".credentials.json")) \
                or os.path.isdir(os.path.join(home, ".claude"))
    else:
        info["logged_in"] = _codex_logged_in(path)
    return info


def login(provider: str) -> dict:
    """Launch the CLI's own sign-in (browser OAuth). On Windows it opens in a new
    console so the user sees the URL/prompts; the app then polls status() until
    logged_in flips true. Never sets an API key (auth is the user's subscription)."""
    exe = _exe(provider)
    path = shutil.which(exe)
    if not path:
        raise CliNotInstalled(f"{exe} CLI not found — install it first")
    argv = [path, "auth", "login"] if provider == "claude_cli" else [path, "login"]
    kwargs = {"env": _child_env()}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)
    return {"provider": provider, "started": True, "pid": proc.pid, "cmd": " ".join([exe, *argv[1:]])}


def install_hint(provider: str) -> dict:
    """How to install the CLI (shown when it isn't on PATH)."""
    if provider == "claude_cli":
        return {"name": "Claude Code", "cmd": "npm install -g @anthropic-ai/claude-code",
                "url": "https://docs.claude.com/en/docs/claude-code/setup",
                "after": "then click Sign in (runs: claude auth login)"}
    return {"name": "Codex CLI", "cmd": "npm install -g @openai/codex",
            "url": "https://developers.openai.com/codex/cli",
            "after": "then click Sign in (runs: codex login)"}
