from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from data.sqlite.connection import DEFAULT_DB_PATH, get_connection, init_sql


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reserve_request(
    provider: str,
    *,
    run_id: str,
    target_id: str,
    daily_request_cap: int,
    monthly_request_cap: int,
    estimated_cost_usd: float = 0.0,
    daily_spend_cap_usd: float = 0.0,
    monthly_spend_cap_usd: float = 0.0,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    """Atomically reserve one paid call or return the cap that rejected it.

    Reserved and completed calls both consume allowance. This is deliberate:
    an app crash after the provider receives a request must not make that call
    disappear from local spend governance.
    """
    provider = str(provider or "").strip().lower()
    if not provider:
        raise ValueError("provider is required")
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        usage = conn.execute(
            """
            SELECT
              COUNT(CASE WHEN date(occurred_at)=date('now') THEN 1 END) AS requests_today,
              COUNT(CASE WHEN strftime('%Y-%m',occurred_at)=strftime('%Y-%m','now') THEN 1 END) AS requests_month,
              COALESCE(SUM(CASE WHEN date(occurred_at)=date('now') THEN estimated_cost_usd ELSE 0 END),0) AS spend_today,
              COALESCE(SUM(CASE WHEN strftime('%Y-%m',occurred_at)=strftime('%Y-%m','now') THEN estimated_cost_usd ELSE 0 END),0) AS spend_month
            FROM paid_provider_requests WHERE provider=?
            """,
            (provider,),
        ).fetchone()
        today = int(usage["requests_today"] or 0)
        month = int(usage["requests_month"] or 0)
        spend_today = float(usage["spend_today"] or 0.0)
        spend_month = float(usage["spend_month"] or 0.0)
        reason = ""
        if today >= max(0, int(daily_request_cap)):
            reason = "daily_request_cap"
        elif month >= max(0, int(monthly_request_cap)):
            reason = "monthly_request_cap"
        elif daily_spend_cap_usd > 0 and spend_today + estimated_cost_usd > daily_spend_cap_usd + 1e-9:
            reason = "daily_spend_cap"
        elif monthly_spend_cap_usd > 0 and spend_month + estimated_cost_usd > monthly_spend_cap_usd + 1e-9:
            reason = "monthly_spend_cap"
        if reason:
            conn.rollback()
            return {
                "allowed": False,
                "reason": reason,
                "requests_today": today,
                "requests_month": month,
                "estimated_spend_today_usd": round(spend_today, 6),
                "estimated_spend_month_usd": round(spend_month, 6),
            }
        request_id = f"paidreq_{uuid4().hex}"
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO paid_provider_requests(
              request_id,provider,run_id,target_id,status,estimated_cost_usd,occurred_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (request_id, provider, run_id, target_id, "reserved", max(0.0, estimated_cost_usd), now),
        )
        conn.commit()
        return {
            "allowed": True,
            "request_id": request_id,
            "requests_today": today + 1,
            "requests_month": month + 1,
            "estimated_spend_today_usd": round(spend_today + max(0.0, estimated_cost_usd), 6),
            "estimated_spend_month_usd": round(spend_month + max(0.0, estimated_cost_usd), 6),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def finish_request(
    request_id: str,
    *,
    status: str,
    response_rows: int = 0,
    error_type: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE paid_provider_requests
            SET status=?,response_rows=?,error_type=?,completed_at=?,updated_at=datetime('now')
            WHERE request_id=?
            """,
            (status, max(0, int(response_rows)), str(error_type or "")[:200], _utc_now(), request_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_scan_yield(
    run_id: str,
    candidate_id: str,
    provider_yield: dict[str, dict],
    *,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        for provider, values in provider_yield.items():
            conn.execute(
                """
                INSERT INTO paid_provider_scan_yield(
                  run_id,candidate_id,provider,source_records,canonical_opportunities,
                  new_canonical_opportunities,eligible_opportunities,net_new_eligible_opportunities
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id,candidate_id,provider) DO UPDATE SET
                  source_records=excluded.source_records,
                  canonical_opportunities=excluded.canonical_opportunities,
                  new_canonical_opportunities=excluded.new_canonical_opportunities,
                  eligible_opportunities=excluded.eligible_opportunities,
                  net_new_eligible_opportunities=excluded.net_new_eligible_opportunities,
                  updated_at=datetime('now')
                """,
                (
                    run_id, candidate_id, provider,
                    int(values.get("source_records") or 0),
                    int(values.get("canonical_opportunities") or 0),
                    int(values.get("new_canonical_opportunities") or 0),
                    int(values.get("eligible_opportunities") or 0),
                    int(values.get("net_new_eligible_opportunities") or 0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def provider_usage(provider: str, *, db_path: str = DEFAULT_DB_PATH) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        usage = conn.execute(
            """
            SELECT
              COUNT(CASE WHEN date(occurred_at)=date('now') THEN 1 END) AS requests_today,
              COUNT(CASE WHEN strftime('%Y-%m',occurred_at)=strftime('%Y-%m','now') THEN 1 END) AS requests_month,
              COALESCE(SUM(CASE WHEN date(occurred_at)=date('now') THEN estimated_cost_usd ELSE 0 END),0) AS spend_today,
              COALESCE(SUM(CASE WHEN strftime('%Y-%m',occurred_at)=strftime('%Y-%m','now') THEN estimated_cost_usd ELSE 0 END),0) AS spend_month,
              COALESCE(SUM(response_rows),0) AS response_rows,
              COUNT(CASE WHEN status='success' THEN 1 END) AS successful_requests,
              COUNT(CASE WHEN status='failure' THEN 1 END) AS failed_requests
            FROM paid_provider_requests WHERE provider=?
            """,
            (provider,),
        ).fetchone()
        yield_row = conn.execute(
            """
            SELECT
              COALESCE(SUM(source_records),0) AS source_records,
              COALESCE(SUM(canonical_opportunities),0) AS canonical_opportunities,
              COALESCE(SUM(new_canonical_opportunities),0) AS new_canonical_opportunities,
              COALESCE(SUM(eligible_opportunities),0) AS eligible_opportunities,
              COALESCE(SUM(net_new_eligible_opportunities),0) AS net_new_eligible_opportunities
            FROM paid_provider_scan_yield WHERE provider=?
            """,
            (provider,),
        ).fetchone()
    finally:
        conn.close()
    eligible = int(yield_row["eligible_opportunities"] or 0)
    net_new = int(yield_row["net_new_eligible_opportunities"] or 0)
    return {
        "requests_today": int(usage["requests_today"] or 0),
        "requests_month": int(usage["requests_month"] or 0),
        "estimated_spend_today_usd": round(float(usage["spend_today"] or 0.0), 6),
        "estimated_spend_month_usd": round(float(usage["spend_month"] or 0.0), 6),
        "response_rows": int(usage["response_rows"] or 0),
        "successful_requests": int(usage["successful_requests"] or 0),
        "failed_requests": int(usage["failed_requests"] or 0),
        "source_records": int(yield_row["source_records"] or 0),
        "canonical_opportunities": int(yield_row["canonical_opportunities"] or 0),
        "new_canonical_opportunities": int(yield_row["new_canonical_opportunities"] or 0),
        "eligible_opportunities": eligible,
        "net_new_eligible_opportunities": net_new,
        "net_new_eligible_yield_percent": round(100 * net_new / eligible, 2) if eligible else 0.0,
    }
