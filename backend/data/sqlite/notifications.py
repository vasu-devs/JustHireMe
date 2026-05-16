from __future__ import annotations

import json
from data.sqlite.connection import DEFAULT_DB_PATH, connect


def create_notifications_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            sent_at TEXT,
            error TEXT
        )
        """
    )


def queue_notification(
    channel: str,
    recipient: str,
    message: str,
    subject: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Queue a notification. Returns the queue id."""
    conn = connect(db_path)
    try:
        create_notifications_table(conn)
        cur = conn.execute(
            """
            INSERT INTO notifications_queue(channel, recipient, subject, message)
            VALUES(?, ?, ?, ?)
            """,
            (channel, recipient, subject, message),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_pending_notifications(
    channel: str | None = None,
    limit: int = 10,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Fetch unsent notifications, oldest first."""
    conn = connect(db_path)
    try:
        create_notifications_table(conn)
        if channel:
            rows = conn.execute(
                """
                SELECT id, channel, recipient, subject, message, created_at
                FROM notifications_queue
                WHERE sent_at IS NULL AND channel = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (channel, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, channel, recipient, subject, message, created_at
                FROM notifications_queue
                WHERE sent_at IS NULL
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row[0],
            "channel": row[1],
            "recipient": row[2],
            "subject": row[3] or "",
            "message": row[4],
            "created_at": row[5] or "",
        }
        for row in rows
    ]


def mark_sent(notification_id: int, db_path: str = DEFAULT_DB_PATH) -> None:
    from datetime import datetime, timezone

    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE notifications_queue SET sent_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), notification_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_failed(notification_id: int, error: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE notifications_queue SET error = ? WHERE id = ?",
            (str(error)[:500], notification_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_notification_stats(db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        create_notifications_table(conn)
        total = conn.execute("SELECT COUNT(*) FROM notifications_queue").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM notifications_queue WHERE sent_at IS NULL"
        ).fetchone()[0]
        sent = conn.execute(
            "SELECT COUNT(*) FROM notifications_queue WHERE sent_at IS NOT NULL AND error IS NULL"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM notifications_queue WHERE error IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "pending": pending, "sent": sent, "failed": failed}
