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

import base64
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


class CliModelUnsupported(CliError):
    """The requested -m model is rejected by the account (retry without it)."""


# Subscription-CLI provider -> the executable to shell out to. Each is a coding
# agent / assistant CLI the user has already signed into with their OWN plan
# (Claude Pro/Max, ChatGPT, Google account/Gemini, GitHub Copilot) — no API key.
_EXE = {
    "claude_cli": "claude",
    "codex_cli": "codex",
    "gemini_cli": "gemini",
    "copilot_cli": "copilot",
}


def _exe(provider: str) -> str:
    return _EXE.get(provider, "codex")


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


# A model `-m` override that the account can't use (ChatGPT-account Codex only
# exposes its own default model, e.g. gpt-5.5; API-only / -codex variants 400).
_MODEL_UNSUPPORTED_HINT = "not supported when using codex"


def _codex_error_detail(stderr: str, stdout: str) -> str:
    """Pull the meaningful failure text out of a codex run.

    `codex exec` prints a ~280-char startup banner and echoes the whole prompt on
    stderr *before* any real error, so the HEAD of stderr — which `_classify`
    truncates to 300 chars — is pure boilerplate (the banner is exactly what
    showed up, useless, in the logs). Drop everything up to the banner's closing
    rule and keep the TAIL, where codex actually reports what went wrong.
    """
    text = (stderr or "").strip()
    if "\n--------\n" in text:
        text = text.split("\n--------\n")[-1]
    detail = text[-500:].strip()
    return detail or (stdout or "").strip()[-500:] or "codex produced no output"


def _codex_run_once(exe_path: str, prompt: str, *, model, timeout: int) -> str:
    out_fd, out_path = tempfile.mkstemp(suffix="-codex.txt")
    os.close(out_fd)
    argv = [
        exe_path, "exec", "-",
        "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
        "--output-last-message", out_path,
    ]
    # Only forward an explicit, account-compatible model override; never the
    # known-rejected default (see _CODEX_REJECTED_MODELS).
    if model and str(model) not in _CODEX_REJECTED_MODELS:
        argv += ["-m", str(model)]
    try:
        r = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=_child_env(), timeout=timeout,
        )
        if r.returncode != 0:
            # Check the FULL stderr (codex prints a long banner before the error,
            # so the truncated _classify message can miss the hint).
            combined = ((r.stderr or "") + " " + (r.stdout or "")).lower()
            if _MODEL_UNSUPPORTED_HINT in combined:
                raise CliModelUnsupported(f"codex rejected model {model!r}")
            raise _classify(_codex_error_detail(r.stderr, r.stdout))
        try:
            with open(out_path, encoding="utf-8") as handle:
                message = handle.read().strip()
        except OSError:
            message = ""
        # codex writes the clean final message to the --output-last-message file
        # AND streams it to stdout; if the file is empty (a codex-version quirk),
        # salvage stdout before giving up.
        if not message:
            message = (r.stdout or "").strip()
        if not message:
            # A genuinely empty turn: codex ended without a text reply (it only
            # reasoned, or attempted a sandboxed action it couldn't complete).
            # Surface that clearly instead of its useless boilerplate banner.
            raise _classify(
                "codex ended its turn without a final text message — "
                + _codex_error_detail(r.stderr, "")
            )
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


def _codex_exec(exe_path: str, prompt: str, *, model, timeout: int) -> str:
    """Run `codex exec` non-interactively and return its final message.

    The prompt (incl. any embedded JSON schema) goes on STDIN — never argv — so
    it can't be mangled by the Windows `codex.cmd` shim / cmd.exe or hit the
    ~32K command-line limit. We read the clean final message from
    --output-last-message rather than scraping the agent's streamed stdout.
    --skip-git-repo-check lets it run from the sidecar's app-data cwd (not a git
    repo); --sandbox read-only keeps any model-issued command harmless.

    If an explicit model override is rejected by the account (ChatGPT-account
    Codex only allows its own default model), we transparently retry once
    WITHOUT -m so the call still succeeds on the user's default model.
    """
    try:
        return _codex_run_once(exe_path, prompt, model=model, timeout=timeout)
    except CliModelUnsupported:
        # Only retry if we actually forwarded a model; otherwise the account's
        # own default is the problem and there's nothing to drop.
        if model and str(model) not in _CODEX_REJECTED_MODELS:
            return _codex_run_once(exe_path, prompt, model=None, timeout=timeout)
        raise


def _gemini_exec(exe_path: str, system: str, user: str, *, model, timeout: int) -> str:
    """Gemini CLI in headless mode: `gemini --output-format json [-m M]`, prompt on
    STDIN (non-TTY stdin = non-interactive), clean text read from the JSON
    `response` field. Auth is the user's Google account / Gemini plan OAuth."""
    prompt = (system + "\n\n" + user) if system else user
    argv = [exe_path, "--output-format", "json"]
    if model:
        argv += ["-m", str(model)]
    try:
        r = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=_child_env(), timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeout(f"gemini_cli timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise CliNotInstalled("gemini CLI vanished from PATH") from exc
    out = (r.stdout or "").strip()
    # Preferred path: structured JSON {"response": "...", "error": {...}}.
    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict):
            if parsed.get("error"):
                raise _classify(f"{parsed.get('error')} {r.stderr or ''}")
            text = str(parsed.get("response") or "").strip()
            if text:
                return text
    except (ValueError, TypeError):
        pass  # not JSON — fall through to raw stdout / error handling
    if r.returncode != 0:
        raise _classify(r.stderr or out or "gemini returned no output")
    if not out:
        raise _classify(r.stderr or "gemini returned no output")
    return out


def _copilot_exec(exe_path: str, system: str, user: str, *, model, timeout: int) -> str:
    """GitHub Copilot CLI programmatic mode: `copilot -p <prompt> -s --no-ask-user
    [--model M]`. `-s` prints only the response; `--no-ask-user` stops it pausing
    for input in a headless run. Auth is the user's GitHub Copilot subscription."""
    prompt = (system + "\n\n" + user) if system else user
    argv = [exe_path, "-p", prompt, "-s", "--no-ask-user"]
    if model:
        argv += ["--model", str(model)]
    try:
        r = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=_child_env(), timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeout(f"copilot_cli timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise CliNotInstalled("copilot CLI vanished from PATH") from exc
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        raise _classify(r.stderr or out or "copilot call failed")
    if not out:
        raise _classify(r.stderr or "copilot returned no output")
    return out


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
    if provider == "gemini_cli":
        return _gemini_exec(exe_path, system, user, model=model, timeout=timeout)
    if provider == "copilot_cli":
        return _copilot_exec(exe_path, system, user, model=model, timeout=timeout)

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


def _jwt_claims(token: str) -> dict:
    """Decode a JWT's payload (claims) without verifying the signature. Used only
    to read identity claims (email / plan) locally — the token itself is never
    logged or returned."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _codex_auth_status() -> dict | None:
    """Rich Codex login state — the signed-in email and ChatGPT plan — read
    locally from the id_token claims in ~/.codex/auth.json. Returns only those
    identity fields (never the token). None if the file is missing/unreadable."""
    path = os.path.join(os.path.expanduser("~"), ".codex", "auth.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    claims = _jwt_claims(str(tokens.get("id_token") or tokens.get("access_token") or ""))
    auth_blk = claims.get("https://api.openai.com/auth") or {}
    plan = auth_blk.get("chatgpt_plan_type")
    return {
        "logged_in": True,
        "email": claims.get("email") or None,
        # "plus" -> "Plus", "pro" -> "Pro"; prefix so it reads like Claude's plan.
        "plan": f"ChatGPT {plan.title()}" if isinstance(plan, str) and plan else None,
        "method": data.get("auth_mode") or None,
    }


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


def _gemini_logged_in() -> bool:
    """Gemini CLI stores its Google-account OAuth under ~/.gemini. (A
    GEMINI_API_KEY/GOOGLE_API_KEY would also work, but that's the API-key path.)"""
    home = os.path.expanduser("~")
    gemini_dir = os.path.join(home, ".gemini")
    return (
        os.path.exists(os.path.join(gemini_dir, "oauth_creds.json"))
        or os.path.exists(os.path.join(gemini_dir, "google_accounts.json"))
        or os.path.isdir(gemini_dir)
        or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    )


def _copilot_logged_in() -> bool:
    """Copilot CLI authenticates with the user's GitHub Copilot subscription via a
    GitHub token (env or the gh CLI's stored login)."""
    if any(os.environ.get(v) for v in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".config", "gh", "hosts.yml")) or os.path.isdir(os.path.join(home, ".copilot")):
        return True
    try:
        gh = shutil.which("gh")
        if gh:
            r = subprocess.run([gh, "auth", "status"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=_child_env(), timeout=20)
            if r.returncode == 0:
                return True
    except Exception:
        pass
    return False


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
    elif provider == "gemini_cli":
        info["logged_in"] = _gemini_logged_in()
    elif provider == "copilot_cli":
        info["logged_in"] = _copilot_logged_in()
    else:  # codex_cli — show the signed-in ChatGPT account + plan, like Claude
        rich = _codex_auth_status()
        if rich is not None:
            info.update(rich)
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
    if provider == "claude_cli":
        argv = [path, "auth", "login"]
    elif provider == "codex_cli":
        argv = [path, "login"]
    else:
        # gemini / copilot: launching the CLI itself runs its sign-in flow
        # (Google account OAuth / GitHub Copilot device auth) in the new console.
        argv = [path]
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
    if provider == "gemini_cli":
        return {"name": "Gemini CLI", "cmd": "npm install -g @google/gemini-cli",
                "url": "https://github.com/google-gemini/gemini-cli",
                "after": "then click Sign in and authorize your Google account"}
    if provider == "copilot_cli":
        return {"name": "GitHub Copilot CLI", "cmd": "npm install -g @github/copilot",
                "url": "https://docs.github.com/copilot/concepts/agents/about-copilot-cli",
                "after": "then sign in with your GitHub Copilot account"}
    return {"name": "Codex CLI", "cmd": "npm install -g @openai/codex",
            "url": "https://developers.openai.com/codex/cli",
            "after": "then click Sign in (runs: codex login)"}
