from __future__ import annotations

from data.sqlite import notifications as db
from notifications.email import send_email
from notifications.whatsapp import queue_whatsapp

DEFAULT_PHONE = "+212696879642"
DEFAULT_EMAIL = "adnanesaber15@gmail.com"
DASHBOARD_URL = "https://alternance.qwik.ma/dashboard"


class NotificationManager:
    """Queue-based notification manager for JustHireMe.

    Notifications are written to the SQLite queue table.
    An external consumer (OpenClaw heartbeat or cron) picks them up and sends them.
    """

    def __init__(
        self,
        phone: str = DEFAULT_PHONE,
        email: str = DEFAULT_EMAIL,
        db_path: str | None = None,
    ):
        self.phone = phone
        self.email = email
        self.db_path = db_path

    # --- WhatsApp ---

    def queue_whatsapp(self, message: str) -> int:
        """Queue a WhatsApp message for the default phone."""
        kwargs = {"channel": "whatsapp", "recipient": self.phone, "message": message}
        if self.db_path:
            kwargs["db_path"] = self.db_path
        return db.queue_notification(**kwargs)

    def queue_scan_notification(self, new_leads: list[dict]) -> int | None:
        """Queue a notification about new leads found during a scan."""
        if not new_leads:
            return None
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [f"Alternance Update — {date_str}", f"", f"Nouveaux leads trouvés : {len(new_leads)}", ""]
        for lead in new_leads[:5]:
            title = lead.get("title", "N/A")
            company = lead.get("company", "N/A")
            location = lead.get("location", "")
            meta = dict(lead.get("source_meta") or {})
            program = meta.get("matched_program", {})
            program_title = program.get("program_title", "")
            university = program.get("university", "")
            line = f"• {company} — {title}"
            if location:
                line += f" ({location})"
            if program_title and university:
                line += f"\n  Programme : {program_title} @ {university}"
            lines.append(line)
        if len(new_leads) > 5:
            lines.append(f"… et {len(new_leads) - 5} de plus")
        lines.append("")
        lines.append(f"→ Approuvez sur : {DASHBOARD_URL}")
        return self.queue_whatsapp("\n".join(lines))

    def queue_generation_notification(self, lead: dict) -> int | None:
        """Queue a notification after generation completes with PDF links."""
        if not lead:
            return None
        title = lead.get("title", "N/A")
        company = lead.get("company", "N/A")
        job_id = lead.get("job_id", "")
        resume = lead.get("resume_asset") or lead.get("asset") or ""
        cover = lead.get("cover_letter_asset") or ""

        lines = [
            f"📄 Package généré — {title} @ {company}",
            "",
        ]
        if resume:
            lines.append(f"CV : {resume}")
        if cover:
            lines.append(f"Lettre : {cover}")
        lines.append("")
        lines.append(f"→ Dashboard : {DASHBOARD_URL}")
        if job_id:
            lines.append(f"→ Lead ID : {job_id}")
        return self.queue_whatsapp("\n".join(lines))

    # --- Email ---

    def queue_email(self, subject: str, body: str) -> int:
        """Queue an email notification."""
        kwargs = {
            "channel": "email",
            "recipient": self.email,
            "subject": subject,
            "message": body,
        }
        if self.db_path:
            kwargs["db_path"] = self.db_path
        return db.queue_notification(**kwargs)

    def queue_scan_email(self, new_leads: list[dict]) -> int | None:
        """Queue an email about new leads found during a scan."""
        if not new_leads:
            return None
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subject = f"[JustHireMe] {len(new_leads)} nouveaux leads alternance — {date_str}"
        lines = [f"<h2>Alternance Update — {date_str}</h2>", f"<p><b>{len(new_leads)} nouveaux leads trouvés</b></p>", "<ul>"]
        for lead in new_leads[:10]:
            title = lead.get("title", "N/A")
            company = lead.get("company", "N/A")
            location = lead.get("location", "")
            url = lead.get("url", "")
            meta = dict(lead.get("source_meta") or {})
            program = meta.get("matched_program", {})
            li = f"<li><b>{company}</b> — {title}"
            if location:
                li += f" ({location})"
            if program.get("program_title") and program.get("university"):
                li += f"<br>Programme : {program['program_title']} @ {program['university']}"
            if url:
                li += f'<br><a href="{url}">Voir l\'offre</a>'
            li += "</li>"
            lines.append(li)
        lines.append("</ul>")
        if len(new_leads) > 10:
            lines.append(f"<p>… et {len(new_leads) - 10} de plus.</p>")
        lines.append(f'<p><a href="{DASHBOARD_URL}">Approuver sur le dashboard →</a></p>')
        return self.queue_email(subject, "\n".join(lines))

    def queue_generation_email(self, lead: dict) -> int | None:
        """Queue an email after generation completes."""
        if not lead:
            return None
        title = lead.get("title", "N/A")
        company = lead.get("company", "N/A")
        job_id = lead.get("job_id", "")
        resume = lead.get("resume_asset") or lead.get("asset") or ""
        cover = lead.get("cover_letter_asset") or ""
        subject = f"[JustHireMe] Package généré — {title} @ {company}"
        lines = [
            f"<h2>📄 Package d'application généré</h2>",
            f"<p><b>{title}</b> @ <b>{company}</b></p>",
        ]
        if resume:
            lines.append(f'<p>CV : <a href="file://{resume}">{resume}</a></p>')
        if cover:
            lines.append(f'<p>Lettre de motivation : <a href="file://{cover}">{cover}</a></p>')
        lines.append(f'<p><a href="{DASHBOARD_URL}">Ouvrir le dashboard →</a></p>')
        if job_id:
            lines.append(f"<p>Lead ID : {job_id}</p>")
        return self.queue_email(subject, "\n".join(lines))

    # --- Direct send (for immediate delivery from backend) ---

    def send_email_now(self, subject: str, body: str, attachments: list[str] | None = None) -> bool:
        """Send email immediately via Gmail SMTP."""
        return send_email(self.email, subject, body, attachments)

    # --- Stats ---

    def get_stats(self) -> dict:
        return db.get_notification_stats(self.db_path) if self.db_path else db.get_notification_stats()
