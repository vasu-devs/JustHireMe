from __future__ import annotations

from data.sqlite import notifications as db

DEFAULT_PHONE = "+212696879642"


def queue_whatsapp(phone: str, message: str, db_path: str | None = None) -> int:
    """Queue a WhatsApp message in the notifications table.

    The actual sending is done by an external consumer (OpenClaw heartbeat)
    that reads the queue and calls openclaw message send.
    """
    kwargs = {"channel": "whatsapp", "recipient": phone, "message": message}
    if db_path:
        kwargs["db_path"] = db_path
    return db.queue_notification(**kwargs)


def format_scan_message(new_leads: list[dict], date_str: str | None = None) -> str:
    """Format a scan-update message in French."""
    from datetime import datetime, timezone

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"Alternance Update — {date_str}", "", f"Nouveaux leads trouvés : {len(new_leads)}", ""]
    for lead in new_leads[:5]:
        title = lead.get("title", "N/A")
        company = lead.get("company", "N/A")
        location = lead.get("location", "")
        meta = dict(lead.get("source_meta") or {})
        program = meta.get("matched_program", {})
        line = f"• {company} — {title}"
        if location:
            line += f" ({location})"
        if program.get("program_title") and program.get("university"):
            line += f"\n  Programme : {program['program_title']} @ {program['university']}"
        lines.append(line)
    if len(new_leads) > 5:
        lines.append(f"… et {len(new_leads) - 5} de plus")
    lines.append("")
    lines.append("→ Approuvez sur : https://alternance.qwik.ma/dashboard")
    return "\n".join(lines)
