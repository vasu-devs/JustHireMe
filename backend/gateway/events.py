from __future__ import annotations

from contracts.events import InternalEvent


def websocket_payload(event: InternalEvent) -> dict:
    if event.type == "LEAD_UPDATED" or event.event == "LEAD_UPDATED":
        return {"type": "LEAD_UPDATED", "data": event.data}
    if event.event == "HOT_X_LEAD":
        return {"type": "HOT_X_LEAD", "data": event.data}
    payload = {"type": event.type or "agent", "event": event.event}
    if event.job_id:
        payload["job_id"] = event.job_id
    if event.msg:
        payload["msg"] = event.msg
    if event.data:
        payload["data"] = event.data
    return payload
