from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# Gmail credentials for adnanesaber15@gmail.com
GMAIL_EMAIL = "adnanesaber15@gmail.com"
GMAIL_APP_PASSWORD = "uuejarzqqzfxbxza"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
    html: bool = True,
) -> bool:
    """Send email via Gmail SMTP using app password.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (HTML if html=True, plain text otherwise)
        attachments: List of file paths to attach
        html: Whether body is HTML

    Returns:
        True if sent successfully, False otherwise
    """
    msg = MIMEMultipart()
    msg["From"] = GMAIL_EMAIL
    msg["To"] = to
    msg["Subject"] = subject

    mime_type = "html" if html else "plain"
    msg.attach(MIMEText(body, mime_type))

    attachments = attachments or []
    for filepath in attachments:
        if not filepath or not __import__("os").path.exists(filepath):
            continue
        try:
            with open(filepath, "rb") as f:
                subtype = filepath.split(".")[-1].lower() if "." in filepath else "octet-stream"
                attach = MIMEApplication(f.read(), _subtype=subtype)
                attach.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=__import__("os").path.basename(filepath),
                )
                msg.attach(attach)
        except Exception:
            pass

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        return False
