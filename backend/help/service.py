from __future__ import annotations
import logging

import re
from pathlib import Path

from llm import call_raw, resolve_config


_DOCS = (
    "README.md",
    "docs/windows-release.md",
    "docs/source-adapters.md",
    "docs/ARCHITECTURE.md",
)

_USER_GUIDE = """
## In-app user guide

Tone and answer style:
- Answer like a practical in-app support guide.
- Prefer step-by-step instructions when the user asks "how".
- Use the real page names and labels from the app.
- Keep answers concise enough for a chat panel, but include all required steps.
- If the user asks for an unsupported feature, say what exists now and the closest supported workflow.
- Never ask the user to paste private API keys, resumes, cookies, bearer tokens, or local database files into chat.

First-time setup:
1. Open JustHireMe.
2. Wait for the local backend to start. The startup screen shows backend connection and port.
3. Open Settings.
4. In Global AI, choose a provider: Gemini, DeepSeek, NVIDIA, Groq, Grok/xAI, Kimi, Mistral, OpenRouter, Together, Fireworks, Cerebras, Perplexity, Hugging Face, OpenAI, Anthropic, Custom, or Ollama.
5. For cloud providers, paste the API key in the provider key field.
6. Pick a model from the model chips or type a model id.
7. Use the provider check panel to verify connectivity.
8. Open Add Context or Profile and add resume/profile context before relying on ranking or generated documents.
9. Open Settings > Scraping & Discovery and add sources.
10. Go to Dashboard and run a scan.
11. Review leads in Leads, then generate materials in Customize.

How to get an API key:
- OpenAI: go to https://platform.openai.com/api-keys, sign in, create a secret key, copy it once, then paste it into Settings > Global AI after selecting OpenAI.
- Gemini: go to https://aistudio.google.com/app/apikey, sign in with Google, create an API key, then paste it into Settings > Global AI after selecting Gemini.
- Groq: go to https://console.groq.com/keys, sign in, create an API key, then paste it into Settings > Global AI after selecting Groq.
- Anthropic: go to https://console.anthropic.com/settings/keys, sign in, create an API key, then paste it into Settings > Global AI after selecting Anthropic.
- DeepSeek: go to https://platform.deepseek.com/api_keys, sign in, create an API key, then paste it into Settings > Global AI after selecting DeepSeek.
- NVIDIA: go to https://build.nvidia.com/, sign in, open a model page, use Get API Key, then paste it into Settings > Global AI after selecting NVIDIA.
- Grok/xAI: go to https://console.x.ai/, create an API key, then paste it into Settings > Global AI after selecting Grok.
- Kimi/Moonshot: go to https://platform.kimi.ai/, create an API key, then paste it into Settings > Global AI after selecting Kimi.
- Mistral: go to https://console.mistral.ai/, create an API key, then paste it into Settings > Global AI after selecting Mistral.
- OpenRouter: go to https://openrouter.ai/keys, create an API key, then paste it into Settings > Global AI after selecting OpenRouter.
- Together: go to https://api.together.ai/settings/api-keys, create an API key, then paste it into Settings > Global AI after selecting Together.
- Fireworks: go to https://fireworks.ai/account/api-keys, create an API key, then paste it into Settings > Global AI after selecting Fireworks.
- Cerebras: go to https://cloud.cerebras.ai/platform, create an API key, then paste it into Settings > Global AI after selecting Cerebras.
- Perplexity: go to https://www.perplexity.ai/settings/api, create an API key, then paste it into Settings > Global AI after selecting Perplexity.
- Hugging Face: go to https://huggingface.co/settings/tokens, create a token, then paste it into Settings > Global AI after selecting Hugging Face.
- Custom: choose Custom, paste any OpenAI-compatible API key, set the base URL from your provider, and type the model id.
- Ollama: install and run Ollama locally, pull a model such as llama3 or mistral, keep the URL as http://localhost:11434/v1 in Settings > Global AI, and select Ollama. Ollama does not use a cloud API key.

API key safety:
- API keys are sensitive. Do not post them in issues, screenshots, logs, or chat.
- JustHireMe stores settings locally for now; OS keychain storage is planned.
- If a key is leaked, revoke it from the provider dashboard and create a new one.
- If a provider fails, check the key, billing/credits, selected model, and provider status.

Provider and model configuration:
- Global AI sets the default provider/model for agents.
- Per-Step Configuration can override Scout, Evaluator, Generator, Ingestor, or Actuator.
- Leave a step provider blank to inherit Global AI.
- Use Scout for scraping/parsing, Evaluator for job fit analysis, Generator for resume/cover letter/outreach, Ingestor for profile context extraction, and Actuator only for experimental automation.
- If generated material quality is poor, improve Profile/Add Context first, then use a stronger Generator model.

Adding job sources and links:
1. Open Settings.
2. Go to Scraping & Discovery.
3. Choose Global market for worldwide sources or India market for Indian/local and remote-India roles.
4. Optionally fill Target roles / titles with the roles you want the profile to search toward.
5. Use the quick buttons for Global preset, India preset, HN Hiring, RemoteOK, Remotive, Jobicy, We Work Remotely, LinkedIn, Indeed, Naukri, Foundit, Internshala, and other role-neutral sources.
6. To add a custom source, paste a job site, ATS board, RSS/API URL, or plain domain into the Add source input.
7. Click Add source.
8. Review the Target job boards / search URLs textarea.
9. Run a scan from Dashboard.

Target job boards and markets:
- JustHireMe is not limited to tech. Global and India presets are broad job markets.
- Query generation tailors site: sources using the user's profile, skills, role themes, seniority, and selected market.
- India market keeps India intent in generated searches and avoids broad global-only feeds.

Source formats:
- hn-hiring: Hacker News Who is Hiring.
- https://remoteok.com/api, Remotive API, Jobicy API: direct API sources.
- RSS/XML/feed URLs: parsed as feeds.
- ATS/company boards from Greenhouse, Lever, Ashby, and Workable: prefer direct URLs where possible.
- site:company-careers.test jobs India: broad search target.
- Plain domain like company-careers.test: the app converts it into a site: search target with job and location terms.

Custom connectors:
- Open Settings > Scraping & Discovery > Custom Connectors.
- Turn Connector scan on.
- Add connector definitions as a JSON array. Each connector needs name, url, method GET, items_path, and fields mapping.
- Put private API headers in Connector headers, not in connector definitions. Headers are treated as sensitive settings.
- Custom connectors are for premium/private JSON APIs, internal feeds, and paid lead providers. They are normalized into leads and pass through the same quality gate.

Improving scrape quality:
- Prefer direct ATS/company API or board URLs over generic websites.
- Prefer fresh, specific search targets over broad ones.
- Include role/location terms in site: targets.
- Use HN Hiring for startup leads, but expect varied formatting.
- Thin, stale, spammy, senior-only, or low-context leads are filtered by the quality gate before they enter the pipeline.
- Good normalized leads include title, company, URL, platform, description, posted date if visible, quality score, and quality reason.

Scanning:
1. Configure sources in Settings > Scraping & Discovery.
2. Go to Dashboard.
3. Click scan/run scan.
4. Watch Activity for scan events and failures.
5. Open Leads to review approved matches.
6. If results are noisy, tighten sources and rerun cleanup/scan.

Leads:
- Leads shows matching leads and quality/fit signals.
- Open Details to inspect the description, extracted details, signal, and source URL.
- Use delete/remove for bad rows.
- Quality means source/posting quality. Fit means how well the role matches the user's profile.

Customize / generating a package:
1. Open Customize.
2. Paste a job URL or full job description.
3. Click Analyse & Generate / Generate Resume.
4. Wait for resume PDF, cover letter PDF, and outreach drafts.
5. Review the PDF previews and text before using them.
6. If generation is weak, add more profile context in Profile/Add Context and use a stronger Generator model.

Profile and Add Context:
- Profile stores identity, skills, projects, experience, and links.
- Add Context ingests resume, GitHub/portfolio notes, and extra career context.
- Better profile context improves ranking, selected-project rationale, resume tailoring, and cover letters.
- Keep private personal data local and avoid sharing screenshots with sensitive content.

Knowledge:
- Knowledge shows local graph/vector profile context.
- If matching feels generic, add richer project/resume context and re-ingest.
- Vector and graph data are local app data.

Pipeline and follow-ups:
- Job Pipeline tracks statuses and follow-up work.
- Use it after reviewing leads or generating packages.
- Activity shows events for scans, scoring, generation, cleanup, and failures.

Experimental automation:
- Experimental Auto Apply is a contributor lab, disabled by default, and not part of the supported core workflow.
- The supported workflow is scrape, rank, review, customize, and manually submit.
- If asked about auto-apply, explain that it is experimental and should be used only for testing.

Install and Windows security prompt:
1. Download the installer from GitHub Releases.
2. Run the .exe.
3. If Windows SmartScreen appears, click More info.
4. Click Run anyway.
5. The installer includes the desktop app and bundled backend pieces needed for a non-technical user to start. They still need their own LLM API key or local Ollama setup for AI features.
6. Release notes include SHA256 checksums so users can verify installer integrity.

Common troubleshooting:
- Backend stuck starting: restart the app, then check Activity after startup.
- LLM says unavailable: verify Settings > Global AI provider, key, model, billing/credits, and internet.
- No leads: add sources in Settings > Scraping & Discovery, use direct ATS/API sources, then scan from Dashboard.
- Bad leads: delete them, tighten source targets, use cleanup, and prefer direct boards.
- Resume/cover letter not generated: check API key/model, paste a full job description, and make sure Profile/Add Context has useful profile data.
- PDF preview blocked or blank: restart the app and regenerate; if it persists, report the Activity error.
- Auto Apply blocked: enable Experimental Auto Apply only in settings if testing the lab feature; otherwise use manual application.
"""

_PROVIDER_GUIDE = """
What an API key is:
- An API key is a private password/token from an AI provider. JustHireMe uses it to call that provider's LLM from your local app.
- You only paste the key into Settings > Global AI or a Per-Step Configuration field. Do not paste it into chat, screenshots, issues, or logs.
- Ollama is the local option and does not need a cloud API key.

LLM providers available in JustHireMe:
- Gemini: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash.
- DeepSeek: deepseek-chat, deepseek-reasoner.
- NVIDIA: z-ai/glm-5.1, meta/llama-3.1-70b-instruct, Nemotron/NIM models.
- Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant, openai/gpt-oss-120b.
- Grok/xAI: grok-4, grok-3, grok-3-mini.
- Kimi/Moonshot: kimi-k2-turbo-preview, kimi-k2.5, moonshot-v1-128k.
- Mistral: mistral-large-latest, mistral-medium-latest, mistral-small-latest, ministral-8b-latest.
- OpenRouter: openrouter/auto plus many routed models.
- Together: openai/gpt-oss-120b, Llama, DeepSeek, Kimi.
- Fireworks: Llama, Qwen, DeepSeek models.
- Cerebras: llama-3.3-70b, llama3.1-8b, gpt-oss-120b.
- Perplexity: sonar, sonar-pro, sonar-reasoning, sonar-deep-research.
- Hugging Face Router: openai/gpt-oss-120b, Llama, Qwen and other hosted models.
- OpenAI: gpt-4o-mini, gpt-4o, gpt-4-turbo.
- Anthropic: Claude Sonnet, Haiku, Opus.
- Custom: any OpenAI-compatible base URL and model id.
- Ollama: local models like llama3, mistral, gemma2, codellama.

How to configure an LLM:
1. Open Settings > Global AI.
2. Pick the provider you want.
3. For cloud providers, create an API key on that provider's dashboard and paste it into the matching key field.
4. Pick a model chip or type the exact model id.
5. Run the provider check.
6. Optional: use Per-Step Configuration to choose different models for Scout, Evaluator, Generator, Ingestor, or Experimental Actuator.
7. If a model fails, check key, billing/credits, model id, internet, and provider status.
"""

_SOURCE_GUIDE = """
How to add a source and scan:
1. Open Settings > Scraping & Discovery.
2. Choose Global market for worldwide sources or India market for Indian/local and remote-India roles.
3. Optionally fill Target roles / titles with the roles you want the profile to search toward.
4. Use quick presets for Global, India, HN Hiring, RemoteOK, Remotive, Jobicy, We Work Remotely, LinkedIn, Indeed, Naukri, Foundit, or Internshala.
5. For a custom source, paste a company careers page, ATS board, RSS/API URL, search target, or plain domain into Add source.
6. Click Add source.
7. Review Target job boards / search URLs.
8. Go to Dashboard and click Scan sources.
9. Open Leads to review approved matches.

For premium/private JSON APIs:
1. Open Custom Connectors in the same settings page.
2. Turn Connector scan on.
3. Add a JSON connector definition with name, url, items_path, and fields.
4. Add private API headers in Connector headers.
5. Run a Dashboard scan; connector results are quality-gated like every other lead.

Best source formats:
- Direct APIs/RSS: RemoteOK API, Remotive API, Jobicy API, We Work Remotely RSS.
- ATS/job boards: Greenhouse, Lever, Ashby, Workable, LinkedIn, Indeed, Naukri, Foundit, Internshala, Glassdoor, SmartRecruiters, and Workday targets.
- HN Hiring: hn-hiring.
- Search targets: site:jobs.lever.co India, site:boards.greenhouse.io remote marketing, site:naukri.com jobs India.
- Plain domain: company-careers.test, which the app turns into a targeted job search.

For better scrape quality:
1. Prefer direct ATS/API/RSS links over broad generic websites.
2. Add role and location terms to site: searches.
3. Keep sources fresh and specific.
4. Use cleanup if stale or weak rows got through.
5. Remember quality is posting quality; fit is how well it matches your profile.
"""

_WORKFLOW_GUIDE = """
Recommended workflow:
1. Open Settings > Global AI and configure Gemini, DeepSeek, NVIDIA, Groq, Grok/xAI, Kimi, Mistral, OpenRouter, Together, Fireworks, Cerebras, Perplexity, Hugging Face, OpenAI, Anthropic, Custom, or Ollama.
2. Open Profile or Add Context and add your resume, skills, projects, links, and notes.
3. Open Settings > Scraping & Discovery and add source presets or custom job sources.
4. Go to Dashboard and click Scan sources.
5. Open Leads and review quality-gated matches.
6. Open Customize for a strong role, paste the job URL or full description, then generate the resume, cover letter, and outreach drafts.
7. Track serious roles in Job Pipeline.
"""

_CUSTOMIZE_GUIDE = """
How to generate a tailored package:
1. Open Profile/Add Context first and make sure your resume, skills, projects, and experience are present.
2. Open Customize.
3. Paste a job URL or the full job description.
4. Click Analyse & Generate / Generate Resume.
5. Wait for the resume PDF, cover letter PDF, and outreach drafts.
6. Review everything before sending.
7. If the result is weak, add richer project/profile context and use a stronger Generator model in Settings.
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_doc(path: str, limit: int = 9000) -> str:
    file = _repo_root() / path
    try:
        text = file.read_text(encoding="utf-8", errors="ignore")
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/help/service.py:_read_doc: %s', log_exc)
        return ""
    return f"\n\n## {path}\n{text[:limit]}"


def _knowledge() -> str:
    docs = "".join(_read_doc(path) for path in _DOCS)
    product_brief = """
## Product brief
JustHireMe is a local-first Tauri desktop workbench for job search intelligence.
The frontend is React/TypeScript. The backend is a local FastAPI sidecar.
Core workflows: import profile/resume, scrape job leads, quality-gate noisy rows,
rank fit, review leads, generate tailored resume PDF, cover letter PDF, and
outreach drafts. Data stays local by default.

Main pages:
- Dashboard: command center, scans, activity, pipeline snapshot.
- Customize: paste a job URL/text and generate the application package.
- Leads: review matching leads.
- Job Pipeline: track statuses and follow-ups.
- Knowledge: local profile graph/vector context.
- Activity: event trail for scans, scoring, generation, and failures.
- Profile: candidate identity, skills, projects, experience, links.
- Add Context: ingest resume, GitHub, portfolio, notes, and extra profile context.
- Settings: LLM provider, API keys, discovery sources, automation lab settings.

Important behavior:
- Browser automation/auto-apply is experimental and opt-in.
- API keys are stored in local settings for now; OS keychain is planned.
- The app uses the user's configured LLM provider/model when a backend agent calls llm.call_raw/call_llm.
- If a model or key is missing, some agents use deterministic fallbacks and should explain that limitation.
"""
    return product_brief + _USER_GUIDE + docs


def _words(question: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", question.lower()))


def _topic(question: str) -> str:
    w = _words(question)
    q = question.lower()
    if {"api", "key"} & w or "llm" in w or "model" in w or "provider" in w or "available" in w:
        return "providers"
    if "scrap" in q or "source" in w or "sources" in w or "job board" in q or "crawl" in q:
        return "sources"
    if "resume" in w or "cover" in w or "customize" in w or "package" in w or "generate" in w:
        return "customize"
    if "start" in w or "setup" in w or "first" in w or ("what" in w and "do" in w):
        return "workflow"
    if "auto" in w and "apply" in w:
        return "auto_apply"
    if "install" in w or "download" in w or "exe" in w or "windows" in w:
        return "install"
    return "general"


def _focused_knowledge(question: str) -> str:
    topic = _topic(question)
    brief = """
JustHireMe is a local-first Tauri desktop workbench. Main pages are Dashboard,
Customize, Leads, Job Pipeline, Knowledge, Activity, Profile, Add Context, and Settings.
Core workflow: configure LLM, add profile context, add sources, scan, review leads,
generate resume/cover letter/outreach, then track roles.
"""
    chunks = {
        "providers": _PROVIDER_GUIDE + "\n" + _USER_GUIDE[_USER_GUIDE.find("How to get an API key:"):_USER_GUIDE.find("Adding job sources and links:")],
        "sources": _SOURCE_GUIDE,
        "customize": _CUSTOMIZE_GUIDE,
        "workflow": _WORKFLOW_GUIDE,
        "auto_apply": "Experimental Auto Apply is a contributor lab. It is disabled by default and unsupported for normal users. The supported workflow is scrape, rank, review, customize, and manually submit.",
        "install": _USER_GUIDE[_USER_GUIDE.find("Install and Windows security prompt:"):_USER_GUIDE.find("Common troubleshooting:")],
        "general": _WORKFLOW_GUIDE + "\n" + _SOURCE_GUIDE + "\n" + _CUSTOMIZE_GUIDE,
    }
    return (brief + "\n" + chunks.get(topic, chunks["general"]))[:5500]


def _steps(title: str, items: list[str]) -> str:
    lines = [title]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item}")
    return "\n".join(lines)


def _fallback(question: str) -> str:
    q = question.lower()
    topic = _topic(question)
    if topic == "providers":
        return (
            "An API key is the private token/password your AI provider gives you so JustHireMe can call its LLM from your local app. "
            "Do not paste keys into chat or screenshots.\n\n"
            "Available LLM providers here:\n"
            "1. Gemini: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash.\n"
            "2. DeepSeek: deepseek-chat, deepseek-reasoner.\n"
            "3. NVIDIA: z-ai/glm-5.1, Llama/Nemotron NIM models.\n"
            "4. Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant, gpt-oss.\n"
            "5. Grok/xAI: grok-4, grok-3, grok-3-mini.\n"
            "6. Kimi/Moonshot: kimi-k2, kimi-k2.5, moonshot-v1.\n"
            "7. Mistral, OpenRouter, Together, Fireworks, Cerebras, Perplexity, Hugging Face Router.\n"
            "8. OpenAI and Anthropic.\n"
            "9. Custom OpenAI-compatible provider.\n"
            "10. Ollama for local models; no cloud API key needed.\n\n"
            "How to get and add one:\n"
            "1. Open the provider dashboard: OpenAI platform, Google AI Studio, Groq Console, Anthropic Console, DeepSeek Platform, NVIDIA Build, xAI Console, Kimi/Moonshot Platform, Mistral Console, OpenRouter, Together, Fireworks, Cerebras, Perplexity, or Hugging Face Tokens.\n"
            "2. Create an API key and copy it once.\n"
            "3. In JustHireMe, open Settings > Global AI.\n"
            "4. Select the same provider.\n"
            "5. Paste the key into that provider's key field.\n"
            "6. Pick a model chip or type the model id.\n"
            "7. Run the provider check. If it fails, check billing/credits, model name, key, and internet."
        )
    if topic == "sources":
        return _steps("How to add a source and scan:", [
            "Open Settings > Scraping & Discovery.",
            "Use quick add for Global preset, India preset, HN Hiring, RemoteOK, Remotive, Jobicy, or We Work Remotely.",
            "For a custom source, paste a company careers page, ATS board, RSS/API URL, or plain domain into Add source.",
            "Click Add source and review the Target job boards / search URLs textarea.",
            "Go to Dashboard and run a scan.",
            "Open Leads to review approved matches. Thin, stale, spammy, or senior-only rows are filtered by the quality gate.",
        ])
    if "link" in q or "url" in q:
        return _steps("How to add a job link:", [
            "For one job, open Customize and paste the job URL or full job description.",
            "Click Analyse & Generate / Generate Resume to create the tailored package.",
            "For recurring scraping, open Settings > Scraping & Discovery.",
            "Paste the site, ATS board, RSS/API URL, or domain into Add source.",
            "Click Add source, then run a scan from Dashboard.",
        ])
    if topic == "customize":
        return _steps("How to generate a resume and cover letter:", [
            "Open Profile/Add Context first and make sure your resume, skills, projects, and experience are present.",
            "Open Customize.",
            "Paste a job URL or the full job description.",
            "Click Analyse & Generate / Generate Resume.",
            "Review the generated resume PDF, cover letter PDF, and outreach drafts before sending.",
            "If quality is weak, add richer profile/project context and use a stronger Generator model in Settings.",
        ])
    if topic == "workflow":
        return _steps("Recommended first setup:", [
            "Open Settings > Global AI and configure a provider or Ollama.",
            "Open Profile/Add Context and add your resume, skills, projects, links, and notes.",
            "Open Settings > Scraping & Discovery and add source presets or custom sources.",
            "Run a scan from Dashboard.",
            "Review approved roles in Leads.",
            "Use Customize to generate a tailored resume, cover letter, and outreach drafts for a strong role.",
        ])
    return _steps("What JustHireMe helps with:", [
        "Dashboard runs scans and shows the workbench state.",
        "Settings configures LLM providers, API keys, models, and scraping sources.",
        "Profile/Add Context stores your local candidate data.",
        "Leads lets you review quality-gated job matches.",
        "Customize generates a tailored resume PDF, cover letter PDF, and outreach drafts.",
        "Job Pipeline tracks roles and follow-ups.",
    ])


def answer(question: str, history: list[dict] | None = None) -> dict:
    question = str(question or "").strip()
    provider, _key, model = resolve_config("help")
    if not question:
        return {"answer": "Ask me anything about using JustHireMe.", "provider": provider, "model": model}

    recent = []
    for item in (history or [])[-8:]:
        role = str(item.get("role") or "")[:20]
        content = str(item.get("content") or "")[:1000]
        if role and content:
            recent.append(f"{role}: {content}")

    topic = _topic(question)
    if topic in {"providers", "sources", "customize", "workflow"}:
        return {"answer": _fallback(question), "provider": provider, "model": model, "source": "guide"}

    system = (
        "You are JustHireMe's production in-app help assistant. Answer from the product knowledge below. "
        "Be concise, practical, and honest. If the user asks how to do something, give exact page names "
        "and numbered steps. Include prerequisite steps when needed, for example API key setup before AI generation. "
        "Do not invent unsupported features. Mention experimental automation as experimental. "
        "When relevant, remind the user that JustHireMe is local-first. "
        "Never ask the user to reveal private API keys, cookies, resumes, or local database files. "
        "Keep the answer under 12 short lines."
    )
    prompt = (
        f"Focused product knowledge:\n{_focused_knowledge(question)}\n\n"
        f"Recent chat:\n{chr(10).join(recent) or '(none)'}\n\n"
        f"User question: {question}"
    )

    try:
        response = call_raw(system, prompt, step="help").strip()
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/help/service.py:answer: %s', exc)
        response = ""
        provider = f"{provider} unavailable"
        model = str(exc)[:120]
    if not response:
        response = _fallback(question)
    return {"answer": response[:4000], "provider": provider, "model": model}
