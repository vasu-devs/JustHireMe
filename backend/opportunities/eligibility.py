from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.taxonomy import TECH_TAXONOMY
from opportunities.models import LiveStatus
from opportunities.safety import PaidStatus, assess_safety
from opportunities.taxonomy import (
    OpportunityClassification,
    OpportunityType,
    TechnicalTrack,
    WorkplaceScope,
    classify_opportunity,
)


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    NEEDS_REVIEW = "needs_review"
    INELIGIBLE = "ineligible"


class Decision(StrEnum):
    APPLY_NOW = "apply_now"
    STRONG_STRETCH = "strong_stretch"
    NEEDS_REVIEW = "needs_review"
    SKIP = "skip"


class DegreeLevel(StrEnum):
    UNKNOWN = "unknown"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    DOCTORATE = "doctorate"


class UnknownCompensationPolicy(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    SKIP = "skip"


OPPORTUNITY_RULE_VERSION = "36"


class CandidateConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = "pilot"
    consent_confirmed_at: datetime | None = None
    home_country: str = "IN"
    graduation_year: int = 2027
    currently_enrolled: bool = True
    current_degree_level: DegreeLevel = DegreeLevel.UNKNOWN
    accepted_india_cities: list[str] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list, max_length=100)
    project_keywords: list[str] = Field(default_factory=list, max_length=100)
    spoken_languages: list[str] = Field(default_factory=list, max_length=30)
    preferred_technical_tracks: list[TechnicalTrack] = Field(default_factory=list, max_length=12)
    accepted_opportunity_types: list[OpportunityType] = Field(
        default_factory=lambda: [
            OpportunityType.INTERNSHIP,
            OpportunityType.NEW_GRAD,
            OpportunityType.ENTRY_LEVEL_FULL_TIME,
            OpportunityType.STRETCH_FULL_TIME,
        ],
        min_length=1,
        max_length=4,
    )
    allow_india_onsite: bool = True
    allow_india_hybrid: bool = True
    allow_india_remote: bool = True
    allow_worldwide_remote: bool = True
    allow_unpaid: bool = False
    allow_bond: bool = False
    professional_experience_years: float = Field(default=0.0, ge=0.0)
    minimum_monthly_compensation_inr: int = Field(default=0, ge=0)
    target_monthly_compensation_inr: int = Field(default=0, ge=0)
    minimum_monthly_compensation_usd: int = Field(default=0, ge=0)
    target_monthly_compensation_usd: int = Field(default=0, ge=0)
    unknown_compensation_policy: UnknownCompensationPolicy = UnknownCompensationPolicy.ALLOW
    maximum_internship_months: int = Field(default=12, ge=1, le=36)
    auto_apply_enabled: bool = False
    auto_apply_confirmed_at: datetime | None = None
    auto_apply_minimum_fit_score: int = Field(default=80, ge=0, le=100)
    auto_apply_daily_limit: int = Field(default=5, ge=1, le=20)
    auto_apply_allow_strong_stretch: bool = False

    @model_validator(mode="after")
    def validate_auto_apply_consent(self) -> CandidateConstraints:
        if self.auto_apply_enabled and self.auto_apply_confirmed_at is None:
            raise ValueError("auto-apply requires explicit candidate confirmation")
        return self

    @model_validator(mode="after")
    def validate_compensation_targets(self) -> CandidateConstraints:
        pairs = (
            ("INR", self.minimum_monthly_compensation_inr, self.target_monthly_compensation_inr),
            ("USD", self.minimum_monthly_compensation_usd, self.target_monthly_compensation_usd),
        )
        for currency, minimum, target in pairs:
            if target and minimum and target < minimum:
                raise ValueError(f"{currency} target compensation must be at least the minimum")
        return self


class ApplicabilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: str = OPPORTUNITY_RULE_VERSION
    eligibility: EligibilityStatus
    decision: Decision
    live_status: LiveStatus
    opportunity_type: OpportunityType
    technical_track: TechnicalTrack
    workplace_scope: WorkplaceScope
    india_eligible: bool
    paid_status: PaidStatus
    hard_blockers: list[str] = Field(default_factory=list)
    safety_blockers: list[str] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    career_growth_score: int = Field(default=0, ge=0, le=100)
    hiring_confidence_score: int = Field(default=0, ge=0, le=100)
    priority_score: int = Field(default=0, ge=0, le=100)
    career_signals: list[str] = Field(default_factory=list)
    candidate_fit_score: int = Field(default=50, ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    posting_skills: list[str] = Field(default_factory=list)
    candidate_evidence_missing: bool = False
    posting_india_cities: list[str] = Field(default_factory=list)
    graduation_years: list[int] = Field(default_factory=list)
    monthly_compensation_inr: list[int] = Field(default_factory=list)
    monthly_compensation_usd: list[int] = Field(default_factory=list)
    compensation_score: int = Field(default=50, ge=0, le=100)
    target_compensation_met: bool | None = None
    internship_duration_months: list[int] = Field(default_factory=list)
    minimum_experience_years: int = Field(default=0, ge=0)
    requires_current_enrollment: bool = False
    work_authorization_restricted: bool = False
    required_language_groups: list[list[str]] = Field(default_factory=list)
    required_degree_level: DegreeLevel = DegreeLevel.UNKNOWN


_CLOSED = re.compile(r"\b(applications? (?:are )?closed|position (?:has been )?filled|no longer accepting)\b", re.I)
_EXPERIENCE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
_EXPERIENCE_RANGE = re.compile(
    r"\b(\d{1,2})\s*(?:[-–—]|to)\s*\d{1,2}\s*(?:years?|yrs?)\b",
    re.I,
)
_AUTHORIZATION = re.compile(
    r"\b(unrestricted|existing|already have|must have|must already have|require[sd]?)\b.{0,35}\bwork authorization\b",
    re.I,
)
_COUNTRY_RESTRICTION = re.compile(
    r"\b(must reside|must be based|located in|residents? of)\b.{0,45}\b(united states|u\.?s\.?|canada|"
    r"united kingdom|u\.?k\.?|european union|\beu\b)\b|"
    r"\b(united states|u\.?s\.?|canada|united kingdom|u\.?k\.?|european union|\beu\b)\s+only\b",
    re.I,
)
_GRADUATION_SIGNALS = (
    "graduate",
    "graduates",
    "graduating",
    "graduation",
    "class of",
    "batch",
)
_YEAR = re.compile(r"\b(20[2-4]\d)\b")
_ENROLLED = re.compile(r"\b(currently enrolled|must be enrolled|be enrolled|returning to (?:school|university))\b", re.I)
_EXTERNAL_PROGRAM_RESTRICTION = re.compile(
    r"\b(?:only open (?:to|for)|eligible only (?:to|for))\b.{0,100}"
    r"\b(?:candidates?|applicants?)\b.{0,100}\b(?:applied|registered|nominated)\b"
    r".{0,100}\b(?:scheme|program(?:me)?|portal)\b|"
    r"\bmust (?:first )?(?:apply|register) (?:through|under|via)\b.{0,100}"
    r"\b(?:scheme|program(?:me)?|portal)\b",
    re.I,
)
_MONTHLY_PAY_RANGE = re.compile(
    r"(?:₹|inr|rs\.?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lac|l)?\s*[-–—]\s*"
    r"(?:₹|inr|rs\.?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lac|l)?\s*"
    r"(?:₹|inr|rs\.?)?\s*(?:/|per\s*)?(?:month|monthly|pm)\b",
    re.I,
)
_MONTHLY_PAY = re.compile(
    r"(?:₹|inr|rs\.?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lac|l)?\s*"
    r"(?:₹|inr|rs\.?)?\s*(?:/|per\s*)?(?:month|monthly|pm)\b",
    re.I,
)
_ANNUAL_LAKH = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?\s+per\s+annum)\b", re.I)
_USD_MONTHLY_RANGE = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*[-–—]\s*"
    r"(?:\$|usd\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:month|monthly|pm)\b",
    re.I,
)
_USD_MONTHLY = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:month|monthly|pm)\b",
    re.I,
)
_USD_ANNUAL_RANGE = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*[-–—]\s*"
    r"(?:\$|usd\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:year|yearly|annual(?:ly)?|annum)\b",
    re.I,
)
_USD_ANNUAL = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:year|yearly|annual(?:ly)?|annum)\b",
    re.I,
)
_USD_HOURLY_RANGE = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*[-–—]\s*"
    r"(?:\$|usd\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:hour|hourly|hr)\b",
    re.I,
)
_USD_HOURLY = re.compile(
    r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:usd\s*)?"
    r"(?:/|per\s*)?(?:hour|hourly|hr)\b",
    re.I,
)
_UPPER_BOUND_PREFIX = re.compile(
    r"\b(?:up\s+to|max(?:imum)?(?:\s+(?:of|is))?|as\s+(?:high|much)\s+as)\s*$",
    re.I,
)
_UPPER_BOUND_COMPENSATION = re.compile(
    r"\b(?:up\s+to|max(?:imum)?(?:\s+(?:of|is))?|as\s+(?:high|much)\s+as)\s*"
    r"(?:₹|\$|usd\b|inr\b|rs\.?\s*)",
    re.I,
)
_INTERNSHIP_DURATION = re.compile(r"\b(\d{1,2})\s*[- ]?months?\b", re.I)
_LANGUAGE_NAMES = (
    "English", "Hindi", "Mandarin", "Chinese", "German", "French", "Spanish",
    "Portuguese", "Dutch", "Italian", "Japanese", "Korean", "Arabic", "Turkish",
    "Ukrainian", "Russian", "Polish", "Swedish", "Norwegian", "Danish",
)
_LANGUAGE_NAME_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _LANGUAGE_NAMES) + r")\b",
    re.I,
)
_LANGUAGE_REQUIREMENT = re.compile(
    r"\b(fluent|fluency|proficien(?:t|cy)|required|requirement|must speak|native(?: speaker)?|"
    r"daily communication|working language)\b",
    re.I,
)
_DEGREE_REQUIREMENT_SIGNAL = re.compile(
    r"\b(currently pursuing|must (?:have|hold|be)|required?|requirement|minimum|"
    r"should have|you (?:have|hold)|candidates? (?:have|hold)|only|eligible)\b",
    re.I,
)
_OPTIONAL_DEGREE = re.compile(r"\b(preferred|desirable|nice to have|plus|asset)\b", re.I)
_DEGREE_PATTERNS: tuple[tuple[DegreeLevel, re.Pattern[str]], ...] = (
    (
        DegreeLevel.BACHELORS,
        re.compile(
            r"\b(?:bachelor(?:['’]s|s)|bachelor\s+(?:degree|program(?:me)?)|"
            r"bachelor\s+of\s+(?:technology|engineering)|b[.]?\s*tech(?:nology)?|"
            r"undergraduate(?:\s+(?:degree|program(?:me)?))?)\b",
            re.I,
        ),
    ),
    (
        DegreeLevel.MASTERS,
        re.compile(
            r"\b(?:master(?:['’]s|s)|master\s+(?:degree|program(?:me)?)|"
            r"master\s+of\s+(?:technology|engineering)|m[.]?\s*tech(?:nology)?|"
            r"postgraduate(?:\s+(?:degree|program(?:me)?))?)\b",
            re.I,
        ),
    ),
    (DegreeLevel.DOCTORATE, re.compile(r"\b(doctorate|doctoral|ph\.?d\.?)\b", re.I)),
)
_DEGREE_RANK = {
    DegreeLevel.UNKNOWN: 0,
    DegreeLevel.BACHELORS: 1,
    DegreeLevel.MASTERS: 2,
    DegreeLevel.DOCTORATE: 3,
}
_OPTIONAL_LANGUAGE = re.compile(r"\b(asset|preferred|nice to have|bonus|a plus|advantage)\b", re.I)
_INDIA_CITY_ALIASES = {
    "ahmedabad": "ahmedabad",
    "bangalore": "bengaluru",
    # Numatix's live Zoho posting currently emits this spelling.
    "banglore": "bengaluru",
    "bengaluru": "bengaluru",
    "chandigarh": "chandigarh",
    "chennai": "chennai",
    "coimbatore": "coimbatore",
    "delhi": "delhi",
    "gurgaon": "gurugram",
    "gurugram": "gurugram",
    "hyderabad": "hyderabad",
    # DoorDash's live India Greenhouse board currently emits this spelling.
    "hyderbad": "hyderabad",
    "jaipur": "jaipur",
    "kochi": "kochi",
    "kolkata": "kolkata",
    "mohali": "mohali",
    "mumbai": "mumbai",
    "noida": "noida",
    "pune": "pune",
}
_CAREER_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mentorship", re.compile(r"\b(mentor(?:ship|ed)?|dedicated buddy|pair(?:ing)? with|code reviews?)\b", re.I)),
    ("production_impact", re.compile(r"\b(production(?:-grade)?|real[- ]world|ship(?:ping)? (?:features|code)|customer[- ]facing)\b", re.I)),
    ("end_to_end_ownership", re.compile(r"\b(end[- ]to[- ]end|ownership|own (?:a |the )?(?:feature|project|service))\b", re.I)),
    ("conversion_path", re.compile(r"\b(pre[- ]placement offer|\bppo\b|full[- ]time conversion|return offer)\b", re.I)),
    ("structured_learning", re.compile(r"\b(learning and development|professional development|training program|job shadowing)\b", re.I)),
)
_TECH_ALIAS_ENTRIES = tuple(
    (canonical, tuple(alias.lower() for alias in aliases))
    for canonical, aliases in TECH_TAXONOMY.items()
)


def _track_matches_preference(track: TechnicalTrack, preferred: list[TechnicalTrack]) -> bool:
    """Keep broad roles visible while respecting a candidate's chosen specialization."""
    if not preferred or TechnicalTrack.SOFTWARE in preferred or track == TechnicalTrack.SOFTWARE:
        return True
    selected = set(preferred)
    if track == TechnicalTrack.FULLSTACK:
        return bool(selected & {TechnicalTrack.FULLSTACK, TechnicalTrack.BACKEND, TechnicalTrack.FRONTEND})
    if TechnicalTrack.FULLSTACK in selected and track in {TechnicalTrack.BACKEND, TechnicalTrack.FRONTEND}:
        return True
    if track in {TechnicalTrack.AI_ML, TechnicalTrack.DATA}:
        return bool(selected & {TechnicalTrack.AI_ML, TechnicalTrack.DATA})
    return track in selected


def _required_language_groups(description: str) -> list[set[str]]:
    """Extract required natural languages while preserving OR alternatives."""
    groups: list[set[str]] = []
    for clause in re.split(r"(?<=[.!?])\s+|[;\n•]+", description):
        if not _LANGUAGE_REQUIREMENT.search(clause) or _OPTIONAL_LANGUAGE.search(clause):
            continue
        names = [match.group(1).title() for match in _LANGUAGE_NAME_PATTERN.finditer(clause)]
        names = list(dict.fromkeys(names))
        if not names:
            continue
        if len(names) > 1 and re.search(r"\bor\b", clause, re.I):
            groups.append(set(names))
        else:
            groups.extend({name} for name in names)
    unique: list[set[str]] = []
    for group in groups:
        if group not in unique:
            unique.append(group)
    return unique


def _required_degree_level(description: str) -> DegreeLevel:
    """Extract the minimum level from explicit, non-preferred degree clauses."""
    required: list[DegreeLevel] = []
    for clause in re.split(r"(?<=[.!?])\s+|[;\n•]+", description):
        if not _DEGREE_REQUIREMENT_SIGNAL.search(clause) or _OPTIONAL_DEGREE.search(clause):
            continue
        levels = [level for level, pattern in _DEGREE_PATTERNS if pattern.search(clause)]
        if levels:
            # Alternatives such as "Bachelor's or Master's" admit the lower
            # level; independent requirement clauses are combined below.
            required.append(min(levels, key=_DEGREE_RANK.__getitem__))
    return max(required, key=_DEGREE_RANK.__getitem__, default=DegreeLevel.UNKNOWN)


def _is_word_character(value: str) -> bool:
    return value == "_" or value.isalnum()


def _contains_bounded_alias(text: str, alias: str) -> bool:
    r"""Match a literal alias with the old regex's ``\w`` boundaries.

    Running one giant alternation over long descriptions caused severe regex
    backtracking: technology extraction consumed roughly three quarters of a
    full-index rescore. ``str.find`` stays in optimized C code while these two
    boundary checks preserve important distinctions such as Java vs JavaScript.
    """
    offset = 0
    while (index := text.find(alias, offset)) >= 0:
        end = index + len(alias)
        before_ok = index == 0 or not _is_word_character(text[index - 1])
        after_ok = end == len(text) or not _is_word_character(text[end])
        if before_ok and after_ok:
            return True
        offset = index + 1
    return False


def _experience_requirements(text: str) -> list[int]:
    """Extract lower-bound years while excluding explicit history/age facts."""
    values: list[int] = []
    matches = [*_EXPERIENCE_RANGE.finditer(text)]
    ranged_spans = [match.span() for match in matches]
    matches.extend(
        match
        for match in _EXPERIENCE.finditer(text)
        if not any(start <= match.start() < end for start, end in ranged_spans)
    )
    history_subject = re.compile(
        r"\b(company|business|firm|brand|platform|product|software|systems?|technology|"
        r"industry|history|heritage|legacy|founders?|co-?founders?|team)\b",
        re.I,
    )
    history_action = re.compile(
        r"\b(worked together for|spent|operating for|in business for|serving for|"
        r"has been operating for|have been operating for|founded|established|launched)\b",
        re.I,
    )
    requirement_context = re.compile(
        r"\b(experience|requirements?|qualifications?|requires?|required|minimum|"
        r"at least|must have|should have|you have|ideally)\b",
        re.I,
    )
    for match in matches:
        before = text[max(0, match.start() - 120):match.start()]
        after = text[match.end():match.end() + 100]
        if re.match(r"^\s*(?:ago|old|of history)\b", after, re.I):
            continue
        # "Up to N years" is an upper bound that explicitly permits zero
        # experience. Treating N as the minimum demotes genuine fresher roles.
        if re.search(r"\b(?:up to|maximum|max(?:imum)?(?: of)?)\s*$", before[-40:], re.I):
            continue
        clause_start = max(
            text.rfind(delimiter, 0, match.start())
            for delimiter in (".", ";", "\n", "•")
        )
        clause_ends = [
            index
            for delimiter in (".", ";", "\n", "•")
            if (index := text.find(delimiter, match.end())) >= 0
        ]
        clause_end = min(clause_ends, default=len(text))
        local_context = text[clause_start + 1:clause_end]
        if (
            (history_action.search(before) or history_subject.search(local_context))
            and not requirement_context.search(local_context)
        ):
            continue
        values.append(int(match.group(1)))
    return values


def _extract_technologies(text: str) -> set[str]:
    lower = text.lower()
    return {
        canonical
        for canonical, aliases in _TECH_ALIAS_ENTRIES
        if any(_contains_bounded_alias(lower, alias) for alias in aliases)
    }


def infer_live_status(description: str, *, source_observed_active: bool) -> LiveStatus:
    if _CLOSED.search(description):
        return LiveStatus.CLOSED
    return LiveStatus.ACTIVE if source_observed_active else LiveStatus.UNKNOWN


def _graduation_years(description: str) -> set[int]:
    """Extract years from bounded clauses without regex backtracking.

    The former pattern attempted a greedy ``[^.\n]{0,80}`` prefix at nearly
    every character in long job descriptions. Descriptions without graduation
    language therefore paid an avoidable quadratic-style scan. Locate the rare
    signal first, then reproduce its punctuation-bounded 80-character context.
    """
    lower = description.lower()
    spans: set[tuple[int, int]] = set()
    for signal in _GRADUATION_SIGNALS:
        offset = 0
        while (start := lower.find(signal, offset)) >= 0:
            end = start + len(signal)
            before_ok = start == 0 or not _is_word_character(lower[start - 1])
            after_ok = end == len(lower) or not _is_word_character(lower[end])
            if before_ok and after_ok:
                spans.add((start, end))
            offset = start + 1

    years: set[int] = set()
    for signal_start, signal_end in sorted(spans):
        prefix_start = max(0, signal_start - 80)
        prefix = description[prefix_start:signal_start]
        boundary = max(prefix.rfind("."), prefix.rfind("\n"))
        start = prefix_start + boundary + 1 if boundary >= 0 else prefix_start

        suffix_end = min(len(description), signal_end + 80)
        suffix = description[signal_end:suffix_end]
        stops = [
            position
            for position in (suffix.find("."), suffix.find("\n"))
            if position >= 0
        ]
        end = signal_end + min(stops) if stops else suffix_end
        years.update(int(value) for value in _YEAR.findall(description[start:end]))
    return years


def _india_cities(value: str) -> set[str]:
    lower = value.lower()
    return {canonical for alias, canonical in _INDIA_CITY_ALIASES.items() if re.search(rf"\b{alias}\b", lower)}


def _money_value(number: str, unit: str = "") -> int:
    value = float(number.replace(",", ""))
    multiplier = 100_000 if unit.lower() in {"lakh", "lac", "l"} else 1_000 if unit.lower() in {"k", "thousand"} else 1
    return round(value * multiplier)


def _upper_bound_only(description: str, match_start: int) -> bool:
    return bool(_UPPER_BOUND_PREFIX.search(description[max(0, match_start - 32):match_start]))


def _monthly_compensation_values(description: str) -> list[int]:
    values: list[int] = []
    range_matches = list(_MONTHLY_PAY_RANGE.finditer(description))
    range_spans = [match.span() for match in range_matches]
    for match in range_matches:
        if _upper_bound_only(description, match.start()):
            continue
        if not re.search(r"₹|\binr\b|\brs\.?\b|\blakhs?\b|\blac\b|\d\s*l\b", match.group(0), re.I):
            continue
        values.append(_money_value(match.group(1), match.group(2) or match.group(4) or ""))
    for match in _MONTHLY_PAY.finditer(description):
        if any(start <= match.start() < end for start, end in range_spans):
            continue
        if _upper_bound_only(description, match.start()):
            continue
        if not re.search(r"₹|\binr\b|\brs\.?\b|\blakhs?\b|\blac\b|\d\s*l\b", match.group(0), re.I):
            continue
        values.append(_money_value(match.group(1), match.group(2) or ""))
    values.extend(
        round(float(match.group(1)) * 100_000 / 12)
        for match in _ANNUAL_LAKH.finditer(description)
        if not _upper_bound_only(description, match.start())
    )
    return values


def _usd_monthly_compensation_values(description: str) -> list[int]:
    """Normalize disclosed USD monthly, annual, and hourly lower bounds.

    Hourly postings use the conventional 40-hour week only for ranking. The
    original disclosure remains in source evidence, and no FX conversion is
    performed so volatile exchange rates cannot silently change eligibility.
    """
    values: list[int] = []
    range_patterns = (
        (_USD_MONTHLY_RANGE, lambda value: round(value)),
        (_USD_ANNUAL_RANGE, lambda value: round(value / 12)),
        (_USD_HOURLY_RANGE, lambda value: round(value * 40 * 52 / 12)),
    )
    single_patterns = (
        (_USD_MONTHLY, lambda value: round(value)),
        (_USD_ANNUAL, lambda value: round(value / 12)),
        (_USD_HOURLY, lambda value: round(value * 40 * 52 / 12)),
    )
    range_spans: list[tuple[int, int]] = []
    for pattern, normalize in range_patterns:
        for match in pattern.finditer(description):
            range_spans.append(match.span())
            if _upper_bound_only(description, match.start()):
                continue
            values.append(normalize(_money_value(match.group(1), match.group(2) or "")))
    for pattern, normalize in single_patterns:
        for match in pattern.finditer(description):
            if any(start <= match.start() < end for start, end in range_spans):
                continue
            if _upper_bound_only(description, match.start()):
                continue
            values.append(normalize(_money_value(match.group(1), match.group(2) or "")))
    return values


def _compensation_score(
    candidate: CandidateConstraints,
    inr_values: list[int],
    usd_values: list[int],
) -> tuple[int, bool | None]:
    thresholds = (
        (inr_values, candidate.minimum_monthly_compensation_inr, candidate.target_monthly_compensation_inr),
        (usd_values, candidate.minimum_monthly_compensation_usd, candidate.target_monthly_compensation_usd),
    )
    configured = [(values, minimum, target) for values, minimum, target in thresholds if minimum or target]
    if not configured:
        return 50, None
    observed = [(values, minimum, target) for values, minimum, target in configured if values]
    if not observed:
        return 0, None

    target_checks = [min(values) >= target for values, _minimum, target in observed if target]
    if target_checks and any(target_checks):
        return 100, True

    floor_checks = [min(values) >= minimum for values, minimum, _target in observed if minimum]
    if floor_checks and any(floor_checks):
        return 70, False if target_checks else None

    # Comparable pay was disclosed, but it cleared neither the configured hard
    # floor nor target. The hard-blocking decision is made by the caller.
    comparable = any(minimum or target for _values, minimum, target in observed)
    return (20 if comparable else 50), (False if target_checks else None)


def evaluate_applicability(
    *,
    title: str,
    description: str,
    location: str,
    candidate: CandidateConstraints,
    workplace: str = "",
    live_status: LiveStatus | None = None,
    source_observed_active: bool = False,
) -> ApplicabilityDecision:
    classification: OpportunityClassification = classify_opportunity(
        title,
        description,
        location,
        workplace,
    )
    status = live_status or infer_live_status(description, source_observed_active=source_observed_active)
    safety = assess_safety(
        f"{title}\n{description}",
        allow_unpaid=candidate.allow_unpaid,
        allow_bond=candidate.allow_bond,
    )
    hard_blockers: list[str] = []
    unknowns = list(classification.unknowns)
    evidence = {**classification.evidence, **safety.evidence}
    posting_cities = _india_cities(location)
    authorization_restricted = bool(
        _AUTHORIZATION.search(description) and _COUNTRY_RESTRICTION.search(description)
    )

    if status in {LiveStatus.CLOSED, LiveStatus.EXPIRED}:
        hard_blockers.append("closed")
        evidence["closed"] = [f"lifecycle_status:{status.value}"]
    if classification.opportunity_type == OpportunityType.OTHER:
        years = _experience_requirements(description)
        if any(year > 0 for year in years) or re.search(
            r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect)\b",
            title,
            re.I,
        ):
            hard_blockers.append("experience_requirement")
            evidence["experience_requirement"] = ["senior_title_or_experience_signal"]
        else:
            hard_blockers.append("not_early_career")
    if classification.technical_track in {TechnicalTrack.NON_TECHNICAL, TechnicalTrack.UNKNOWN}:
        hard_blockers.append(
            "non_technical_role" if classification.technical_track == TechnicalTrack.NON_TECHNICAL
            else "technical_track_unknown"
        )
    elif not _track_matches_preference(classification.technical_track, candidate.preferred_technical_tracks):
        hard_blockers.append("technical_track_not_preferred")
        evidence["technical_track_not_preferred"] = [
            f"posting:{classification.technical_track.value}",
            f"preferred:{sorted(track.value for track in candidate.preferred_technical_tracks)}",
        ]
    if (
        classification.opportunity_type != OpportunityType.OTHER
        and classification.opportunity_type not in candidate.accepted_opportunity_types
    ):
        hard_blockers.append("opportunity_type_not_accepted")
        evidence["opportunity_type_not_accepted"] = [
            f"posting:{classification.opportunity_type.value}",
            f"accepted:{sorted(kind.value for kind in candidate.accepted_opportunity_types)}",
        ]
    if classification.workplace_scope in {
        WorkplaceScope.RESTRICTED_REMOTE,
        WorkplaceScope.OUTSIDE_INDIA_ONSITE,
    }:
        hard_blockers.append("country_restriction")
    if classification.workplace_scope in {WorkplaceScope.INDIA_ONSITE, WorkplaceScope.INDIA_HYBRID}:
        accepted_cities = {
            canonical
            for city in candidate.accepted_india_cities
            for canonical in _india_cities(city)
        }
        if accepted_cities and posting_cities and accepted_cities.isdisjoint(posting_cities):
            hard_blockers.append("india_city_not_accepted")
            evidence["india_city_not_accepted"] = [
                f"posting:{sorted(posting_cities)}",
                f"accepted:{sorted(accepted_cities)}",
            ]
        elif accepted_cities and not posting_cities:
            unknowns.append("india_city_unknown")
            evidence["india_city_unknown"] = [
                f"accepted:{sorted(accepted_cities)}",
                "posting:country_only",
            ]
    workplace_allowed = {
        WorkplaceScope.INDIA_ONSITE: candidate.allow_india_onsite,
        WorkplaceScope.INDIA_HYBRID: candidate.allow_india_hybrid,
        WorkplaceScope.INDIA_REMOTE: candidate.allow_india_remote,
        WorkplaceScope.WORLDWIDE_REMOTE: candidate.allow_worldwide_remote,
    }
    if classification.workplace_scope in workplace_allowed and not workplace_allowed[classification.workplace_scope]:
        hard_blockers.append("workplace_not_accepted")
        evidence["workplace_not_accepted"] = [f"posting:{classification.workplace_scope.value}"]
    if authorization_restricted:
        hard_blockers.append("work_authorization")
        evidence["work_authorization"] = ["restricted_work_authorization_text"]

    required_language_groups = _required_language_groups(description)
    candidate_languages = {language.casefold() for language in candidate.spoken_languages}
    missing_language_groups = [
        group
        for group in required_language_groups
        if candidate_languages.isdisjoint(language.casefold() for language in group)
    ]
    if missing_language_groups:
        hard_blockers.append("language_requirement")
        evidence["language_requirement"] = [
            "one_of:" + ",".join(sorted(group)) for group in missing_language_groups
        ]

    qualification_text = f"{title}\n{description}"
    required_degree_level = _required_degree_level(qualification_text)
    if required_degree_level != DegreeLevel.UNKNOWN:
        evidence["degree_requirement"] = [f"minimum:{required_degree_level.value}"]
        if candidate.current_degree_level == DegreeLevel.UNKNOWN:
            unknowns.append("candidate_degree_level_unknown")
        elif _DEGREE_RANK[candidate.current_degree_level] < _DEGREE_RANK[required_degree_level]:
            hard_blockers.append("degree_level_requirement")
            evidence["degree_requirement"].append(
                f"candidate:{candidate.current_degree_level.value}"
            )

    graduation_years = _graduation_years(qualification_text)
    if graduation_years and candidate.graduation_year not in graduation_years:
        hard_blockers.append("graduation_year")
        evidence["graduation_year"] = [f"allowed_years:{sorted(graduation_years)}"]
    if _ENROLLED.search(description) and not candidate.currently_enrolled:
        hard_blockers.append("enrollment_requirement")
    if _EXTERNAL_PROGRAM_RESTRICTION.search(description):
        hard_blockers.append("external_program_restriction")
        evidence["external_program_restriction"] = ["named_external_program_or_portal_required"]

    compensation_values = _monthly_compensation_values(description)
    usd_compensation_values = _usd_monthly_compensation_values(description)
    if (
        candidate.minimum_monthly_compensation_inr > 0
        and compensation_values
        and min(compensation_values) < candidate.minimum_monthly_compensation_inr
    ):
        hard_blockers.append("compensation_below_minimum")
        evidence["compensation_below_minimum"] = [
            f"observed_monthly_inr:{min(compensation_values)}",
            f"candidate_minimum_inr:{candidate.minimum_monthly_compensation_inr}",
        ]
    if (
        candidate.minimum_monthly_compensation_usd > 0
        and usd_compensation_values
        and min(usd_compensation_values) < candidate.minimum_monthly_compensation_usd
    ):
        hard_blockers.append("compensation_below_minimum")
        evidence.setdefault("compensation_below_minimum", []).extend([
            f"observed_monthly_usd:{min(usd_compensation_values)}",
            f"candidate_minimum_usd:{candidate.minimum_monthly_compensation_usd}",
        ])
    compensation_targeting_enabled = bool(
        candidate.minimum_monthly_compensation_inr
        or candidate.target_monthly_compensation_inr
        or candidate.minimum_monthly_compensation_usd
        or candidate.target_monthly_compensation_usd
    )
    comparable_compensation_observed = bool(
        compensation_values
        and (candidate.minimum_monthly_compensation_inr or candidate.target_monthly_compensation_inr)
    ) or bool(
        usd_compensation_values
        and (candidate.minimum_monthly_compensation_usd or candidate.target_monthly_compensation_usd)
    )
    if compensation_targeting_enabled and not comparable_compensation_observed:
        evidence["compensation_unknown"] = [
            f"candidate_policy:{candidate.unknown_compensation_policy.value}"
        ]
        if _UPPER_BOUND_COMPENSATION.search(description):
            evidence["compensation_upper_bound_only"] = [
                "maximum_disclosed_without_guaranteed_minimum"
            ]
        if candidate.unknown_compensation_policy == UnknownCompensationPolicy.REVIEW:
            unknowns.append("compensation_unknown")
        elif candidate.unknown_compensation_policy == UnknownCompensationPolicy.SKIP:
            hard_blockers.append("compensation_unknown")

    durations = [int(value) for value in _INTERNSHIP_DURATION.findall(description)]
    if (
        classification.opportunity_type == OpportunityType.INTERNSHIP
        and durations
        and max(durations) > candidate.maximum_internship_months
    ):
        hard_blockers.append("internship_duration")
        evidence["internship_duration"] = [
            f"required_months:{max(durations)}",
            f"candidate_maximum_months:{candidate.maximum_internship_months}",
        ]

    experience_years = _experience_requirements(description)
    minimum_experience = max(experience_years, default=0)
    stretch = False
    if minimum_experience > candidate.professional_experience_years:
        if minimum_experience <= 3 and classification.opportunity_type != OpportunityType.OTHER:
            stretch = True
            evidence["experience_stretch"] = [f"minimum_years:{minimum_experience}"]
        elif minimum_experience >= 4 and "experience_requirement" not in hard_blockers:
            hard_blockers.append("experience_requirement")

    if "remote_geography_unknown" in unknowns:
        hard_blockers.append("remote_geography_unknown")
    if "india_city_unknown" in unknowns:
        hard_blockers.append("india_city_unknown")

    hard_blockers = list(dict.fromkeys(hard_blockers))
    reviewable_blockers = {"remote_geography_unknown", "india_city_unknown"}
    decisive_hard_blockers = [blocker for blocker in hard_blockers if blocker not in reviewable_blockers]
    paid_status = safety.paid_status
    if paid_status == PaidStatus.UNKNOWN and classification.opportunity_type != OpportunityType.INTERNSHIP:
        paid_status = PaidStatus.PAID
        evidence["paid_status"] = ["compensated_employment_type"]

    if decisive_hard_blockers or safety.blockers:
        eligibility = EligibilityStatus.INELIGIBLE
        decision = Decision.SKIP
    elif unknowns or status == LiveStatus.UNKNOWN:
        eligibility = EligibilityStatus.NEEDS_REVIEW
        decision = Decision.NEEDS_REVIEW
        if status == LiveStatus.UNKNOWN:
            unknowns.append("live_status_unknown")
    elif stretch:
        eligibility = EligibilityStatus.LIKELY_ELIGIBLE
        decision = Decision.STRONG_STRETCH
    else:
        eligibility = EligibilityStatus.ELIGIBLE
        decision = Decision.APPLY_NOW

    career_signals = [name for name, pattern in _CAREER_SIGNALS if pattern.search(description)]
    career_growth_score = min(100, 25 + 15 * len(career_signals))
    if safety.blockers or safety.warnings:
        career_growth_score = max(0, career_growth_score - 20)
    hiring_confidence_score = 85 if status == LiveStatus.ACTIVE else 35
    if classification.workplace_scope == WorkplaceScope.UNKNOWN:
        hiring_confidence_score = max(0, hiring_confidence_score - 15)
    if paid_status == PaidStatus.PAID:
        hiring_confidence_score = min(100, hiring_confidence_score + 5)
    elif paid_status in {PaidStatus.UNPAID, PaidStatus.SUSPICIOUS}:
        hiring_confidence_score = max(0, hiring_confidence_score - 25)
    candidate_technologies = _extract_technologies("\n".join([
        *candidate.technical_skills,
        *candidate.project_keywords,
    ]))
    posting_technologies = _extract_technologies(f"{title}\n{description}")
    matched_technologies = candidate_technologies & posting_technologies
    candidate_evidence_missing = not bool(candidate.technical_skills or candidate.project_keywords)
    if candidate_evidence_missing:
        candidate_fit_score = 50
    elif posting_technologies:
        candidate_fit_score = round(100 * len(matched_technologies) / len(posting_technologies))
    else:
        candidate_fit_score = 50
    if matched_technologies:
        evidence["candidate_skill_matches"] = sorted(matched_technologies)
    compensation_score, target_compensation_met = _compensation_score(
        candidate,
        compensation_values,
        usd_compensation_values,
    )
    if target_compensation_met is True:
        evidence["target_compensation"] = ["disclosed_lower_bound_meets_or_exceeds_target"]
    priority_bases = {
        Decision.APPLY_NOW: 60,
        Decision.STRONG_STRETCH: 45,
        Decision.NEEDS_REVIEW: 25,
        Decision.SKIP: 0,
    }
    priority_score = 0 if decision == Decision.SKIP else min(
        100,
        priority_bases[decision]
        + round(career_growth_score * 0.15)
        + round(hiring_confidence_score * 0.1)
        + round(candidate_fit_score * 0.15)
        + round(compensation_score * 0.2),
    )

    return ApplicabilityDecision(
        eligibility=eligibility,
        decision=decision,
        live_status=status,
        opportunity_type=classification.opportunity_type,
        technical_track=classification.technical_track,
        workplace_scope=classification.workplace_scope,
        india_eligible=classification.india_eligible,
        paid_status=paid_status,
        hard_blockers=hard_blockers,
        safety_blockers=safety.blockers,
        safety_warnings=safety.warnings,
        unknowns=list(dict.fromkeys(unknowns)),
        evidence=evidence,
        career_growth_score=career_growth_score,
        hiring_confidence_score=hiring_confidence_score,
        priority_score=priority_score,
        career_signals=career_signals,
        candidate_fit_score=candidate_fit_score,
        matched_skills=sorted(matched_technologies),
        posting_skills=sorted(posting_technologies),
        candidate_evidence_missing=candidate_evidence_missing,
        posting_india_cities=sorted(posting_cities),
        graduation_years=sorted(graduation_years),
        monthly_compensation_inr=sorted(set(compensation_values)),
        monthly_compensation_usd=sorted(set(usd_compensation_values)),
        compensation_score=compensation_score,
        target_compensation_met=target_compensation_met,
        internship_duration_months=sorted(set(durations)),
        minimum_experience_years=minimum_experience,
        requires_current_enrollment=bool(_ENROLLED.search(description)),
        work_authorization_restricted=authorization_restricted,
        required_language_groups=[sorted(group) for group in required_language_groups],
        required_degree_level=required_degree_level,
    )
