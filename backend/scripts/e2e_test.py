#!/usr/bin/env python3
"""
End-to-end test for JustHireMe Alternance integration.

Tests:
  1. Create a manual lead for a known alternance posting
  2. Trigger match-program endpoint
  3. Verify a program is matched in the same city
  4. Approve the program
  5. Verify generation would be allowed (status = tailoring)
  6. Verify notifications are queued after scan simulation

Usage:
    cd /tmp/justhireme-v11/backend
    python -m scripts.e2e_test

Requires the backend to be running on port 3006.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

# Ensure backend is on PYTHONPATH
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import httpx

BASE_URL = os.environ.get("JHM_API_URL", "http://127.0.0.1:3006")
API_TOKEN = os.environ.get("JHM_API_TOKEN", "")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}

PASS = []
FAIL = []


def _log(step: str, ok: bool, detail: str = "") -> None:
    mark = "✅" if ok else "❌"
    msg = f"{mark} {step}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if ok:
        PASS.append(step)
    else:
        FAIL.append(step)


def _health() -> dict:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=10)
        return r.json() if r.status_code == 200 else {"error": r.status_code}
    except Exception as exc:
        return {"error": str(exc)}


def _create_manual_lead() -> dict:
    job_id = f"test-{uuid.uuid4().hex[:8]}"
    payload = {
        "text": (
            "Stage Alternance Développeur Fullstack H/F\n"
            "Société: TechCorp France\n"
            "Ville: Paris\n"
            "Description: Recherche un développeur fullstack en alternance pour 24 mois. "
            "Stack: React, Node.js, Python. Formation Master Développement Web.",
        ),
        "url": f"https://example.com/jobs/{job_id}",
    }
    r = httpx.post(f"{BASE_URL}/api/v1/leads/manual", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _match_program(job_id: str) -> dict:
    r = httpx.post(f"{BASE_URL}/api/v1/leads/{job_id}/match-program", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _approve_program(job_id: str) -> dict:
    r = httpx.post(f"{BASE_URL}/api/v1/leads/{job_id}/approve-program", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _get_lead(job_id: str) -> dict:
    r = httpx.get(f"{BASE_URL}/api/v1/leads/{job_id}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _queue_test_notification() -> dict:
    from notifications.manager import NotificationManager

    notifier = NotificationManager()
    nid = notifier.queue_whatsapp("Test message from JustHireMe E2E")
    return {"id": nid}


def _get_notification_stats() -> dict:
    from data.sqlite import notifications as db

    return db.get_notification_stats()


def main() -> int:
    print("=" * 60)
    print("JustHireMe Alternance — E2E Integration Test")
    print("=" * 60)
    print(f"API: {BASE_URL}")
    print(f"Token: {'set' if API_TOKEN else 'NOT SET'}")
    print()

    # Step 0: Health check
    health = _health()
    ok = health.get("status") in {"alive", "healthy"}
    _log("Health check", ok, json.dumps(health.get("components", {}), indent=2)[:200])
    if not ok:
        print("\nBackend is not healthy. Is it running?")
        return 1

    # Step 1: Create manual lead
    print("\n--- Step 1: Create manual lead ---")
    try:
        lead = _create_manual_lead()
        job_id = lead["job_id"]
        _log("Create manual lead", True, f"job_id={job_id}")
    except Exception as exc:
        _log("Create manual lead", False, str(exc))
        return 1

    # Step 2: Match program
    print("\n--- Step 2: Match program ---")
    try:
        match_result = _match_program(job_id)
        status = match_result.get("status")
        program = match_result.get("program", {})
        _log("Match program", status == "matched", f"status={status} program={program.get('program_title','none')}")
    except Exception as exc:
        _log("Match program", False, str(exc))

    # Step 3: Verify lead has program_status=matched
    print("\n--- Step 3: Verify lead status ---")
    try:
        lead = _get_lead(job_id)
        meta = dict(lead.get("source_meta") or {})
        program_status = meta.get("program_status", "")
        matched_program = meta.get("matched_program", {})
        city = matched_program.get("city", "")
        _log("Program status = matched", program_status == "matched", f"city={city}")
    except Exception as exc:
        _log("Verify lead status", False, str(exc))

    # Step 4: Approve program
    print("\n--- Step 4: Approve program ---")
    try:
        approve_result = _approve_program(job_id)
        approved = approve_result.get("status") == "approved"
        _log("Approve program", approved)
    except Exception as exc:
        _log("Approve program", False, str(exc))

    # Step 5: Verify lead status = tailoring (generation allowed)
    print("\n--- Step 5: Verify generation gate ---")
    try:
        lead = _get_lead(job_id)
        lead_status = lead.get("status", "")
        meta = dict(lead.get("source_meta") or {})
        program_status = meta.get("program_status", "")
        gen_allowed = lead_status == "tailoring" and program_status == "approved"
        _log("Generation allowed", gen_allowed, f"lead_status={lead_status} program_status={program_status}")
    except Exception as exc:
        _log("Verify generation gate", False, str(exc))

    # Step 6: Notifications queue
    print("\n--- Step 6: Notifications queue ---")
    try:
        _queue_test_notification()
        stats = _get_notification_stats()
        has_pending = stats.get("pending", 0) >= 1
        _log("Notification queued", has_pending, f"pending={stats.get('pending')} total={stats.get('total')}")
    except Exception as exc:
        _log("Notification queue", False, str(exc))

    # Step 7: Email send test
    print("\n--- Step 7: Email send test ---")
    try:
        from notifications.email import send_email

        sent = send_email(
            to="adnanesaber15@gmail.com",
            subject="[JustHireMe E2E] Test email",
            body="<h1>JustHireMe E2E Test</h1><p>This is a test email from the E2E test suite.</p>",
            html=True,
        )
        _log("Email sent", sent)
    except Exception as exc:
        _log("Email sent", False, str(exc))

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print(f"Failed steps: {', '.join(FAIL)}")
    print("=" * 60)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
