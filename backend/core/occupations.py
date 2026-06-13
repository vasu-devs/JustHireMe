"""Field-agnostic occupation and employment vocabularies.

Shared across discovery (lead scoring / role detection) and profile ingestion
(deterministic résumé parsing) so every layer recognizes a real professional
role in ANY field — healthcare, trades, business, education, creative, science,
public service, software — not just tech. Lives in ``core`` because both the
``discovery`` and ``profile`` packages need it and neither may import the other.

Kept deliberately broad-but-finite: enough coverage to recognize the great
majority of real job titles, without trying to enumerate every occupation on
Earth (that would add noise). Structure-based heuristics handle the long tail.
"""

from __future__ import annotations

# Employment-structure terms: domain-neutral signals that a text describes a job.
EMPLOYMENT_TERMS: tuple[str, ...] = (
    "full-time", "full time", "part-time", "part time", "contract",
    "permanent", "temporary", "internship", "apprenticeship", "salary",
    "wage", "hourly", "per hour", "per year", "per annum", "benefits",
    "shift", "responsibilities", "qualifications", "requirements",
    "job description", "position", "vacancy", "opening", "we are looking for",
    "looking for", "join our team", "join the team",
)

# Occupation nouns across major fields. Not exhaustive by design.
OCCUPATION_TERMS: tuple[str, ...] = (
    # tech
    "engineer", "developer", "programmer", "designer", "analyst", "scientist",
    "administrator", "architect",
    # healthcare
    "nurse", "doctor", "physician", "therapist", "technician", "pharmacist",
    "caregiver", "dentist", "paramedic", "surgeon", "practitioner",
    # trades / labor
    "welder", "electrician", "plumber", "carpenter", "mechanic", "machinist",
    "driver", "operator", "fabricator", "installer",
    # business / office
    "accountant", "bookkeeper", "manager", "coordinator", "specialist",
    "consultant", "associate", "assistant", "clerk", "officer", "executive",
    "representative", "agent", "supervisor", "director", "controller",
    # education / public / service
    "teacher", "tutor", "instructor", "professor", "lecturer", "trainer",
    "chef", "cook", "baker", "barista", "server", "bartender", "housekeeper",
    "stylist", "barber", "cleaner", "guard", "receptionist",
    # creative / marketing / legal / science
    "writer", "editor", "translator", "photographer", "marketer", "recruiter",
    "lawyer", "paralegal", "attorney", "auditor", "surveyor", "researcher",
    "nutritionist", "counselor", "social worker",
)
