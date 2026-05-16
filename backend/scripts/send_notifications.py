#!/usr/bin/env python3
"""
Notification sender cron script.

Reads pending notifications from the SQLite queue and sends them via:
- WhatsApp: writes to stdout for OpenClaw to pick up
- Email: sends directly via Gmail SMTP

Usage (from repo root or backend dir):
    python backend/scripts/send_notifications.py
    # or as a cron job every 5 minutes

Environment:
    JHM_APP_DATA_DIR — where the SQLite DB lives (default: ~/.local/share/JustHireMe)
"""
from __future__ import annotations

import os
import sys

# Ensure backend is on PYTHONPATH
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from data.sqlite import notifications as db
from notifications.email import send_email


def send_pending(limit: int = 20) -> dict:
    """Process pending notifications from the queue."""
    pending = db.get_pending_notifications(limit=limit)
    sent = 0
    failed = 0
    skipped = 0

    for item in pending:
        channel = item["channel"]
        nid = item["id"]

        if channel == "email":
            ok = send_email(
                to=item["recipient"],
                subject=item["subject"] or "[JustHireMe] Notification",
                body=item["message"],
                html=True,
            )
            if ok:
                db.mark_sent(nid)
                sent += 1
            else:
                db.mark_failed(nid, "SMTP send failed")
                failed += 1

        elif channel == "whatsapp":
            # Write to a consumable file for OpenClaw heartbeat
            queue_dir = os.path.join(
                os.environ.get("JHM_APP_DATA_DIR") or os.path.expanduser("~/.local/share/JustHireMe"),
                "notifications",
            )
            os.makedirs(queue_dir, exist_ok=True)
            queue_file = os.path.join(queue_dir, "whatsapp_pending.jsonl")
            import json

            with open(queue_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": nid,
                    "to": item["recipient"],
                    "message": item["message"],
                    "created_at": item["created_at"],
                }, ensure_ascii=False) + "\n")
            db.mark_sent(nid)
            sent += 1

        else:
            db.mark_failed(nid, f"Unknown channel: {channel}")
            skipped += 1

    return {"sent": sent, "failed": failed, "skipped": skipped, "processed": len(pending)}


def main() -> int:
    stats = send_pending()
    print(f"Processed {stats['processed']} notification(s): {stats['sent']} sent, {stats['failed']} failed, {stats['skipped']} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
