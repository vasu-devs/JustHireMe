from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from discovery.normalizer import clean_text


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    ENTRY_LEVEL_FULL_TIME = "entry_level_full_time"
    STRETCH_FULL_TIME = "stretch_full_time"
    OTHER = "other"


class TechnicalTrack(StrEnum):
    SOFTWARE = "software"
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    AI_ML = "ai_ml"
    DATA = "data"
    CLOUD_DEVOPS = "cloud_devops"
    SECURITY = "security"
    MOBILE = "mobile"
    QA_AUTOMATION = "qa_automation"
    EMBEDDED_SYSTEMS = "embedded_systems"
    NON_TECHNICAL = "non_technical"
    UNKNOWN = "unknown"


class WorkplaceScope(StrEnum):
    INDIA_ONSITE = "india_onsite"
    INDIA_HYBRID = "india_hybrid"
    INDIA_REMOTE = "india_remote"
    WORLDWIDE_REMOTE = "worldwide_remote"
    REGION_REMOTE = "region_remote"
    RESTRICTED_REMOTE = "restricted_remote"
    OUTSIDE_INDIA_ONSITE = "outside_india_onsite"
    UNKNOWN = "unknown"


class OpportunityClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_type: OpportunityType
    technical_track: TechnicalTrack
    workplace_scope: WorkplaceScope
    india_eligible: bool
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)


_INTERN = re.compile(r"\b(intern(?:ship)?s?|co-?ops?)\b", re.I)
_EARLY_CAREER_PROGRAM = re.compile(
    r"\b(resident|residency|fellow(?:ship)?|(?:campus|university)\s+program)\b",
    re.I,
)
_PROGRAM_INTERNSHIP_EVIDENCE = re.compile(
    r"\b(internship|undergraduate(?:\s+(?:degree|student))?|"
    r"final[ -]?year(?:\s+(?:college|university))?\s+students?)\b",
    re.I,
)
_PROGRAM_NEW_GRAD_EVIDENCE = re.compile(
    r"\b(fresh|recent|new)\s+graduates?\b|\bearly[ -]?career\b",
    re.I,
)
_PROGRAM_TECHNICAL_EVIDENCE = re.compile(
    r"\b(?:tech(?:nology|nical)?(?:[ -]based)?\s+roles?|technical\s+tracks?)"
    r"\s+(?:include|including|such as|cover)\b[^.\n]{0,240}"
    r"\b(?:software|engineering|ai\s*/?\s*ml|machine learning|automation|"
    r"cybersecurity|database|cloud|data|statistical programming)\b",
    re.I,
)
_NEW_GRAD = re.compile(
    r"\b(new\s*grad(?:uate)?|graduate(?:\s+(?:engineer|developer|program))?|"
    r"campus(?:\s+(?:hire|hiring|engineer|graduate)))\b",
    re.I,
)
_ENTRY = re.compile(
    r"\b(entry[ -]?level|fresher|junior|associate\s+(?:software|backend|frontend|data|cloud|security|qa|systems?)|"
    r"(?:data(?:\s+qa)?|software|technical|qa|quality assurance)\s+associate|"
    r"software\s+engineer\s+(?:i|1)|sde\s*(?:i|1)|engineer\s+(?:i|1))\b",
    re.I,
)
_STRUCTURED_INTERNSHIP = re.compile(
    r"\bemployment\s+type\s*:\s*(?:intern|internship)\b",
    re.I,
)
_STRUCTURED_ENTRY_EXPERIENCE = re.compile(
    r"\b(?:work\s+)?experience\s*:\s*(?:fresher\b|"
    r"0(?:\s*(?:[-–—]|to)\s*[0-3]\s*(?:years?|yrs?))?\b)|"
    r"\b0\s*(?:[-–—]|to)\s*[0-3]\s*(?:years?|yrs?)\s+of\s+(?:relevant\s+|professional\s+|"
    r"technical\s+|work\s+)?experience\b",
    re.I,
)
_STRUCTURED_STRETCH_EXPERIENCE = re.compile(
    r"\b(?:work\s+)?experience\s*:\s*[1-3]"
    r"(?:\s*(?:[-–—]|to)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b",
    re.I,
)
_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head of|vice president|vp)\b",
    re.I,
)
_PROGRAM_STAFF_TITLE = re.compile(
    r"^\s*(?:technical\s+)?(?:mentor|trainer|faculty|instructor|teacher)\b|"
    r"\b(?:mentor|trainer|faculty|instructor|teacher)\b[^()\n]{0,80}"
    r"\binternship\s+program\b",
    re.I,
)
_NON_TECH = re.compile(
    r"\b(marketing|advertis(?:e|ing)|ads? specialist|sales|recruit(?:er|ing|ment)|human resources|\bhr\b|"
    r"accountant|finance|legal|customer success|procurement|copywriter|regulatory intelligence|data entry|"
    r"business development|communications?|social media|content writer|account development representative|"
    r"sales development representative|\bsdr\b|account executive|talent acquisition|people operations?|"
    r"workplace (?:and|&) culture|"
    r"product (?:manager|management|ops|operations|intern|led growth)|program manager|program coordinator|business analyst|"
    r"operations?|demand generation|\bb2b growth\b|cloud business|"
    r"(?:ai\s+)?gtm\s+(?:intern|associate|manager|leader|strategist)|"
    r"go[- ]to[- ]market\s+(?:intern|associate|manager|leader|strategist|pricing)|"
    r"domain (?:expert|specialist)|subject matter expert|"
    r"technical writer|data annotator|ai trainer|"
    r"designer|design intern|design engineer(?:ing)?|mechanical engineer(?:ing)?)\b",
    re.I,
)
_TECHNICAL_TITLE_CONTEXT = re.compile(
    r"\b(engineer(?:ing)?|developer|programmer|software|technical|technology|research|data|algorithm|"
    r"computer|systems?|network|quality assurance|\bqa\b|sde|swe|test development)\b",
    re.I,
)
_MIXED_DESIGN_TECH_TITLE = re.compile(
    r"\b(?:ui\s*/?\s*ux\s+)?designer\b\s*(?:&|and|\+|/)\s*"
    r"(?:flutter|mobile|software|front[ -]?end|web)?\s*(?:developer|engineer)\b|"
    r"\b(?:flutter|mobile|software|front[ -]?end|web)?\s*(?:developer|engineer)\b\s*"
    r"(?:&|and|\+|/)\s*(?:ui\s*/?\s*ux\s+)?designer\b",
    re.I,
)
_SOFTWARE_ENGINEERING_ACRONYM = re.compile(r"\b(?:sde|swe)\b", re.I)
_EXPLICIT_TECHNICAL_ROLE_DESCRIPTION = re.compile(
    r"\b(support integration architect|technical integration|healthcare information technology|"
    r"systems integration|integration engineering)\b",
    re.I,
)
_QA_TITLE = re.compile(r"\b(qa|quality assurance|software testing)\b", re.I)
_QA_TECHNICAL_EVIDENCE = re.compile(
    r"\b(engineer(?:ing)?|automation|software|web|mobile|full[ -]?stack|devops|cloud|"
    r"cybersecurity|firmware|ai\s*/?\s*ml|api(?: testing)?|test cases?|test automation|automated tests?|"
    r"sdet|selenium|cypress|playwright|postman|jira|bug(?:s| tracking)?|sql|python|java|"
    r"javascript|typescript|ci/?cd|regression testing|functional testing|\bit\b|it validation)\b",
    re.I,
)
_QA_NONTECHNICAL_EVIDENCE = re.compile(
    r"\b(pharmaceutical|sterility|clinical|laboratory|gmp|gxp|call cent(?:er|re)|"
    r"linguistic|(?:language|quality assurance) rater|lead generation|food safety|manufacturing quality|"
    r"training specialist|medical device quality)\b",
    re.I,
)
_BOUNDED_STRETCH_EXPERIENCE = re.compile(
    r"\b(?:minimum(?:\s+of)?|at\s+least|requires?|required|qualifications?)"
    r"[^.\n]{0,70}\b[1-3](?:\s*(?:[-–—]|to)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b|"
    r"\b[1-3](?:\s*(?:[-–—]|to)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)"
    r"\s+(?:of\s+)?(?:hands[ -]?on\s+)?(?:relevant\s+|professional\s+|software\s+|"
    r"engineering\s+|technical\s+|work\s+)?experience\b",
    re.I,
)
_TRACK_PATTERNS: tuple[tuple[TechnicalTrack, re.Pattern[str]], ...] = (
    (TechnicalTrack.FULLSTACK, re.compile(r"\b(full[ -]?stack|mern|mean stack)\b", re.I)),
    (TechnicalTrack.AI_ML, re.compile(r"\b(machine learning|artificial intelligence|gen[ -]?ai|\bai\b|\bml\b|nlp|computer vision|llm)\b", re.I)),
    (TechnicalTrack.DATA, re.compile(
        r"\b(data engineer|data scientist|data analyst|data analytics|data qa|data quality|analytics engineer|"
        r"business intelligence|\bbi engineer)\b",
        re.I,
    )),
    (TechnicalTrack.BACKEND, re.compile(r"\b(back[ -]?end|server[ -]?side|api engineer|distributed systems)\b", re.I)),
    (TechnicalTrack.FRONTEND, re.compile(r"\b(front[ -]?end|web ui|react developer|ui engineer)\b", re.I)),
    (TechnicalTrack.MOBILE, re.compile(r"\b(android|ios|mobile|flutter|react native)\b", re.I)),
    (TechnicalTrack.CLOUD_DEVOPS, re.compile(
        r"\b(cloud|devops|platform engineer|site reliability|sre|infrastructure|"
        r"(?:it|systems?|network) administrator|"
        r"support integration architect|technical integration|systems integration|"
        r"integration engineering)\b",
        re.I,
    )),
    (TechnicalTrack.SECURITY, re.compile(r"\b(cyber|security|soc analyst|penetration test|appsec)\b", re.I)),
    (TechnicalTrack.QA_AUTOMATION, re.compile(r"\b(sdet|qa automation|test automation|quality engineer)\b", re.I)),
    (TechnicalTrack.EMBEDDED_SYSTEMS, re.compile(r"\b(embedded|firmware|compiler|kernel|robotics|systems programmer|hw)\b", re.I)),
    (TechnicalTrack.SOFTWARE, re.compile(
        r"\b(software|developer|programmer|sw)\b",
        re.I,
    )),
)
_REMOTE = re.compile(
    r"\b(remote|work from home|home based|distributed[- ]first|distributed\s+(?:team|workforce|company|organisation|organization))\b",
    re.I,
)
_WORLDWIDE = re.compile(r"\b(worldwide|anywhere|global remote|work from anywhere)\b", re.I)
_INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|banglore|hyderabad|hyderbad|pune|gurugram|gurgaon|noida|delhi|chennai|mumbai|"
    r"ahmedabad|kochi|kolkata|jaipur|coimbatore|mohali|chandigarh)\b",
    re.I,
)
_RESTRICTED = re.compile(
    r"\b(united states|u\.?s\.?|canada|united kingdom|u\.?k\.?|european union|\beu\b)\b.{0,25}\b(only|required)|"
    r"\b(only|must reside|must be based|located in|work authorization)\b.{0,45}\b(united states|u\.?s\.?|canada|"
    r"united kingdom|u\.?k\.?|european union|\beu\b)",
    re.I,
)
_OUTSIDE_INDIA = re.compile(
    r"\b(united states|canada|united kingdom|germany|france|berlin|london|san francisco|new york|singapore|australia)\b",
    re.I,
)
_REMOTE_REGION = re.compile(
    r"\b(apac|asia(?:[- ]?pacific)?)\b",
    re.I,
)
_EXCLUDED_REMOTE_REGION = re.compile(
    r"\b(emea|europe|americas?|latam|middle east|africa)\b",
    re.I,
)
_GENERIC_REMOTE_LOCATION = re.compile(
    r"\b(remote|home based|work from home|virtual|distributed|multiple locations?|various locations?)\b",
    re.I,
)
_FRONTEND_STACK = re.compile(r"\b(react|angular|vue|typescript|javascript|front[ -]?end|web ui)\b", re.I)
_BACKEND_STACK = re.compile(r"\b(api|python|java|spring|node\.?js|django|flask|server[ -]?side|database)\b", re.I)


def classify_opportunity(
    title: str,
    description: str,
    location: str,
    workplace: str = "",
) -> OpportunityClassification:
    # ATS-authored titles commonly use underscores as visual separators
    # (for example ``Intern_2027_SW``). Python regex treats underscores as word
    # characters, so normalize them before applying word-boundary signals.
    clean_title = clean_text(title).replace("_", " ")
    clean_description = clean_text(description)
    clean_location = clean_text(location)
    clean_workplace = clean_text(workplace)
    all_text = f"{clean_title}\n{clean_location}\n{clean_workplace}\n{clean_description}"
    evidence: dict[str, list[str]] = {}
    unknowns: list[str] = []
    non_technical_title = bool(
        _NON_TECH.search(clean_title) and not _MIXED_DESIGN_TECH_TITLE.search(clean_title)
    )

    if _SENIOR.search(clean_title):
        opportunity_type = OpportunityType.OTHER
        evidence["opportunity_type"] = ["senior_title"]
    elif _PROGRAM_STAFF_TITLE.search(clean_title):
        opportunity_type = OpportunityType.OTHER
        evidence["opportunity_type"] = ["internship_program_staff_title"]
    elif _INTERN.search(clean_title):
        opportunity_type = OpportunityType.INTERNSHIP
        evidence["opportunity_type"] = ["internship_title"]
    elif (
        _STRUCTURED_INTERNSHIP.search(clean_description)
        and _TECHNICAL_TITLE_CONTEXT.search(clean_title)
        and not non_technical_title
    ):
        opportunity_type = OpportunityType.INTERNSHIP
        evidence["opportunity_type"] = ["structured_internship_employment_type"]
    elif _EARLY_CAREER_PROGRAM.search(clean_title) and _PROGRAM_INTERNSHIP_EVIDENCE.search(
        clean_description
    ):
        opportunity_type = OpportunityType.INTERNSHIP
        evidence["opportunity_type"] = ["early_career_program_with_internship_evidence"]
    elif _EARLY_CAREER_PROGRAM.search(clean_title) and _PROGRAM_NEW_GRAD_EVIDENCE.search(
        clean_description
    ):
        opportunity_type = OpportunityType.NEW_GRAD
        evidence["opportunity_type"] = ["early_career_program_with_new_grad_evidence"]
    elif _NEW_GRAD.search(clean_title):
        opportunity_type = OpportunityType.NEW_GRAD
        evidence["opportunity_type"] = ["graduate_title"]
    elif _ENTRY.search(clean_title):
        opportunity_type = OpportunityType.ENTRY_LEVEL_FULL_TIME
        evidence["opportunity_type"] = ["entry_level_title"]
    elif (
        _STRUCTURED_ENTRY_EXPERIENCE.search(clean_description)
        and _TECHNICAL_TITLE_CONTEXT.search(clean_title)
        and not non_technical_title
    ):
        opportunity_type = OpportunityType.ENTRY_LEVEL_FULL_TIME
        evidence["opportunity_type"] = ["structured_zero_experience_requirement"]
    elif (
        _TECHNICAL_TITLE_CONTEXT.search(clean_title)
        and not non_technical_title
        and (
            _BOUNDED_STRETCH_EXPERIENCE.search(clean_description)
            or _STRUCTURED_STRETCH_EXPERIENCE.search(clean_description)
        )
    ):
        opportunity_type = OpportunityType.STRETCH_FULL_TIME
        evidence["opportunity_type"] = ["bounded_technical_experience_requirement"]
    else:
        opportunity_type = OpportunityType.OTHER
        evidence["opportunity_type"] = ["no_early_career_title_signal"]

    if non_technical_title:
        technical_track = TechnicalTrack.NON_TECHNICAL
        evidence["technical_track"] = ["non_technical_title"]
    else:
        technical_track = TechnicalTrack.UNKNOWN
        qa_title = bool(_QA_TITLE.search(clean_title))
        if qa_title:
            if _QA_TECHNICAL_EVIDENCE.search(f"{clean_title}\n{clean_description}"):
                technical_track = TechnicalTrack.QA_AUTOMATION
                evidence["technical_track"] = ["qa_title_with_technical_evidence"]
            elif _QA_NONTECHNICAL_EVIDENCE.search(f"{clean_title}\n{clean_description}"):
                technical_track = TechnicalTrack.NON_TECHNICAL
                evidence["technical_track"] = ["qa_title_with_nonsoftware_evidence"]
            else:
                evidence["technical_track"] = ["qa_title_software_scope_unknown"]
        else:
            for track, pattern in _TRACK_PATTERNS:
                if pattern.search(clean_title):
                    technical_track = track
                    evidence["technical_track"] = [f"title_pattern:{track.value}"]
                    break
        if technical_track == TechnicalTrack.UNKNOWN and not qa_title and (
            _TECHNICAL_TITLE_CONTEXT.search(clean_title)
            or _EXPLICIT_TECHNICAL_ROLE_DESCRIPTION.search(clean_description)
            or (
                _EARLY_CAREER_PROGRAM.search(clean_title)
                and _PROGRAM_TECHNICAL_EVIDENCE.search(clean_description)
            )
        ):
            # Description evidence may resolve a vague technical title such as
            # "Engineering Intern" or "Research Intern". A generic/nontechnical
            # title cannot become CSE merely because its description mentions AI.
            for track, pattern in _TRACK_PATTERNS:
                if pattern.search(clean_description):
                    technical_track = track
                    evidence["technical_track"] = [f"description_pattern:{track.value}"]
                    break
        if technical_track == TechnicalTrack.UNKNOWN and _SOFTWARE_ENGINEERING_ACRONYM.search(
            clean_title
        ):
            technical_track = TechnicalTrack.SOFTWARE
            evidence["technical_track"] = ["title_acronym:software_engineering"]
        if technical_track == TechnicalTrack.UNKNOWN:
            unknowns.append("technical_track_unknown")
        elif (
            technical_track == TechnicalTrack.SOFTWARE
            and _FRONTEND_STACK.search(clean_description)
            and _BACKEND_STACK.search(clean_description)
        ):
            # A deliberately generic title can still be made more useful from
            # two-sided stack evidence; one framework alone is not enough.
            technical_track = TechnicalTrack.FULLSTACK
            evidence["technical_track"] = ["description_frontend_and_backend_evidence"]

    structured_remote = bool(re.search(
        r"\b(remote|telecommute|work from home|home based)\b", clean_workplace, re.I
    ))
    structured_hybrid = bool(re.search(r"\bhybrid\b", clean_workplace, re.I))
    structured_onsite = bool(re.search(
        r"\b(on-?site|in[- ]office|office based)\b", clean_workplace, re.I
    ))
    # A provider's explicit workplace field is stronger than incidental prose
    # such as "remote teams" or the common public fact "Remote: No". Ambiguous
    # structured values (for example "remote or onsite") intentionally fall
    # back to the combined-text classifier.
    if structured_remote and not structured_onsite:
        is_remote = True
    elif (structured_onsite or structured_hybrid) and not structured_remote:
        is_remote = False
    else:
        is_remote = bool(_REMOTE.search(all_text))
    if is_remote and _INDIA.search(clean_location):
        workplace_scope = WorkplaceScope.INDIA_REMOTE
        india_eligible = True
        evidence["workplace_scope"] = ["remote_india_location"]
    elif is_remote and _WORLDWIDE.search(clean_location):
        workplace_scope = WorkplaceScope.WORLDWIDE_REMOTE
        india_eligible = True
        evidence["workplace_scope"] = ["worldwide_remote_location"]
    elif is_remote and _RESTRICTED.search(all_text):
        workplace_scope = WorkplaceScope.RESTRICTED_REMOTE
        india_eligible = False
        evidence["workplace_scope"] = ["remote_country_restriction"]
    elif is_remote:
        title_and_location = f"{clean_title}\n{clean_location}"
        remaining_location = _GENERIC_REMOTE_LOCATION.sub(" ", clean_location)
        remaining_location = re.sub(r"[^a-z0-9]+", " ", remaining_location, flags=re.I).strip()
        if _EXCLUDED_REMOTE_REGION.search(title_and_location):
            workplace_scope = WorkplaceScope.RESTRICTED_REMOTE
            india_eligible = False
            evidence["workplace_scope"] = ["explicit_non_india_remote_region"]
        elif remaining_location and _OUTSIDE_INDIA.search(clean_location):
            workplace_scope = WorkplaceScope.RESTRICTED_REMOTE
            india_eligible = False
            evidence["workplace_scope"] = ["explicit_non_india_remote_location"]
        elif _REMOTE_REGION.search(title_and_location):
            workplace_scope = WorkplaceScope.REGION_REMOTE
            india_eligible = False
            evidence["workplace_scope"] = ["remote_region_requires_review"]
            unknowns.append("region_remote_eligibility_unknown")
        elif remaining_location:
            workplace_scope = WorkplaceScope.RESTRICTED_REMOTE
            india_eligible = False
            evidence["workplace_scope"] = ["explicit_non_india_remote_location"]
        elif _WORLDWIDE.search(clean_description):
            workplace_scope = WorkplaceScope.WORLDWIDE_REMOTE
            india_eligible = True
            evidence["workplace_scope"] = ["worldwide_remote_description"]
        else:
            workplace_scope = WorkplaceScope.UNKNOWN
            india_eligible = False
            evidence["workplace_scope"] = ["remote_without_hiring_geography"]
            unknowns.append("remote_geography_unknown")
    elif _INDIA.search(clean_location):
        hybrid = structured_hybrid or bool(re.search(r"\bhybrid\b", all_text, re.I))
        workplace_scope = WorkplaceScope.INDIA_HYBRID if hybrid else WorkplaceScope.INDIA_ONSITE
        india_eligible = True
        evidence["workplace_scope"] = ["india_location", "hybrid_signal" if hybrid else "onsite_default"]
    elif clean_location:
        workplace_scope = WorkplaceScope.OUTSIDE_INDIA_ONSITE
        india_eligible = False
        evidence["workplace_scope"] = [
            "known_outside_india_location" if _OUTSIDE_INDIA.search(clean_location)
            else "non_india_location"
        ]
    else:
        workplace_scope = WorkplaceScope.UNKNOWN
        india_eligible = False
        evidence["workplace_scope"] = ["location_scope_unresolved"]
        unknowns.append("workplace_scope_unknown")

    return OpportunityClassification(
        opportunity_type=opportunity_type,
        technical_track=technical_track,
        workplace_scope=workplace_scope,
        india_eligible=india_eligible,
        evidence=evidence,
        unknowns=unknowns,
    )
