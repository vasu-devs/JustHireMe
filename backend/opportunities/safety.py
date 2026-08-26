from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PaidStatus(StrEnum):
    PAID = "paid"
    UNPAID = "unpaid"
    UNKNOWN = "unknown"
    SUSPICIOUS = "suspicious"


class SafetyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_status: PaidStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)


_UNPAID = re.compile(r"\b(unpaid|without (?:pay|compensation)|no stipend)\b", re.I)
_VOLUNTEER_ROLE = re.compile(
    r"\b(?:intern(?:ship)?|role|position)\b[^\n.;]{0,50}\bvolunteer(?:y|ism)?\b|"
    r"\bvolunteer(?:y|ism)?\b[^\n.;]{0,50}\b(?:intern(?:ship)?|role|position)\b",
    re.I,
)
_PAID = re.compile(r"\b(paid|stipend|salary|compensation of|hourly rate|per (?:month|annum|year))\b", re.I)
_CONDITIONAL_PAY = re.compile(
    r"\b(?:possibility|potential|chance)\s+(?:of\s+)?(?:a\s+)?(?:future\s+)?"
    r"(?:stipend|pay|compensation)\b|"
    r"\bperformance[- ]based\s+(?:stipend|pay|compensation)\b|"
    r"\b(?:stipend|pay|compensation)\s+based\s+on\s+(?:performance|contributions?)\b|"
    r"\b(?:stipend|pay|compensation)\b[^.\n]{0,50}\bbased\s+on\b"
    r"[^.\n]{0,30}\bperformance\b|"
    r"\b(?:stipend|pay|compensation)\b.{0,20}\b(?:may|might|could)\s+be\b",
    re.I,
)
_EXPLICIT_NUMERIC_PAY = re.compile(
    r"(?:₹|\$|€|£|\b(?:inr|usd|eur|gbp)\b)\s*\d|"
    r"\b(?:hourly|monthly|annual)\s+(?:rate|salary|compensation)\b.{0,25}\d|"
    r"\b\d[\d,.]*\s*(?:/\s*(?:hr|hour|month|year)|per\s+(?:hour|month|year)|lpa)\b",
    re.I,
)
_TRAINING_FEE = re.compile(r"\b(training|registration|application|onboarding)\b.{0,25}\b(fee|deposit)\b", re.I)
_SECURITY_DEPOSIT = re.compile(r"\b(security|refundable|equipment)\b.{0,20}\b(deposit|fee)\b", re.I)
_PAY_TO_APPLY = re.compile(
    r"\b(?:must|required to|first)\b.{0,20}\bpay\b|\bpay\s+(?:inr|rs\.?|₹|usd|\$)?\s*\d",
    re.I,
)
_SERVICE_BOND = re.compile(
    r"\b(service|employment)\s+bond\b|\bbond\s+(?:period|agreement)\b|"
    r"\bservice\s+lock(?:-|\s*)in(?:\s+period)?\b",
    re.I,
)
_EXIT_PENALTY = re.compile(r"\b(exit|leaving|early termination)\s+(?:penalty|fee|charge)\b", re.I)
_ORIGINAL_DOCUMENTS = re.compile(r"\b(original (?:degree|marksheet|certificate|passport|documents?))\b", re.I)
_EXPLICIT_TRAINING_AS_INTERNSHIP = re.compile(
    r"\btraining\s+phase\s+(?:itself\s+)?(?:will\s+be|is)\s+considered\s+as\s+an?\s+internship\b|"
    r"\b(?:internship\s+training|training\s+internship)\s+program\b|"
    r"\b(?:internship|training)\s+type\b[^.\n]{0,100}\bclassroom[- ]based\b|"
    r"\blecture\s*[–-]\s*tutorial\s*[–-]\s*practical\b",
    re.I,
)
_COURSE_LIKE_INTERNSHIP = re.compile(
    r"\bwhat\s+you\s+will\s+learn\b",
    re.I,
)
_INTERNSHIP_SIGNAL = re.compile(r"\bintern(?:ship)?s?\b", re.I)
_COURSE_PARTICIPANT = re.compile(
    r"\b(?:participants?|learners?|students?)\b[^.\n]{0,180}"
    r"\b(?:training|classroom|labs?|curriculum|tutorials?|skills?)\b|"
    r"\b(?:equips?|prepares?)\s+(?:participants?|learners?|students?)\b",
    re.I,
)
_EMPLOYMENT_EVIDENCE = re.compile(
    r"\b(?:key\s+)?responsibilities\b|\byou\s+will\s+be\s+responsible\b|"
    r"\bjoin\s+(?:our|the)\s+team\b|\bwe\s+are\s+(?:hiring|looking\s+for)\b|"
    r"\breport(?:s|ing)?\s+to\b|\bemployment\s+(?:offer|benefits?)\b",
    re.I,
)
_CONDITIONAL_COMPLETION_COMPENSATION = re.compile(
    r"\bcompletion\s+(?:benefit|bonus|payment|compensation)\b[^.\n]{0,180}"
    r"\b(?:upon|after|subject\s+to)\b[^.\n]{0,100}\b(?:completion|performance|attendance)\b|"
    r"\b(?:benefit|bonus|payment|compensation)\b[^.\n]{0,80}"
    r"\bpayable\s+(?:only\s+)?(?:upon|after)\s+(?:successful\s+)?completion\b",
    re.I,
)
_GUARANTEED_RECURRING_PAY = re.compile(
    r"\b(?:monthly|hourly|annual)\s+(?:stipend|salary|rate|compensation)\b[^.\n]{0,40}\d|"
    r"\b(?:stipend|salary|compensation)\b[^.\n]{0,40}(?:₹|\$|€|£|\binr\b|\busd\b)\s*\d|"
    r"(?:₹|\$|€|£|\binr\b|\busd\b)\s*\d[\d,.]*[^.\n]{0,20}"
    r"(?:/\s*(?:hr|hour|month|year)|per\s+(?:hour|month|year))\b",
    re.I,
)


def assess_safety(description: str, *, allow_unpaid: bool = False, allow_bond: bool = False) -> SafetyAssessment:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: dict[str, list[str]] = {}
    unpaid_signal = _UNPAID.search(description)
    volunteer_signal = _VOLUNTEER_ROLE.search(description)
    unpaid = bool(unpaid_signal or volunteer_signal)
    paid = bool(
        _PAID.search(description)
        and (
            not _CONDITIONAL_PAY.search(description)
            or _EXPLICIT_NUMERIC_PAY.search(description)
        )
    )
    fee = bool(_TRAINING_FEE.search(description) and _PAY_TO_APPLY.search(description))
    deposit = bool(_SECURITY_DEPOSIT.search(description))
    bond = bool(_SERVICE_BOND.search(description))
    exit_penalty = bool(_EXIT_PENALTY.search(description))
    training_as_internship = bool(
        _EXPLICIT_TRAINING_AS_INTERNSHIP.search(description)
        or (
            _COURSE_LIKE_INTERNSHIP.search(description)
            and (_INTERNSHIP_SIGNAL.search(description) or _COURSE_PARTICIPANT.search(description))
            and not (_EMPLOYMENT_EVIDENCE.search(description) or _EXPLICIT_NUMERIC_PAY.search(description))
        )
    )
    conditional_completion_compensation = bool(
        _INTERNSHIP_SIGNAL.search(description)
        and _CONDITIONAL_COMPLETION_COMPENSATION.search(description)
        and not _GUARANTEED_RECURRING_PAY.search(description)
    )

    if unpaid:
        (warnings if allow_unpaid else blockers).append("unpaid")
        evidence["unpaid"] = [
            "explicit_unpaid_signal" if unpaid_signal else "explicit_volunteer_role_signal"
        ]
    if fee:
        blockers.append("training_fee")
        evidence["training_fee"] = ["pay_to_apply_and_fee_signal"]
    if deposit:
        blockers.append("security_deposit")
        evidence["security_deposit"] = ["deposit_signal"]
    if bond:
        (warnings if allow_bond else blockers).append("service_bond")
        evidence["service_bond"] = ["bond_signal"]
    if exit_penalty:
        blockers.append("exit_penalty")
        evidence["exit_penalty"] = ["exit_penalty_signal"]
    if training_as_internship:
        blockers.append("training_presented_as_internship")
        evidence["training_presented_as_internship"] = [
            "course_or_classroom_program_without_employment_evidence"
        ]
    if conditional_completion_compensation:
        blockers.append("conditional_completion_compensation")
        evidence["conditional_completion_compensation"] = [
            "end_of-tenure_compensation_is_not_guaranteed_recurring_pay"
        ]
    if _ORIGINAL_DOCUMENTS.search(description):
        blockers.append("original_documents")
        evidence["original_documents"] = ["original_document_retention_signal"]

    if fee or deposit or training_as_internship or conditional_completion_compensation:
        paid_status = PaidStatus.SUSPICIOUS
    elif unpaid:
        paid_status = PaidStatus.UNPAID
    elif paid:
        paid_status = PaidStatus.PAID
    else:
        paid_status = PaidStatus.UNKNOWN
    return SafetyAssessment(
        paid_status=paid_status,
        blockers=list(dict.fromkeys(blockers)),
        warnings=list(dict.fromkeys(warnings)),
        evidence=evidence,
    )
