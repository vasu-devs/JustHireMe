import logging
import re
from urllib.parse import urlparse
from core.logging import get_logger

_log = get_logger(__name__)


POSITIVE_LABELS = {
    "good": 1.0,
    "relevant": 1.0,
    "already_contacted": 0.7,
}

NEGATIVE_LABELS = {
    "trash": -1.0,
    "not_relevant": -1.0,
    "low_quality": -0.9,
    "incorrect_category": -1.0,
    "too_generic": -0.8,
    "not_ai": -1.1,
    "duplicate": -0.45,
}

FEATURE_WEIGHTS = {
    "platform": 6.0,
    "source": 5.0,
    "ats": 5.0,
    "kind": 4.0,
    "company": 4.0,
    "stack": 5.0,
    "tag": 3.0,
    "location": 2.0,
    "budget": 2.0,
    "urgency": 2.0,
}


def _norm(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return value[:80]


def _list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _company_key(lead: dict) -> str:
    company = _norm(lead.get("company", ""))
    if company:
        return company.lstrip("@")
    url = str(lead.get("url") or "")
    try:
        host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/feedback_ranker.py:_company_key: %s', log_exc)
        host = ""
    return host.replace("www.", "").split(".")[0]


def lead_features(lead: dict) -> set[str]:
    meta: dict = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    features: set[str] = set()

    platform = _norm(lead.get("platform", ""))
    if platform:
        features.add(f"platform:{platform}")
    kind = _norm(lead.get("kind", ""))
    if kind:
        features.add(f"kind:{kind}")
    company = _company_key(lead)
    if company:
        features.add(f"company:{company}")
    for key in ("source", "ats"):
        value = _norm(meta.get(key, ""))
        if value:
            features.add(f"{key}:{value}")

    for tag in _list(lead.get("signal_tags")):
        tag = _norm(tag)
        if tag:
            features.add(f"tag:{tag}")
    for stack in _list(lead.get("tech_stack") or meta.get("tech_stack")):
        stack = _norm(stack)
        if stack:
            features.add(f"stack:{stack}")

    location = _norm(lead.get("location") or meta.get("location"))
    if location:
        features.add(f"location:{location}")
    if lead.get("budget"):
        features.add("budget:present")
    if lead.get("urgency") or meta.get("urgency"):
        features.add("urgency:present")
    return features


def _label_weight(label: str) -> float:
    label = _norm(label)
    if label in POSITIVE_LABELS:
        return POSITIVE_LABELS[label]
    return NEGATIVE_LABELS.get(label, 0.0)


def build_model(examples: list[dict]) -> dict[str, dict]:
    model: dict[str, dict] = {}
    for lead in examples:
        weight = _label_weight(str(lead.get("feedback", "")))
        if not weight:
            continue
        for feature in lead_features(lead):
            row = model.setdefault(feature, {"sum": 0.0, "count": 0})
            row["sum"] += weight
            row["count"] += 1
    return model


def _feature_weight(feature: str) -> float:
    prefix = feature.split(":", 1)[0]
    return FEATURE_WEIGHTS.get(prefix, 2.0)


def apply_feedback_learning(lead: dict, examples: list[dict], max_delta: int = 18) -> dict:
    out = dict(lead)
    base = int(out.get("signal_score") or 0)
    out.setdefault("base_signal_score", base)

    model = build_model(examples)
    if not model:
        out["learning_delta"] = 0
        out["learning_reason"] = ""
        return out

    contributions: list[tuple[str, float]] = []
    for feature in lead_features(out):
        learned = model.get(feature)
        if not learned:
            continue
        confidence = min(int(learned["count"]), 5) / 5
        avg = float(learned["sum"]) / max(1, int(learned["count"]))
        contribution = avg * confidence * _feature_weight(feature)
        if abs(contribution) >= 0.35:
            contributions.append((feature, contribution))

    if not contributions:
        out["learning_delta"] = 0
        out["learning_reason"] = ""
        return out

    raw_delta = sum(value for _, value in contributions)
    delta = max(-max_delta, min(max_delta, round(raw_delta)))
    out["learning_delta"] = delta
    out["signal_score"] = max(0, min(100, base + delta))

    top = sorted(contributions, key=lambda item: abs(item[1]), reverse=True)[:3]
    pretty = []
    for feature, value in top:
        label = feature.replace(":", " ")
        pretty.append(f"{label} {'+' if value > 0 else ''}{round(value, 1)}")
    direction = "boost" if delta > 0 else "penalty"
    out["learning_reason"] = f"Feedback {direction}: " + ", ".join(pretty)
    reason = str(out.get("signal_reason") or "").strip()
    if delta:
        suffix = f"feedback learning {'+' if delta > 0 else ''}{delta}"
        out["signal_reason"] = f"{reason}; {suffix}" if reason else suffix

    meta = dict(out.get("source_meta") or {})
    meta["learning"] = {
        "base_signal_score": base,
        "delta": delta,
        "reason": out["learning_reason"],
    }
    out["source_meta"] = meta
    return out


class FeedbackRanker:
    def apply(self, lead: dict, examples: list[dict], max_delta: int = 18) -> dict:
        return apply_feedback_learning(lead, examples, max_delta=max_delta)
