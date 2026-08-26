from pathlib import Path
import zipfile

from profile import ingestor


def test_document_reads_plain_text_resume(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text("name: Jane Doe\nsummary: Applied AI engineer", encoding="utf-8")

    assert "Jane Doe" in ingestor._document(str(resume))


def test_document_reads_markdown_resume(tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("# Jane Doe\n\nPython, FastAPI", encoding="utf-8")

    assert "FastAPI" in ingestor._document(str(resume))


def test_document_reads_docx_resume(tmp_path):
    resume = tmp_path / "resume.docx"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Jane Doe</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Applied AI engineer</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(resume, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    text = ingestor._document(str(resume))

    assert "Jane Doe" in text
    assert "Applied AI engineer" in text


def test_local_parser_extracts_normal_resume_without_llm():
    profile = ingestor._parse_local(
        """
Jane Doe
jane@example.test | https://github.com/jane-example

Summary
Applied AI engineer building FastAPI and React products.

Skills
Python, FastAPI, React, PostgreSQL, Docker

Experience
AI Engineer at Acme
- Built LangGraph workflows.

Projects
Hiring Agent - FastAPI, React, RAG job matching
"""
    )

    assert profile.n == "Jane Doe"
    assert any(skill.n == "Python" for skill in profile.skills)
    assert any(skill.n == "FastAPI" for skill in profile.skills)
    assert profile.exp
    assert profile.projects


def test_local_parser_does_not_store_contacts_as_summary():
    profile = ingestor._parse_local(
        """
Casey Example
casey@example.test | +1 555 010 0001
https://github.com/example-candidate/Vanta
https://github.com/example-candidate/SOMA

Skills
Python, FastAPI, React
"""
    )

    assert "Email:" not in profile.s
    assert "Phone:" not in profile.s
    assert "Links:" not in profile.s
    assert "github.com" not in profile.s


def test_local_parser_repairs_project_titles_and_certificates():
    profile = ingestor._parse_local(
        """
Casey Example

Skills
Python, FastAPI, React, Playwright

Projects
conditioning. - https://github.com/example-candidate/Vanta
- Deployed FastAPI backend on Hugging Face Spaces and Next.js frontend on Vercel.
APIs. - Playwright | https://github.com/example-candidate/Specula
- Built Chrome extension for Pinterest outfit segmentation with Python and FastAPI.

Certificates
Social Networks
Jan2025 - Apr 2025
NPTEL -- Certificate Link
"""
    )

    titles = [project.title for project in profile.projects]
    assert "Vanta" in titles
    assert "Specula" in titles
    assert "conditioning" not in {title.lower() for title in titles}
    assert "apis" not in {title.lower() for title in titles}
    assert profile.certifications == ["Social Networks - NPTEL Jan 2025 - Apr 2025"]


def test_resume_parser_stitches_pdf_project_headers_and_continuations():
    profile = ingestor._parse_resume_heuristic(
        """
Alex Example
Full Stack AI Engineer

Technical Skills
Languages: Python, TypeScript, JavaScript
Frontend: React, Next.js
Backend: FastAPI, Docker
Databases: PostgreSQL, MongoDB, SQLite
AI / LLM: Groq, LangChain, LangGraph
Voice & Realtime: LiveKit, Deepgram, SIP

Projects
BranchGPT (branchgpt.example.test) Next.js 16, TypeScript, Drizzle, Neon PG, Groq
Git-styled DAG Chat Interface for LLM Context Optimization
- Modeled conversations as a Directed Acyclic Graph.
- Implemented LLM-summarized merges via Llama 3.3 that retain insight without transcript bloat - merge logic filters shared
history, appending only new content.
V aani(GitHub) Python, FastAPI, LiveKit, Deepgram, Groq, SIP, Docker
Voice-Native Debt Collection Platform with Real-Time Risk Analysis
- Engineered two tuned personas dispatched by debtor archetype, with real-time interrup-
tion handling.
Odeon (GitHub) FastAPI, WebSockets, LangChain, Groq, React 19
Self-Improving Voice Agent Optimization Framework
- Built a measurable prompt-tuning loop.
Socratis (GitHub) Next.js 14, Python, LiveKit, Deepgram, Groq, MongoDB
Real-Time AI Technical Interviewer with Live Code Awareness
- Built post-interview forensic analysis: Big-O evaluation.

Education
B.T ech in Computer Science Engineering, Example University
CGPA: 8.59
"""
    )

    titles = [project.title for project in profile.projects]

    assert titles == ["BranchGPT", "Vaani", "Odeon", "Socratis"]
    assert "history, appending only new content" in profile.projects[0].impact
    assert "interruption handling" in profile.projects[1].impact
    assert all(title not in {"history, appending only new content", "tion handling"} for title in titles)
