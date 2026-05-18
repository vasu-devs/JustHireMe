import sys
import time

G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
C = "\033[96m"
M = "\033[95m"
B = "\033[1m"
D = "\033[2m"
X = "\033[0m"

def log(tag, msg, color=G):
    ts = time.strftime("%H:%M:%S")
    # Replace any non-ASCII characters to prevent Windows console encoding issues
    msg = str(msg).encode('ascii', 'replace').decode('ascii')
    print(f"{D}{ts}{X} {color}{B}[{tag}]{X} {msg}")


def banner():
    print(f"""
{C}{B}+----------------------------------------------------------+
|         JustHireMe  .  Pipeline Diagnostics              |
+----------------------------------------------------------+{X}
""")


def check_settings():
    from data.repository import create_repository

    repo = create_repository()
    get_setting = repo.settings.get_setting
    get_settings = repo.settings.get_settings
    from discovery.targets import job_targets

    log("CONFIG", "Loading settings from SQLite...", C)
    cfg = get_settings()
    provider = cfg.get("llm_provider", "ollama")
    log("CONFIG", f"LLM Provider = {B}{provider}{X}", C)

    if provider == "nvidia":
        k = get_setting("nvidia_api_key")
        if not k:
            log("CONFIG", "nvidia_api_key is EMPTY — aborting", R)
            sys.exit(1)
        log("CONFIG", f"nvidia_api_key = {k[:12]}•••  ({len(k)} chars)", G)

    elif provider == "groq":
        k = get_setting("groq_api_key")
        if not k:
            log("CONFIG", "groq_api_key is EMPTY — aborting", R)
            sys.exit(1)
        log("CONFIG", f"groq_api_key = {k[:8]}•••  ({len(k)} chars)", G)

    elif provider == "anthropic":
        k = get_setting("anthropic_key")
        if not k:
            log("CONFIG", "anthropic_key is EMPTY — aborting", R)
            sys.exit(1)
        log("CONFIG", f"anthropic_key = {k[:10]}•••  ({len(k)} chars)", G)

    else:
        log("CONFIG", f"Provider '{provider}' uses local inference — no key needed", Y)

    boards = cfg.get("job_boards", "")
    if not boards.strip():
        target = "role-neutral default targets"
        log("CONFIG", f"No job boards configured - using {target}", Y)
        boards = ""

    urls = job_targets(boards, cfg.get("job_market_focus", "global"))
    log("CONFIG", f"Target boards: {len(urls)} configured", G)
    for u in urls:
        log("CONFIG", f"  → {u}", D)

    return cfg, urls


def run_scout(urls):
    from automation.scout import run as _scout

    log("SCOUT", f"Launching Playwright (headed) for {len(urls)} URLs...", M)
    http = [u for u in urls if u.startswith("http")]
    queries = [u for u in urls if not u.startswith("http")]

    t0 = time.time()
    leads = _scout(
        urls=http or None,
        queries=queries or None,
        headed=True,
    )
    dt = round(time.time() - t0, 1)

    log("SCOUT", f"Completed in {dt}s — {B}{len(leads)} new leads{X} discovered", G)
    for lead in leads:
        log("SCOUT", f"  → {lead.get('title','?')} @ {lead.get('company','?')}  [{lead.get('platform','')}]", C)
        log("SCOUT", f"    {D}{lead.get('url','')}{X}", D)

    return leads


def run_evaluator():
    from data.repository import create_repository
    from ranking.evaluator import score as _score

    repo = create_repository()
    get_discovered_leads = repo.leads.get_discovered_leads
    update_lead_score = repo.leads.update_lead_score
    get_setting = repo.settings.get_setting
    get_profile = repo.profile.get_profile

    discovered = get_discovered_leads()
    profile = get_profile()
    provider = get_setting("llm_provider", "ollama")
    log("EVALUATOR", f"{len(discovered)} leads pending evaluation", Y)
    log("EVALUATOR", f"Routing to {B}{provider.upper()}{X}", M)

    results = []
    for i, lead in enumerate(discovered, 1):
        jid = lead["job_id"]
        title = lead.get("title", "?")
        co = lead.get("company", "?")
        log("EVALUATOR", f"[{i}/{len(discovered)}] Scoring: {title} @ {co}", C)

        t0 = time.time()
        try:
            jd = f"{title} at {co} — {lead.get('url', '')}"
            r = _score(jd, profile)
            dt = round(time.time() - t0, 1)

            s = r["score"]
            color = G if s >= 85 else Y if s >= 60 else R
            log("EVALUATOR", f"  Score = {color}{B}{s}/100{X}  ({dt}s)", color)
            log("EVALUATOR", f"  Reason: {D}{r['reason'][:120]}{X}", D)

            update_lead_score(jid, s, r["reason"])
            results.append(r)

        except Exception as e:
            dt = round(time.time() - t0, 1)
            log("EVALUATOR", f"  FAILED ({dt}s): {e}", R)

    approved = [r for r in results if r.get("score", 0) >= 85]
    log("EVALUATOR", f"Done — {len(results)} scored, {B}{len(approved)} approved{X}", G)
    return results


def summary(leads, results):
    print(f"""
{C}{B}+----------------------------------------------------------+
|                    DIAGNOSTIC SUMMARY                    |
+----------------------------------------------------------+{X}

  {G}Scout{X}     : {len(leads)} leads discovered
  {Y}Evaluator{X} : {len(results)} leads scored
  {G}Approved{X}  : {len([r for r in results if r.get('score',0) >= 85])} leads (score >= 85)
  {R}Rejected{X}  : {len([r for r in results if r.get('score',0) < 85])} leads

  {D}All data written to SQLite — check the React UI.{X}
""")


if __name__ == "__main__":
    banner()

    log("BOOT", "Starting pipeline diagnostics...", C)
    cfg, urls = check_settings()

    print()
    leads = run_scout(urls)

    print()
    results = run_evaluator()

    print()
    summary(leads, results)
