from __future__ import annotations

import asyncio


def test_portfolio_ingestor_extracts_real_site_structure_without_llm(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://vasu.dev/",
            title="Vasu Devs | Full Stack Engineer",
            text="""
            Vasu Devs
            Full-stack engineer building AI products, local-first automation, and data workflows.
            I build production React, TypeScript, Python, FastAPI, PostgreSQL, Docker, LLM and RAG systems.
            Featured Projects
            JustHireMe
            Local-first AI job intelligence workbench with resume generation and graph ranking.
            BranchGPT
            Developer workflow agent with Next.js, React, OpenAI and PostgreSQL.
            Contact vasu@example.com
            """,
            links=[
                {"href": "https://github.com/vasu-devs/justhireme", "text": "GitHub"},
                {"href": "https://linkedin.com/in/vasu-devs", "text": "LinkedIn"},
            ],
        ),
        portfolio.PageSnapshot(
            url="https://vasu.dev/projects",
            title="Projects",
            text="""
            Selected Work
            JustHireMe
            Built a local-first desktop workbench using Tauri, React, FastAPI, Kuzu and LanceDB.
            BranchGPT
            Ships AI-assisted repository workflows with Next.js, TypeScript and OpenAI.
            """,
            links=[{"href": "https://github.com/vasu-devs/branchgpt", "text": "BranchGPT repo"}],
        ),
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://vasu.dev"))

    assert result["error"] is None
    assert result["candidate"]["name"] == "Vasu Devs"
    assert result["identity"]["email"] == "vasu@example.com"
    assert result["identity"]["linkedin_url"] == "https://linkedin.com/in/vasu-devs"
    assert any(skill["name"] == "FastAPI" for skill in result["skills"])
    assert any(skill["name"] == "RAG" for skill in result["skills"])
    assert any(project["title"] == "JustHireMe" for project in result["projects"])
    assert result["stats"]["pages_scanned"] == 2
    assert result["stats"]["llm_used"] is False


def test_portfolio_html_snapshot_extracts_links_and_text():
    import profile.portfolio_ingestor as portfolio

    snapshot = portfolio._snapshot_html(
        "https://example.com",
        """
        <html><head><title>Jane Doe</title><style>.x{}</style></head>
        <body>
          <nav><a href="/projects">Projects</a></nav>
          <h1>Jane Doe</h1>
          <p>React and FastAPI portfolio.</p>
          <a href="https://github.com/jane/app">Repo</a>
        </body></html>
        """,
    )

    assert snapshot.title == "Jane Doe"
    assert "React and FastAPI portfolio" in snapshot.text
    assert {"href": "https://example.com/projects", "text": "Projects"} in snapshot.links
    assert {"href": "https://github.com/jane/app", "text": "Repo"} in snapshot.links


def test_portfolio_ingestor_uses_http_fallback_when_browser_returns_no_pages(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    async def fake_browser(_url):
        return [], ""

    def fake_http(_url):
        return [
            portfolio.PageSnapshot(
                url="https://example.com/",
                title="Jane Doe",
                text="Jane Doe\nReact and FastAPI engineer.\nFeatured Projects\nOps Console\nBuilt a dashboard with PostgreSQL.",
                links=[],
            )
        ]

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_crawl_portfolio_http", fake_http)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://example.com"))

    assert result["error"] is None
    assert result["stats"]["pages_scanned"] == 1
    assert any(skill["name"] == "React" for skill in result["skills"])


def test_portfolio_ingestor_filters_noisy_projects(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://example.com/projects",
            title="Projects",
            text="""
            Selected Work
            Runtime Error
            undefined failed route loading
            Useful Analytics Console
            Built a React and FastAPI analytics dashboard with PostgreSQL automation for operators.
            """,
            links=[],
        )
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://example.com/projects"))

    titles = [project["title"] for project in result["projects"]]
    assert "Runtime Error" not in titles
    assert "Useful Analytics Console" in titles


def test_portfolio_ingestor_keeps_real_homepage_products(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://example.com/",
            title="Vasu Devs",
            text="""
            Vasu Devs
            AI Engineer building agentic products.
            Featured Projects
            JustHireMe
            Agentic AI desktop app for transparent, privacy-first job search built with Tauri, React, FastAPI, KuzuDB and LanceDB.
            Internal Finance & P&L Platform
            Built a financial planning system with Python, PostgreSQL, dashboards, automations and audit-ready workflows.
            Runtime Error
            undefined failed route loading
            Skills
            TypeScript React FastAPI PostgreSQL LanceDB KuzuDB
            """,
            links=[],
        )
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://example.com"))

    titles = [project["title"] for project in result["projects"]]
    skills = [skill["name"] for skill in result["skills"]]
    assert "JustHireMe" in titles
    assert "Internal Finance & P&L Platform" in titles
    assert "Runtime Error" not in titles
    assert "KuzuDB" in skills
    assert "LanceDB" in skills


def test_portfolio_ingestor_rejects_cta_and_section_labels(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://example.com/work",
            title="Work",
            text="""
            02 / Works
            Open →
            Show all 45 projects
            Available for remote projects worldwideBook a free call
            JustHireMe
            Built an agentic AI desktop app for transparent job search with Tauri, React, FastAPI and LanceDB.
            04 / Technical Expertise
            Frontend
            7 tools
            Next.jsReactViteTailwindFramer Motion
            06 / Services
            AI Agents & Automation
            Multi-agent pipelines, RAG systems, LangGraph workflows, and intelligent automation.
            """,
            links=[],
        )
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://example.com/work"))

    titles = [project["title"] for project in result["projects"]]
    assert "JustHireMe" in titles
    assert "Open →" not in titles
    assert "02 / Works" not in titles
    assert "Show all 45 projects" not in titles
    assert "Frontend" not in titles
    assert "AI Agents & Automation" not in titles


def test_portfolio_ingestor_keeps_real_products_from_dense_portfolio(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://example.com/",
            title="Vasu DevS",
            text="""
            VASU
            DEVS
            Vasu-DevS ExperienceSkillsServicesContact
            01 / Experience
            JustHireMe
            Agentic AI desktop app for transparent, privacy-first job search
            380.6K
            Launch views
            Internal Finance & P&L Platform
            Days, solo
            Integrations
            10×
            Tests
            Next.js 15TypeScriptPostgreSQLPrismaTailwindVercel
            02 / Selected Works
            01 // Context Optimization / AI
            BranchGPT
            A Git-like chat interface that treats conversations as a DAG for context garbage collection.
            02 // Voice AI / Fintech
            Vaani
            Voice-native debt collection platform powered by LiveKit, Groq, and Deepgram.
            04 / Technical Expertise
            Frontend
            7 tools
            Next.jsReactViteTailwindFramer Motion
            06 / Services
            AI Agents & Automation
            Multi-agent pipelines, RAG systems, LangGraph workflows, and intelligent automation.
            """,
            links=[],
        )
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://example.com"))

    titles = [project["title"] for project in result["projects"]]
    skills = [skill["name"] for skill in result["skills"]]
    assert "JustHireMe" in titles
    assert "BranchGPT" in titles
    assert "Vaani" in titles
    assert "VASU" not in titles
    assert "380.6K" not in titles
    assert "02 // Voice AI / Fintech" not in titles
    assert "Frontend" not in titles
    assert "AI Agents & Automation" not in titles
    assert "React" in skills
    assert "Vite" in skills
    assert "Prisma" in skills


def test_portfolio_ingestor_rejects_browser_nav_and_identity_as_projects(monkeypatch):
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="http://127.0.0.1:4321/",
            title="Jane Doe | Engineer",
            text="""
            Jane Doe
            ProjectsGitHub
            Full-stack engineer building React, TypeScript, FastAPI, PostgreSQL and RAG products.
            Featured Projects
            Ops Console
            Built a React and FastAPI analytics dashboard with PostgreSQL automations for operators.
            Contact jane@example.com
            """,
            links=[{"href": "https://github.com/jane/ops-console", "text": "GitHub"}],
        ),
        portfolio.PageSnapshot(
            url="http://127.0.0.1:4321/projects",
            title="Projects",
            text="""
            Selected Work
            Signal Graph
            Designed a local-first RAG graph interface using Python, FastAPI, React and LanceDB.
            """,
            links=[],
        ),
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("http://127.0.0.1:4321"))

    titles = [project["title"] for project in result["projects"]]
    assert "Ops Console" in titles
    assert "Signal Graph" in titles
    assert "Jane Doe" not in titles
    assert "ProjectsGitHub" not in titles
    assert "Contact jane@example.com" not in titles
