import os
import ipaddress
from urllib.parse import urlparse
import httpx
import anthropic
import instructor
from openai import OpenAI
from pydantic import BaseModel
from data.repository import Repository, create_repository
from core.logging import get_logger

_log = get_logger(__name__)

_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
_repo: Repository = create_repository()


def configure_repository(repo: Repository) -> None:
    global _repo
    _repo = repo


def get_setting(key: str, default: str = "") -> str:
    return _repo.settings.get_setting(key, default)

# Maps provider id → settings key holding the global API key
_KEY_NAMES: dict[str, str] = {
    "anthropic": "anthropic_key",
    "gemini":    "gemini_api_key",
    "groq":      "groq_api_key",
    "nvidia":    "nvidia_api_key",
    "openai":    "openai_api_key",
    "deepseek":  "deepseek_api_key",
    "xai":       "xai_api_key",
    "kimi":      "kimi_api_key",
    "mistral":   "mistral_api_key",
    "openrouter": "openrouter_api_key",
    "together":  "together_api_key",
    "fireworks": "fireworks_api_key",
    "cerebras":  "cerebras_api_key",
    "perplexity": "perplexity_api_key",
    "huggingface": "huggingface_api_key",
    "cohere": "cohere_api_key",
    "sambanova": "sambanova_api_key",
    "qwen": "qwen_api_key",
    "azure": "azure_openai_api_key",
    "custom":    "custom_api_key",
}

# Maps provider id → environment variable fallback
_ENV_NAMES: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "groq":      "GROQ_API_KEY",
    "nvidia":    "NVIDIA_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "deepseek":  "DEEPSEEK_API_KEY",
    "xai":       "XAI_API_KEY",
    "kimi":      "MOONSHOT_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together":  "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "cerebras":  "CEREBRAS_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "huggingface": "HF_TOKEN",
    "cohere": "COHERE_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "custom":    "OPENAI_COMPAT_API_KEY",
}

# Default model per provider (used when no step/global model is set)
_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "gemini":    "gemini-2.5-flash",
    "groq":      "llama-3.3-70b-versatile",
    "nvidia":    "z-ai/glm-5.1",
    "openai":    "gpt-4o-mini",
    "deepseek":  "deepseek-chat",
    "xai":       "grok-4",
    "kimi":      "kimi-k2.6",
    "mistral":   "mistral-large-latest",
    "openrouter": "openrouter/auto",
    "together":  "openai/gpt-oss-120b",
    "fireworks": "accounts/fireworks/models/llama-v3p1-70b-instruct",
    "cerebras":  "llama-3.3-70b",
    "perplexity": "sonar",
    "huggingface": "openai/gpt-oss-120b",
    "cohere": "command-a-03-2025",
    "sambanova": "Meta-Llama-3.3-70B-Instruct",
    "qwen": "qwen-plus",
    "azure": "gpt-4o-mini",
    "custom":    "model-id",
    "ollama":    "llama3",
}

_OPENAI_COMPAT_BASE_URLS: dict[str, str] = {
    "xai": "https://api.x.ai/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "perplexity": "https://api.perplexity.ai/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "cohere": "https://api.cohere.ai/compatibility/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
}

_OPENAI_COMPAT_PROVIDERS = set(_OPENAI_COMPAT_BASE_URLS) | {"azure", "custom"}
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _validate_base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid base URL: {url}")
    host = parsed.hostname or ""
    if host.lower() in _BLOCKED_HOSTS:
        raise ValueError(f"Cannot use localhost as LLM base URL: {url}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError(f"Cannot use private/loopback IP as LLM base URL: {url}")
    return url


def _provider_base_url(provider: str) -> str:
    if provider == "azure":
        base = (
            get_setting("azure_openai_endpoint", "")
            or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        ).strip().rstrip("/")
        if not base:
            raise ValueError("Azure OpenAI endpoint is required")
        if not base.endswith("/openai/v1"):
            base = f"{base}/openai/v1"
        return _validate_base_url(base)
    if provider == "custom":
        return _validate_base_url(
            get_setting("custom_base_url", "")
            or os.environ.get("OPENAI_COMPAT_BASE_URL", "")
            or "https://api.openai.com/v1"
        )
    return _OPENAI_COMPAT_BASE_URLS[provider]


def _resolve(step: str | None = None) -> tuple[str, str, str]:
    """
    Resolve (provider, api_key, model) for a given pipeline step.

    Priority order:
      1. Step-specific setting  ({step}_provider / {step}_api_key / {step}_model)
      2. Global setting         (llm_provider / provider key / nvidia_model etc.)
      3. Environment variable   (ANTHROPIC_API_KEY etc.)
      4. Hardcoded defaults
    """
    sp = get_setting(f"{step}_provider", "") if step else ""
    sk = get_setting(f"{step}_api_key",  "") if step else ""
    sm = get_setting(f"{step}_model",    "") if step else ""

    p = sp or get_setting("llm_provider", "ollama")

    # API key: step-specific > global setting for this provider > env var
    if sk:
        k = sk
    else:
        k = (get_setting(_KEY_NAMES.get(p, ""), "")
             or os.environ.get(_ENV_NAMES.get(p, ""), "")
             or (os.environ.get("GOOGLE_API_KEY", "") if p == "gemini" else ""))

    # Model: step-specific > provider-level setting > default
    if sm:
        model = sm
    elif p in _DEFAULT_MODELS:
        model = get_setting(f"{p}_model", _DEFAULT_MODELS[p])
    else:
        model = _DEFAULT_MODELS.get(p, "llama3")

    if step:
        _log.debug("step=%s → provider=%s model=%s", step, p, model)

    return p, k, model


def resolve_config(step: str | None = None) -> tuple[str, str, str]:
    """Public resolver for agents that need provider-specific request shapes."""
    return _resolve(step)


def _client_nvidia(k: str):
    return instructor.from_openai(
        OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=k,
            timeout=_TIMEOUT,
            max_retries=0,
        ),
        mode=instructor.Mode.JSON,
    )


def _client_gemini(k: str):
    return OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=k,
        timeout=_TIMEOUT,
        max_retries=0,
    )


def _client_openai_compat(provider: str, key: str):
    return OpenAI(
        base_url=_provider_base_url(provider),
        api_key=key,
        timeout=_TIMEOUT,
        max_retries=0,
    )


def call_llm(s: str, u: str, m: type[BaseModel], step: str | None = None):
    """
    Call LLM with structured output.

    Pass `step` (e.g. "evaluator", "scout", "ingestor") to use that step's
    per-step provider/key/model settings. Omit for global defaults.
    """
    p, k, model = _resolve(step)

    if p == "anthropic":
        if not k:
            _log.warning("anthropic — no key (step=%s) — falling back", step)
            return _parse_fallback(u, m)
        c = anthropic.Anthropic(api_key=k, timeout=120.0)
        r = c.messages.parse(
            model=model,
            max_tokens=4096,
            system=s,
            messages=[{"role": "user", "content": u}],
            output_format=m,
        )
        return r.parsed_output

    elif p == "groq":
        if not k:
            _log.warning("groq — no key (step=%s) — falling back", step)
            return _parse_fallback(u, m)
        c = instructor.from_openai(
            OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k,
                   timeout=_TIMEOUT, max_retries=0)
        )
        return c.chat.completions.create(
            model=model,
            response_model=m,
            max_retries=1,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )

    elif p == "gemini":
        if not k:
            _log.warning("gemini: no key (step=%s); falling back", step)
            return _parse_fallback(u, m)
        c = instructor.from_openai(_client_gemini(k), mode=instructor.Mode.JSON)
        return c.chat.completions.create(
            model=model,
            response_model=m,
            max_retries=1,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )

    elif p == "nvidia":
        if not k:
            _log.warning("nvidia — no key (step=%s) — falling back", step)
            return _parse_fallback(u, m)
        c = _client_nvidia(k)
        return c.chat.completions.create(
            model=model,
            response_model=m,
            max_retries=1,
            max_tokens=16384,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

    elif p == "openai":
        if not k:
            _log.warning("openai — no key (step=%s)", step)
            return _parse_fallback(u, m)
        c = instructor.from_openai(OpenAI(api_key=k, timeout=_TIMEOUT))
        return c.chat.completions.create(
            model=model,
            response_model=m,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )

    elif p == "deepseek":
        if not k:
            _log.warning("deepseek — no key (step=%s)", step)
            return _parse_fallback(u, m)
        # deepseek-reasoner does not support tool_choice — use JSON mode instead
        mode = instructor.Mode.JSON if "reasoner" in model else instructor.Mode.TOOLS
        c = instructor.from_openai(
            OpenAI(base_url="https://api.deepseek.com", api_key=k, timeout=_TIMEOUT),
            mode=mode,
        )
        return c.chat.completions.create(
            model=model,
            response_model=m,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )

    elif p in _OPENAI_COMPAT_PROVIDERS:
        if not k:
            _log.warning("%s — no key (step=%s)", p, step)
            return _parse_fallback(u, m)
        if p == "perplexity":
            schema = m.model_json_schema()
            raw = call_raw(
                s + "\nReturn only valid JSON matching this schema:\n" + str(schema),
                u,
                step=step,
            )
            try:
                return m.model_validate_json(raw)
            except Exception:
                _log.warning("perplexity structured parse failed (step=%s)", step)
                return _parse_fallback(u, m)
        try:
            client = _client_openai_compat(p, k)
        except ValueError as exc:
            _log.warning("%s configuration invalid (step=%s): %s", p, step, exc)
            return _parse_fallback(u, m)
        c = instructor.from_openai(
            client,
            mode=instructor.Mode.JSON,
        )
        return c.chat.completions.create(
            model=model,
            response_model=m,
            max_retries=1,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )

    else:  # ollama / default
        b = get_setting("ollama_url", "http://localhost:11434/v1")
        _log.info("ollama at %s model=%s (step=%s)", b, model, step)
        c = instructor.from_openai(
            OpenAI(base_url=b, api_key="ollama", timeout=_TIMEOUT, max_retries=0)
        )
        return c.chat.completions.create(
            model=model,
            response_model=m,
            max_retries=1,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )


def call_raw(s: str, u: str, step: str | None = None) -> str:
    """
    Call LLM for free-form text output.

    Pass `step` (e.g. "generator") to use that step's per-step settings.
    """
    p, k, model = _resolve(step)

    if p == "anthropic":
        if not k:
            return ""
        c = anthropic.Anthropic(api_key=k, timeout=120.0)
        r = c.messages.create(
            model=model,
            max_tokens=4096,
            system=s,
            messages=[{"role": "user", "content": u}],
        )
        return r.content[0].text

    elif p == "groq":
        if not k:
            return ""
        c = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k,
                   timeout=_TIMEOUT, max_retries=0)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""

    elif p == "gemini":
        if not k:
            return ""
        c = _client_gemini(k)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""

    elif p == "nvidia":
        if not k:
            return ""
        c = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=k,
                   timeout=_TIMEOUT, max_retries=0)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
            max_tokens=16384,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return r.choices[0].message.content or ""

    elif p == "openai":
        if not k:
            return ""
        c = OpenAI(api_key=k, timeout=_TIMEOUT)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""

    elif p == "deepseek":
        if not k:
            return ""
        c = OpenAI(base_url="https://api.deepseek.com", api_key=k, timeout=_TIMEOUT)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""

    elif p in _OPENAI_COMPAT_PROVIDERS:
        if not k:
            return ""
        try:
            c = _client_openai_compat(p, k)
        except ValueError as exc:
            _log.warning("%s configuration invalid (step=%s): %s", p, step, exc)
            return ""
        if p == "perplexity":
            r = c.responses.create(
                model=model,
                instructions=s,
                input=u,
            )
            return getattr(r, "output_text", "") or ""
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""

    else:  # ollama
        b = get_setting("ollama_url", "http://localhost:11434/v1")
        c = OpenAI(base_url=b, api_key="ollama", timeout=_TIMEOUT, max_retries=0)
        r = c.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
        )
        return r.choices[0].message.content or ""


def _parse_fallback(u: str, m: type[BaseModel]):
    """Minimal local fallback — no LLM, returns empty structured output."""
    try:
        return m()
    except Exception:
        return m.model_construct()
