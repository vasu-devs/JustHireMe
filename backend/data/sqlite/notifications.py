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


def get_all_notifications(
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH,
) -> tuple[list[dict], int]:
    """Fetch notifications with optional status filter and pagination. Returns (items, total)."""
    conn = connect(db_path)
    try:
        create_notifications_table(conn)
        # Determine status filter
        if status == "pending":
            where_clause = "WHERE sent_at IS NULL AND error IS NULL"
        elif status == "sent":
            where_clause = "WHERE sent_at IS NOT NULL AND error IS NULL"
        elif status == "failed":
            where_clause = "WHERE error IS NOT NULL"
        else:
            where_clause = ""

        # Total count
        total_sql = f"SELECT COUNT(*) FROM notifications_queue {where_clause}"
        total = conn.execute(total_sql).fetchone()[0]

        # Items
        sql = f"""
            SELECT id, channel, recipient, subject, message, created_at, sent_at, error
            FROM notifications_queue
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, (max(1, limit), max(0, offset))).fetchall()
    finally:
        conn.close()

    items = [
        {
            "id": row[0],
            "channel": row[1],
            "recipient": row[2],
            "subject": row[3] or "",
            "message": row[4][:200] + "..." if len(row[4]) > 200 else row[4],
            "created_at": row[5] or "",
            "sent_at": row[6] or None,
            "error": row[7] or None,
        }
        for row in rows
    ]
    return items, total


def reset_notification(notification_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Reset a failed notification so it can be retried."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE notifications_queue SET sent_at = NULL, error = NULL WHERE id = ? AND error IS NOT NULL",
            (notification_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

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
