from __future__ import annotations

import re

import pytest

from core.taxonomy import TECH_TAXONOMY
from opportunities.eligibility import (
    CandidateConstraints,
    Decision,
    DegreeLevel,
    UnknownCompensationPolicy,
    _contains_bounded_alias,
    _graduation_years,
    evaluate_applicability,
)
from opportunities.safety import PaidStatus
from opportunities.taxonomy import OpportunityType, TechnicalTrack, WorkplaceScope


CANDIDATE = CandidateConstraints(
    candidate_id="friend-1",
    home_country="IN",
    graduation_year=2027,
    currently_enrolled=True,
    current_degree_level=DegreeLevel.BACHELORS,
    accepted_india_cities=["Bengaluru", "Hyderabad", "Pune"],
)


def _evaluate(title: str, description: str, location: str):
    return evaluate_applicability(
        title=title,
        description=description,
        location=location,
        candidate=CANDIDATE,
        source_observed_active=True,
    )


def test_worldwide_remote_technical_internship_can_apply() -> None:
    result = _evaluate(
        "Machine Learning Intern",
        "Paid remote internship open worldwide for enrolled computing students.",
        "Remote — Worldwide",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.workplace_scope == WorkplaceScope.WORLDWIDE_REMOTE
    assert result.india_eligible is True


def test_remote_dehradun_is_india_eligible() -> None:
    result = _evaluate(
        "Founding Full Stack Engineer (Intern to FTE)",
        "Paid internship with an explicit conversion path to full-time employment.",
        "Remote; Dehradun, India",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.workplace_scope == WorkplaceScope.INDIA_REMOTE


def test_mixed_designer_and_flutter_developer_title_remains_technical_entry_level() -> None:
    result = _evaluate(
        "UI/UX Designer & Flutter Developer",
        "Paid role deliberately open to freshers and engineers with 0–2 years of experience.",
        "Remote; Mumbai, India",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.opportunity_type == OpportunityType.ENTRY_LEVEL_FULL_TIME
    assert result.technical_track == TechnicalTrack.MOBILE


@pytest.mark.parametrize(
    "title",
    [
        "Senior Product Designer, Developer Success",
        "Mechanical Engineer, Soft Goods Design",
        "Product Sales Engineer, OpenRoads Designer",
    ],
)
def test_incidental_design_and_engineer_words_do_not_bypass_nontechnical_titles(title: str) -> None:
    result = _evaluate(
        title,
        "Requires 6 years of experience building customer-facing programs.",
        "San Francisco, United States",
    )
    assert result.decision == Decision.SKIP
    assert result.technical_track == TechnicalTrack.NON_TECHNICAL


def test_bachelors_candidate_is_blocked_from_masters_or_doctorate_internship() -> None:
    result = _evaluate(
        "Research Sciences Intern",
        "Required qualifications: Currently pursuing a Master's or a Doctorate Degree in Computer Science.",
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.required_degree_level == DegreeLevel.MASTERS
    assert "degree_level_requirement" in result.hard_blockers
    assert result.evidence["degree_requirement"] == [
        "minimum:masters",
        "candidate:bachelors",
    ]


def test_mtech_only_constraint_in_title_blocks_btech_candidate() -> None:
    result = _evaluate(
        "AI Research Intern - Only MTech students will be eligible",
        "Work on applied machine learning research with the engineering team.",
        "Remote, India",
    )

    assert result.decision == Decision.SKIP
    assert result.required_degree_level == DegreeLevel.MASTERS
    assert "degree_level_requirement" in result.hard_blockers


def test_unknown_candidate_degree_requires_review_for_explicit_degree_requirement() -> None:
    candidate = CANDIDATE.model_copy(update={"current_degree_level": DegreeLevel.UNKNOWN})
    result = evaluate_applicability(
        title="Machine Learning Intern",
        description="Applicants must hold a Master's degree in Computer Science.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )

    assert result.decision == Decision.NEEDS_REVIEW
    assert result.required_degree_level == DegreeLevel.MASTERS
    assert "candidate_degree_level_unknown" in result.unknowns


def test_lower_degree_alternative_and_preferred_degree_do_not_block_bachelors() -> None:
    alternative = _evaluate(
        "Software Engineering Intern",
        "Currently pursuing a Bachelor's or Master's degree in Computer Science.",
        "Bengaluru, India",
    )
    preferred = _evaluate(
        "Software Engineering Intern",
        "Bachelor's degree required. Master's degree preferred.",
        "Bengaluru, India",
    )

    assert alternative.decision == Decision.APPLY_NOW
    assert alternative.required_degree_level == DegreeLevel.BACHELORS
    assert preferred.decision == Decision.APPLY_NOW
    assert preferred.required_degree_level == DegreeLevel.BACHELORS


def test_master_as_a_verb_is_not_a_degree_requirement() -> None:
    result = _evaluate(
        "Android Engineer Intern",
        "You have the drive to master the domain knowledge required to make those calls.",
        "Remote, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.required_degree_level == DegreeLevel.UNKNOWN


def test_technical_residency_with_explicit_final_year_internship_evidence_is_eligible() -> None:
    result = _evaluate(
        "AI/Data Resident",
        "A paid six month remote internship for final-year university students in Computer Science.",
        "India - Remote",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.opportunity_type == OpportunityType.INTERNSHIP
    assert result.technical_track == TechnicalTrack.AI_ML
    assert result.evidence["opportunity_type"] == [
        "early_career_program_with_internship_evidence"
    ]


def test_resident_engineer_is_not_early_career_without_program_evidence() -> None:
    result = _evaluate(
        "Resident Software Engineer",
        "Deploy enterprise software at customer sites. Five years of experience required.",
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.opportunity_type == OpportunityType.OTHER
    assert "not_early_career" in result.hard_blockers


def test_campus_hire_is_classified_as_new_grad() -> None:
    result = _evaluate(
        "2026 Campus Hire - Software Engineer",
        "College graduates build C++ systems and computer-vision software.",
        "Bangalore, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.opportunity_type == OpportunityType.NEW_GRAD


def test_underscored_qualcomm_software_intern_is_classified_and_applicable() -> None:
    result = _evaluate(
        "Interim Engineering Intern_2027_SW",
        "Engineering - Software. Bachelor's Computer Science students design embedded software.",
        "Hyderabad, Telangana, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.opportunity_type == OpportunityType.INTERNSHIP
    assert result.technical_track == TechnicalTrack.SOFTWARE


def test_underscored_qualcomm_campus_hire_is_new_grad_software() -> None:
    result = _evaluate(
        "2027 Campus Hire_Associate Engineer_SW",
        "Software Engineering role for 2027 campus graduates with a Bachelor's in Computer Science.",
        "Hyderabad, Telangana, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.opportunity_type == OpportunityType.NEW_GRAD
    assert result.technical_track == TechnicalTrack.SOFTWARE


def test_generic_technical_role_with_bounded_experience_becomes_strong_stretch() -> None:
    result = _evaluate(
        "Software Engineer - Release Infrastructure",
        "Requires 1–4 years of hands-on experience building Python services and CI/CD systems.",
        "India, Bengaluru",
    )

    assert result.decision == Decision.STRONG_STRETCH
    assert result.opportunity_type == OpportunityType.STRETCH_FULL_TIME
    assert result.minimum_experience_years == 1


def test_product_and_company_age_do_not_override_actual_experience_requirement() -> None:
    result = _evaluate(
        "Full-Stack Software Engineer",
        (
            "We integrate software built 20-40 years ago. The founders worked together "
            "for 12 years and spent 3 years building the platform. Requirements: "
            "back-end/full-stack engineer with 1-4 years experience; exceptional college "
            "graduates with strong internship experience are welcome."
        ),
        "Bengaluru, India",
    )

    assert result.decision == Decision.STRONG_STRETCH
    assert result.minimum_experience_years == 1


def test_country_only_india_onsite_requires_city_review_when_candidate_selected_cities() -> None:
    result = _evaluate(
        "Software Engineer I",
        "Build paid Python and SQL services for production customers.",
        "India",
    )

    assert result.decision == Decision.NEEDS_REVIEW
    assert result.workplace_scope == WorkplaceScope.INDIA_ONSITE
    assert "india_city_unknown" in result.unknowns
    assert result.evidence["india_city_unknown"] == [
        "accepted:['bengaluru', 'hyderabad', 'pune']",
        "posting:country_only",
    ]


def test_mechanical_engineer_is_not_rescued_by_cloud_description() -> None:
    result = _evaluate(
        "Mechanical Engineer - Wearable Systems",
        "Requires 1-3 years designing hardware connected to cloud software and AWS services.",
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
    assert "non_technical_role" in result.hard_blockers


def test_four_year_minimum_does_not_become_bounded_stretch() -> None:
    result = _evaluate(
        "Software Engineer",
        "Requires 4–6 years of hands-on experience building Python services.",
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.opportunity_type == OpportunityType.OTHER
    assert "experience_requirement" in result.hard_blockers


def test_domain_expert_is_not_promoted_by_ai_description_mentions() -> None:
    result = _evaluate(
        "Data Domain Expert",
        "Requires 1-3 years of manufacturing experience. Label examples for an AI team.",
        "Bengaluru, India",
    )

    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
    assert result.decision == Decision.SKIP


def test_data_qa_associate_with_zero_to_two_years_is_entry_level() -> None:
    result = _evaluate(
        "Data QA Associate",
        "Computer Science preferred; 0-2 years of data QA experience. Use SQL and Python.",
        "Remote - India",
    )

    assert result.opportunity_type == OpportunityType.ENTRY_LEVEL_FULL_TIME
    assert result.decision == Decision.APPLY_NOW


def test_structured_zero_to_one_experience_makes_technical_role_entry_level() -> None:
    result = _evaluate(
        "Full Stack Developer",
        "Build TypeScript and Python services. Experience: 0-1 year",
        "Pune, India",
    )

    assert result.opportunity_type == OpportunityType.ENTRY_LEVEL_FULL_TIME
    assert result.minimum_experience_years == 0
    assert result.decision == Decision.APPLY_NOW


def test_structured_one_to_three_experience_makes_technical_role_a_stretch() -> None:
    result = _evaluate(
        "DevOps Engineer",
        "Operate AWS and Kubernetes platforms. Experience: 1-3 years",
        "Pune, India",
    )

    assert result.opportunity_type == OpportunityType.STRETCH_FULL_TIME
    assert result.minimum_experience_years == 1
    assert result.decision == Decision.STRONG_STRETCH


def test_zero_year_signal_is_not_mislabeled_as_an_experience_blocker() -> None:
    result = _evaluate(
        "Functional Analyst",
        "Document workflows. Experience: 0-1 year",
        "Pune, India",
    )

    assert result.opportunity_type == OpportunityType.OTHER
    assert "experience_requirement" not in result.hard_blockers
    assert "not_early_career" in result.hard_blockers


def test_plural_intern_title_is_an_internship() -> None:
    result = _evaluate(
        "AI Interns",
        "Build machine-learning systems with Python. Paid internship.",
        "Pune, India",
    )

    assert result.opportunity_type == OpportunityType.INTERNSHIP
    assert result.decision == Decision.APPLY_NOW


def test_structured_internship_type_requires_a_technical_title() -> None:
    technical = _evaluate(
        "AI Engineer",
        "Build Python ML systems. Employment type: Internship",
        "Pune, India",
    )
    nontechnical = _evaluate(
        "HR Executive",
        "Recruit candidates. Employment type: Internship",
        "Pune, India",
    )

    assert technical.opportunity_type == OpportunityType.INTERNSHIP
    assert technical.decision == Decision.APPLY_NOW
    assert nontechnical.opportunity_type == OpportunityType.OTHER
    assert nontechnical.decision == Decision.SKIP


def test_fresher_or_up_to_one_year_is_not_treated_as_one_year_minimum() -> None:
    result = _evaluate(
        "Intern - Enterprise Data Analysis",
        (
            "Experience: Fresher or up to 1 year in any field. "
            "Experience: 0 - 1 year. Build Python data pipelines on AWS. Paid stipend."
        ),
        "Mumbai, India",
    )

    assert result.minimum_experience_years == 0
    assert "experience_stretch" not in result.evidence


def test_explicit_minimum_and_maximum_uses_the_minimum_experience() -> None:
    result = _evaluate(
        "Software Development Engineer",
        (
            "Requirements Experience: A minimum of 2 years and a maximum of 5 years "
            "of professional experience in software development. Build Python services."
        ),
        "Hyderabad, India",
    )

    assert result.minimum_experience_years == 2
    assert result.decision == Decision.STRONG_STRETCH


def test_data_analyst_title_outranks_incidental_ai_description_language() -> None:
    result = _evaluate(
        "Data Analyst / DA-1",
        "Requires 0-2 years. Analyze dashboards and support an AI-powered fintech product.",
        "Bengaluru, India",
    )

    assert result.technical_track == TechnicalTrack.DATA
    assert result.decision == Decision.APPLY_NOW


def test_plain_qa_intern_uses_qa_track_despite_incidental_ai_language() -> None:
    result = _evaluate(
        "QA Intern/ Consultant",
        "Test an analytics and AI product using SQL, Python, and software testing.",
        "Pune, India",
    )

    assert result.opportunity_type == OpportunityType.INTERNSHIP
    assert result.technical_track == TechnicalTrack.QA_AUTOMATION
    assert result.decision == Decision.APPLY_NOW


def test_ai_gtm_intern_is_not_misclassified_as_a_cse_internship() -> None:
    result = _evaluate(
        "AI GTM Intern",
        "Own go-to-market campaigns for an AI software company. Paid internship.",
        "Bengaluru, India",
    )

    assert result.opportunity_type == OpportunityType.INTERNSHIP
    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
    assert result.decision == Decision.SKIP


def test_nonsoftware_quality_assurance_role_is_not_promoted_to_cse() -> None:
    result = _evaluate(
        "Quality Assurance Advisor, Sterility Assurance",
        "Advise on pharmaceutical sterility, laboratory compliance, and clinical quality.",
        "Bengaluru, India",
    )

    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
    assert result.decision == Decision.SKIP


def test_sparse_qa_title_stays_unknown_instead_of_inventing_software_scope() -> None:
    result = _evaluate(
        "Quality Assurance Intern",
        "Assist the quality analyst and maintain documentation.",
        "Pune, India",
    )

    assert result.technical_track == TechnicalTrack.UNKNOWN
    assert result.decision == Decision.SKIP


def test_qa_engineer_title_is_sufficient_software_qa_evidence() -> None:
    result = _evaluate(
        "Senior QA Engineer",
        "Own the quality function and work with the product team.",
        "Pune, India",
    )

    assert result.technical_track == TechnicalTrack.QA_AUTOMATION


def test_engineer_on_go_to_market_data_team_remains_technical() -> None:
    result = _evaluate(
        "Systems Engineer - Go-To-Market Data Team",
        "Requires 2 years of Python, SQL, data pipeline, and software systems experience.",
        "Bengaluru, India",
    )

    assert result.technical_track != TechnicalTrack.NON_TECHNICAL
    assert result.opportunity_type == OpportunityType.STRETCH_FULL_TIME


@pytest.mark.parametrize("region", ["AMERICAS", "EMEA"])
def test_non_india_region_in_remote_title_blocks_role(region: str) -> None:
    result = _evaluate(
        f"Support Engineer ({region})",
        "Requires 2 years of software troubleshooting experience. This is a remote role.",
        "Remote",
    )

    assert result.workplace_scope == WorkplaceScope.RESTRICTED_REMOTE
    assert result.decision == Decision.SKIP


def test_apac_remote_title_requires_geography_review() -> None:
    result = _evaluate(
        "Support Engineer (APAC)",
        "Requires 2 years of software troubleshooting experience. This is a remote role.",
        "Remote",
    )

    assert result.workplace_scope == WorkplaceScope.REGION_REMOTE
    assert result.decision == Decision.NEEDS_REVIEW
    assert "region_remote_eligibility_unknown" in result.unknowns


def test_explicit_non_india_location_outranks_apac_title() -> None:
    result = _evaluate(
        "Solution Engineer APAC",
        "This is a remote role.",
        "Australia",
    )

    assert result.workplace_scope == WorkplaceScope.RESTRICTED_REMOTE
    assert result.decision == Decision.SKIP


@pytest.mark.parametrize("title", ["Technical Writer - PostgreSQL", "AI Trainer - Freelance Data Annotator"])
def test_adjacent_non_cse_roles_do_not_enter_stretch_queue(title: str) -> None:
    result = _evaluate(
        title,
        "Requires 2 years of experience working with AI and software engineering teams.",
        "Remote - India",
    )

    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
    assert result.decision == Decision.SKIP


def test_remote_us_only_never_becomes_india_eligible() -> None:
    result = _evaluate(
        "Software Engineer Intern",
        "Remote internship. Applicants must reside in the United States and have unrestricted US work authorization.",
        "Remote — United States only",
    )
    assert result.decision == Decision.SKIP
    assert result.india_eligible is False
    assert {"country_restriction", "work_authorization"} <= set(result.hard_blockers)


def test_senior_role_cannot_be_reclassified_by_intern_word_in_description() -> None:
    result = _evaluate(
        "Senior Backend Engineer",
        "Seven years required. Mentor interns and junior engineers.",
        "Bengaluru, India",
    )
    assert result.decision == Decision.SKIP
    assert result.hard_blockers == ["experience_requirement"]


def test_abbreviated_senior_title_cannot_be_reclassified_by_engineer_level_one() -> None:
    result = _evaluate(
        "Sr. Data Engineer I",
        "Build Python and SQL data systems.",
        "Remote",
    )
    assert result.decision == Decision.SKIP
    assert "experience_requirement" in result.hard_blockers


def test_remote_without_hiring_geography_requires_review() -> None:
    result = _evaluate(
        "Software Developer Intern",
        "Fully remote paid software internship. No hiring countries are stated.",
        "Remote",
    )
    assert result.decision == Decision.NEEDS_REVIEW
    assert "remote_geography_unknown" in result.unknowns


def test_explicit_foreign_remote_location_overrides_worldwide_marketing_copy() -> None:
    result = _evaluate(
        "Software Engineer I, Backend",
        "Join a worldwide company building remote-first Python services.",
        "Remote Spain",
    )
    assert result.decision == Decision.SKIP
    assert result.workplace_scope == WorkplaceScope.RESTRICTED_REMOTE
    assert "country_restriction" in result.hard_blockers


def test_emea_remote_is_not_treated_as_worldwide() -> None:
    result = _evaluate(
        "Graduate Software Engineer",
        "Build software for customers worldwide from our distributed team.",
        "Home Based - EMEA",
    )
    assert result.decision == Decision.SKIP
    assert result.workplace_scope == WorkplaceScope.RESTRICTED_REMOTE


def test_any_non_india_onsite_location_is_blocked_even_if_country_is_abbreviated() -> None:
    result = _evaluate(
        "Software Engineer Intern (Winter 2027)",
        "Paid software internship for enrolled students.",
        "US",
    )
    assert result.decision == Decision.SKIP
    assert result.workplace_scope == WorkplaceScope.OUTSIDE_INDIA_ONSITE


def test_fee_deposit_and_future_stipend_remain_blocked() -> None:
    result = _evaluate(
        "AI Engineer Intern",
        "Stipend after training. Candidates must first pay a refundable INR 25,000 training and security deposit.",
        "Remote — India",
    )
    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.SUSPICIOUS
    assert {"training_fee", "security_deposit"} <= set(result.safety_blockers)


def test_course_curriculum_presented_as_internship_is_blocked() -> None:
    result = _evaluate(
        "AI - ML Engineer - Intern",
        (
            "What You Will Learn. This internship equips students through training and labs. "
            "Participants will gain practical skills in Python, TensorFlow, and model deployment."
        ),
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.SUSPICIOUS
    assert result.safety_blockers == ["training_presented_as_internship"]


def test_explicit_internship_training_program_is_blocked_despite_responsibility_copy() -> None:
    result = _evaluate(
        "AI - Data Analyst - Intern",
        (
            "Join our immersive AI Data Analyst internship training program. "
            "Responsibilities include completing labs and guided portfolio projects."
        ),
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.SUSPICIOUS
    assert result.safety_blockers == ["training_presented_as_internship"]


def test_paid_employer_internship_can_include_learning_language() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        (
            "We are hiring a paid intern to join our engineering team. Key responsibilities "
            "include building Python APIs. What You Will Learn: production testing and deployment."
        ),
        "Bengaluru, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert "training_presented_as_internship" not in result.safety_blockers


def test_conditional_performance_stipend_is_not_claimed_as_confirmed_paid() -> None:
    result = _evaluate(
        "Full Stack Developer Intern",
        "Remote internship with a potential stipend based on performance and contributions.",
        "Remote - worldwide; applicants from India may apply.",
    )

    assert result.paid_status == PaidStatus.UNKNOWN


def test_delayed_performance_stipend_is_not_claimed_as_confirmed_paid() -> None:
    result = _evaluate(
        "Software Engineer Intern (Remote)",
        "Flexible internship. Good stipend available based on 1 month's performance.",
        "Indore, India",
    )

    assert result.paid_status == PaidStatus.UNKNOWN


def test_mandatory_tenure_completion_benefit_is_blocked() -> None:
    result = _evaluate(
        "AI Engineer",
        (
            "Six month internship with a ₹1,00,000 Completion Benefit upon successful "
            "completion of the mandatory tenure, subject to satisfactory performance "
            "and attendance."
        ),
        "Mumbai, India",
    )

    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.SUSPICIOUS
    assert result.safety_blockers == ["conditional_completion_compensation"]


def test_monthly_stipend_plus_completion_bonus_remains_paid() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        (
            "Paid internship with a monthly stipend of INR 20,000 and an additional "
            "completion bonus payable after successful completion."
        ),
        "Bengaluru, India",
    )

    assert result.decision == Decision.APPLY_NOW
    assert result.paid_status == PaidStatus.PAID
    assert "conditional_completion_compensation" not in result.safety_blockers


def test_internship_program_mentor_is_not_classified_as_an_intern() -> None:
    result = _evaluate(
        "Mentor- Java Full Stack (Internship Program)",
        "Mentor interns in Java and React. Minimum 3 years of professional experience.",
        "Bengaluru, India",
    )

    assert result.opportunity_type == OpportunityType.OTHER
    assert result.decision == Decision.SKIP
    assert "experience_requirement" in result.hard_blockers


def test_location_adjusted_compensation_with_numeric_rate_remains_paid() -> None:
    result = _evaluate(
        "Software Engineer Intern",
        "Compensation may be adjusted by work location. Estimated hourly rate of $27/hr.",
        "Remote - United States",
    )

    assert result.paid_status == PaidStatus.PAID


def test_unpaid_bond_and_exit_penalty_are_independent_blockers() -> None:
    result = _evaluate(
        "Full Stack Intern",
        "Six-month unpaid internship. A two-year service bond and exit penalty apply.",
        "Pune, India",
    )
    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.UNPAID
    assert result.safety_blockers == ["unpaid", "service_bond", "exit_penalty"]


def test_service_lock_in_is_treated_as_an_employment_bond() -> None:
    result = _evaluate(
        "Software Engineer Intern - Backend",
        "Paid final-year internship. Full-time conversion includes a 2-year service lock-in period.",
        "Bangalore, India",
    )

    assert result.decision == Decision.SKIP
    assert result.safety_blockers == ["service_bond"]


def test_generic_campus_program_requires_explicit_internship_and_technical_evidence() -> None:
    technical = _evaluate(
        "Lilly Campus Program",
        "Lilly India Internship Program. Tech based roles include AI/ML, automation, "
        "cybersecurity, database operations, and statistical programming.",
        "Gurgaon, India",
    )
    nontechnical = _evaluate(
        "Campus Program",
        "India Internship Program with roles in marketing and human resources.",
        "Gurgaon, India",
    )

    assert technical.opportunity_type == OpportunityType.INTERNSHIP
    assert technical.technical_track == TechnicalTrack.AI_ML
    assert "not_early_career" not in technical.hard_blockers
    assert nontechnical.opportunity_type == OpportunityType.INTERNSHIP
    assert nontechnical.technical_track == TechnicalTrack.UNKNOWN
    assert "technical_track_unknown" in nontechnical.hard_blockers


def test_volunteer_internship_is_explicit_unpaid_work() -> None:
    result = _evaluate(
        "Intern System Administrator (Volunteer)",
        "Join a volunteer-driven nonprofit and maintain its software systems.",
        "Remote - India",
    )

    assert result.decision == Decision.SKIP
    assert result.paid_status == PaidStatus.UNPAID
    assert result.safety_blockers == ["unpaid"]
    assert result.evidence["unpaid"] == ["explicit_volunteer_role_signal"]


def test_india_onsite_city_must_match_candidate_preferences() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        "Paid software internship for 2027 graduates.",
        "Chennai, India",
    )
    assert result.decision == Decision.SKIP
    assert result.hard_blockers == ["india_city_not_accepted"]


def test_bangalore_and_bengaluru_are_the_same_city() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        "Paid software internship for 2027 graduates.",
        "Bangalore, India",
    )
    assert result.decision == Decision.APPLY_NOW


def test_known_provider_banglore_typo_is_still_classified_as_bengaluru() -> None:
    result = _evaluate(
        "Quantitative Developer Intern",
        "Paid Python internship for enrolled engineering students.",
        "Banglore, Karnataka, India",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.workplace_scope == WorkplaceScope.INDIA_ONSITE
    assert result.posting_india_cities == ["bengaluru"]


def test_known_provider_hyderabad_typo_is_still_classified_as_india() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        "Paid software internship for 2027 graduates.",
        "Hyderbad",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.workplace_scope == WorkplaceScope.INDIA_ONSITE
    assert result.posting_india_cities == ["hyderabad"]


def test_distributed_systems_skill_does_not_turn_an_onsite_role_remote() -> None:
    result = _evaluate(
        "[Backend, Onsite] Software Engineering Intern",
        "Paid backend internship building distributed systems and serverless APIs.",
        "Bangalore",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.workplace_scope == WorkplaceScope.INDIA_ONSITE


def test_structured_onsite_overrides_incidental_remote_description_text() -> None:
    result = evaluate_applicability(
        title="Software Engineer II",
        description=(
            "Build agentic AI services with globally distributed remote teams. "
            "Remote: No. Requires 2 years of experience."
        ),
        location="IN-Hyderabad",
        workplace="onsite",
        candidate=CANDIDATE,
        source_observed_active=True,
    )

    assert result.workplace_scope == WorkplaceScope.INDIA_ONSITE
    assert result.india_eligible is True


def test_product_ops_intern_does_not_become_technical_from_ai_buzzwords() -> None:
    result = _evaluate(
        "Product Ops Intern",
        "Paid AI internship coordinating agents, workflows, partner approvals, and operations.",
        "Bengaluru, India",
    )
    assert result.decision == Decision.SKIP
    assert "non_technical_role" in result.hard_blockers


def test_non_technical_early_career_titles_are_not_rescued_by_tech_buzzwords() -> None:
    for title in (
        "SDR Intern - Munich",
        "Intern Workplace & Culture Management (all genders)",
        "Sales Development Representative Intern",
        "Talent Acquisition Intern",
        "LinkedIn Recruitment Internship",
        "Junior Ads Specialist",
        "Junior IT Procurement Specialist",
        "Copywriter Intern",
        "B2B Growth & Demand Generation Intern",
        "Product Led Growth Intern",
        "Operation Intern | India | Remote",
        "Data Entry Intern",
        "Cloud Business Intern Engineering Background",
        "Regulatory Intelligence Intern",
    ):
        result = _evaluate(
            title,
            "Work with software, APIs, Python, AI, data, and engineering teams.",
            "Bengaluru, India",
        )
        assert result.decision == Decision.SKIP
        assert result.technical_track == TechnicalTrack.NON_TECHNICAL
        assert "non_technical_role" in result.hard_blockers


def test_generic_internship_is_not_rescued_by_technical_company_description() -> None:
    result = _evaluate(
        "India Intern",
        "Support a global company building AI, software, data, and cloud platforms.",
        "India",
    )
    assert result.decision == Decision.SKIP
    assert result.technical_track == TechnicalTrack.UNKNOWN
    assert "technical_track_unknown" in result.hard_blockers


def test_vague_but_technical_title_can_use_description_track_evidence() -> None:
    result = _evaluate(
        "Research Intern",
        "Build computer vision and machine learning models in Python.",
        "Remote - Worldwide",
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.technical_track == TechnicalTrack.AI_ML


def test_sde_and_swe_acronyms_are_software_roles() -> None:
    sde = _evaluate(
        "SDE I",
        (
            "Full-time role for B Tech Computer Science candidates with 0-1 years in software "
            "development. Build REST APIs in Java, TypeScript, or Python under mentorship."
        ),
        "Bangalore, India",
    )
    swe = _evaluate(
        "SWE Intern",
        "Paid internship shipping production code with an engineering mentor.",
        "Remote - India",
    )

    assert sde.opportunity_type == OpportunityType.ENTRY_LEVEL_FULL_TIME
    assert sde.technical_track == TechnicalTrack.FULLSTACK
    assert sde.decision == Decision.APPLY_NOW
    assert "technical_track_unknown" not in sde.hard_blockers
    assert swe.opportunity_type == OpportunityType.INTERNSHIP
    assert swe.technical_track == TechnicalTrack.SOFTWARE
    assert swe.decision == Decision.APPLY_NOW


def test_explicit_integration_architecture_description_resolves_generic_support_title() -> None:
    result = _evaluate(
        "Service Delivery Management Consultant 1- Support",
        (
            "Support Integration Architect. Troubleshoot complex technical integration issues. "
            "At least 2 years combined related experience and education, including 1 year of "
            "healthcare information technology support."
        ),
        "Bengaluru, India",
    )
    assert result.technical_track == TechnicalTrack.CLOUD_DEVOPS
    assert result.opportunity_type == OpportunityType.OTHER
    assert result.decision == Decision.SKIP
    assert "technical_track_unknown" not in result.hard_blockers


def test_explicit_genai_builder_intern_remains_technical() -> None:
    result = _evaluate(
        "GenAI Product Builder Intern",
        "Paid internship building Python APIs, LLM agents, and production software.",
        "Bengaluru, India",
    )
    assert result.decision == Decision.APPLY_NOW


def test_required_language_groups_support_and_and_or_semantics() -> None:
    english_only = CANDIDATE.model_copy(update={"spoken_languages": ["English"]})
    mandarin = evaluate_applicability(
        title="Test Development Engineer Intern",
        description="Language Skills: Fluent Mandarin & English. Build Python test automation.",
        location="Remote - India",
        candidate=english_only,
        source_observed_active=True,
    )
    ukrainian_or_russian = evaluate_applicability(
        title="Junior Technical Support Engineer",
        description=(
            "Languages: Intermediate English for technical documentation; "
            "fluent Ukrainian or Russian for daily communication. Diagnose REST APIs."
        ),
        location="Remote - India",
        candidate=english_only,
        source_observed_active=True,
    )
    assert mandarin.decision == Decision.SKIP
    assert mandarin.required_language_groups == [["Mandarin"], ["English"]]
    assert mandarin.evidence["language_requirement"] == ["one_of:Mandarin"]
    assert ukrainian_or_russian.decision == Decision.SKIP
    assert ukrainian_or_russian.required_language_groups == [["Russian", "Ukrainian"]]


def test_optional_language_does_not_block_an_english_speaker() -> None:
    result = evaluate_applicability(
        title="Junior Network Analyst",
        description=(
            "Troubleshoot network systems and software. "
            "Fluent in English is a requirement. "
            "Fluency in Arabic, French, German, Spanish, or Turkish is an asset."
        ),
        location="Remote - India",
        candidate=CANDIDATE.model_copy(update={"spoken_languages": ["English"]}),
        source_observed_active=True,
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.required_language_groups == [["English"]]


def test_career_growth_and_hiring_confidence_are_evidence_based() -> None:
    result = _evaluate(
        "Backend Engineering Intern",
        "Paid software internship with a dedicated mentor. Own a production feature end-to-end and earn a PPO based on performance.",
        "Bengaluru, India",
    )
    assert result.decision == Decision.APPLY_NOW
    assert {"mentorship", "production_impact", "end_to_end_ownership", "conversion_path"} <= set(result.career_signals)
    assert result.career_growth_score >= 80
    assert result.hiring_confidence_score >= 85
    assert result.priority_score >= 90


def test_candidate_minimum_stipend_and_maximum_duration_are_hard_constraints() -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_inr": 30_000,
        "maximum_internship_months": 6,
    })
    result = evaluate_applicability(
        title="Software Engineering Intern",
        description="Paid 9-month software internship. Stipend ₹20,000 per month.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    assert result.decision == Decision.SKIP
    assert {"compensation_below_minimum", "internship_duration"} <= set(result.hard_blockers)
    assert result.evidence["compensation_below_minimum"] == [
        "observed_monthly_inr:20000",
        "candidate_minimum_inr:30000",
    ]
    assert result.monthly_compensation_inr == [20_000]
    assert result.internship_duration_months == [9]
    assert result.posting_india_cities == ["bengaluru"]


def test_monthly_stipend_range_with_repeated_currency_uses_lower_bound() -> None:
    result = _evaluate(
        "Software Engineering Intern",
        "Paid internship. Stipend: ₹30,000 – ₹50,000 per month.",
        "Bengaluru, India",
    )

    assert result.monthly_compensation_inr == [30_000]


def test_named_external_program_requirement_is_not_presented_as_directly_applicable() -> None:
    result = _evaluate(
        "Technical Support Representative Intern",
        "This role is only open for candidates who have applied under the Prime Minister's "
        "Internship Scheme through their portal. Build and monitor production applications.",
        "Multiple Cities, India",
    )
    assert result.decision == Decision.SKIP
    assert "external_program_restriction" in result.hard_blockers
    assert result.evidence["external_program_restriction"] == [
        "named_external_program_or_portal_required"
    ]


def test_non_inr_monthly_amount_is_not_compared_as_rupees() -> None:
    candidate = CANDIDATE.model_copy(update={"minimum_monthly_compensation_inr": 30_000})
    result = evaluate_applicability(
        title="Software Engineering Intern",
        description="Paid worldwide remote software internship. Compensation is $500 per month.",
        location="Remote — Worldwide",
        candidate=candidate,
        source_observed_active=True,
    )
    assert "compensation_below_minimum" not in result.hard_blockers


@pytest.mark.parametrize(
    ("disclosure", "expected_monthly"),
    [
        ("Compensation is USD 1,500 per month.", 1_500),
        ("Compensation is $1.5k monthly.", 1_500),
        ("Compensation is $24,000 per year.", 2_000),
        ("Compensation is $90k-$120k USD annually.", 7_500),
        ("Compensation is $18-$30 per hour.", 3_120),
    ],
)
def test_usd_compensation_is_normalized_without_fx_conversion(
    disclosure: str,
    expected_monthly: int,
) -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_usd": 1_200,
        "target_monthly_compensation_usd": 2_400,
    })
    result = evaluate_applicability(
        title="Applied AI Engineering Intern",
        description=f"Paid worldwide remote AI internship. {disclosure}",
        location="Remote — Worldwide",
        candidate=candidate,
        source_observed_active=True,
    )
    assert result.monthly_compensation_usd == [expected_monthly]
    assert "compensation_below_minimum" not in result.hard_blockers


def test_compact_inr_lakh_range_is_normalized() -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_inr": 100_000,
        "target_monthly_compensation_inr": 200_000,
    })
    result = evaluate_applicability(
        title="Generative AI Engineering Intern",
        description="Paid internship. Stipend ₹1L-₹2L/month. Mentorship and production ownership.",
        location="Remote - India",
        candidate=candidate,
        source_observed_active=True,
    )

    assert result.monthly_compensation_inr == [100_000]
    assert result.compensation_score == 70
    assert result.target_compensation_met is False


@pytest.mark.parametrize(
    "disclosure",
    [
        "Compensation is up to $25/hr.",
        "The maximum is ₹2L/month.",
    ],
)
def test_upper_bound_only_pay_does_not_satisfy_candidate_floor(disclosure: str) -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_inr": 100_000,
        "target_monthly_compensation_inr": 200_000,
        "minimum_monthly_compensation_usd": 1_200,
        "target_monthly_compensation_usd": 2_400,
        "unknown_compensation_policy": UnknownCompensationPolicy.REVIEW,
    })
    result = evaluate_applicability(
        title="AI Engineering Intern",
        description=f"Worldwide remote paid internship. {disclosure}",
        location="Remote - Worldwide",
        candidate=candidate,
        source_observed_active=True,
    )

    assert result.decision == Decision.NEEDS_REVIEW
    assert result.monthly_compensation_inr == []
    assert result.monthly_compensation_usd == []
    assert result.target_compensation_met is None
    assert result.evidence["compensation_upper_bound_only"] == [
        "maximum_disclosed_without_guaranteed_minimum"
    ]


def test_target_compensation_boosts_priority_and_is_explained() -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_inr": 100_000,
        "target_monthly_compensation_inr": 200_000,
    })
    result = evaluate_applicability(
        title="Generative AI Engineering Intern",
        description="Paid internship shipping production LLM agents. Stipend ₹2,00,000 per month.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    assert result.decision == Decision.APPLY_NOW
    assert result.compensation_score == 100
    assert result.target_compensation_met is True
    assert result.evidence["target_compensation"] == [
        "disclosed_lower_bound_meets_or_exceeds_target"
    ]


@pytest.mark.parametrize(
    ("policy", "decision", "expected_signal"),
    [
        (UnknownCompensationPolicy.ALLOW, Decision.APPLY_NOW, None),
        (UnknownCompensationPolicy.REVIEW, Decision.NEEDS_REVIEW, "compensation_unknown"),
        (UnknownCompensationPolicy.SKIP, Decision.SKIP, "compensation_unknown"),
    ],
)
def test_undisclosed_compensation_obeys_candidate_policy(
    policy: UnknownCompensationPolicy,
    decision: Decision,
    expected_signal: str | None,
) -> None:
    candidate = CANDIDATE.model_copy(update={
        "minimum_monthly_compensation_inr": 100_000,
        "target_monthly_compensation_inr": 200_000,
        "unknown_compensation_policy": policy,
    })
    result = evaluate_applicability(
        title="AI Engineering Intern",
        description="Paid internship building production LLM evaluation systems.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    assert result.decision == decision
    assert result.target_compensation_met is None
    if expected_signal is None:
        assert "compensation_unknown" not in result.unknowns
        assert "compensation_unknown" not in result.hard_blockers
    else:
        assert expected_signal in {*result.unknowns, *result.hard_blockers}


def test_target_compensation_cannot_be_below_hard_floor() -> None:
    with pytest.raises(ValueError, match="INR target compensation must be at least the minimum"):
        CandidateConstraints(
            minimum_monthly_compensation_inr=200_000,
            target_monthly_compensation_inr=100_000,
        )


def test_candidate_specialization_filters_unwanted_tracks_but_keeps_generic_software_roles() -> None:
    candidate = CANDIDATE.model_copy(update={"preferred_technical_tracks": [TechnicalTrack.AI_ML, TechnicalTrack.DATA]})
    frontend = evaluate_applicability(
        title="Frontend Engineering Intern",
        description="Paid React and TypeScript internship for 2027 graduates.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    generic = evaluate_applicability(
        title="Software Engineering Intern",
        description="Paid software internship for 2027 graduates.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    assert frontend.decision == Decision.SKIP
    assert "technical_track_not_preferred" in frontend.hard_blockers
    assert generic.decision == Decision.APPLY_NOW


def test_candidate_can_limit_queue_to_internships_and_remote_work() -> None:
    candidate = CANDIDATE.model_copy(update={
        "accepted_opportunity_types": [OpportunityType.INTERNSHIP],
        "allow_india_onsite": False,
        "allow_india_hybrid": False,
    })
    onsite_intern = evaluate_applicability(
        title="Backend Engineering Intern",
        description="Paid Python internship for 2027 graduates.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    remote_grad = evaluate_applicability(
        title="New Grad Software Engineer",
        description="Paid remote role open worldwide for 2027 graduates.",
        location="Remote — Worldwide",
        candidate=candidate,
        source_observed_active=True,
    )
    assert "workplace_not_accepted" in onsite_intern.hard_blockers
    assert "opportunity_type_not_accepted" in remote_grad.hard_blockers


def test_candidate_fit_uses_traceable_skill_and_project_evidence() -> None:
    candidate = CANDIDATE.model_copy(update={
        "technical_skills": ["Python", "FastAPI", "Docker"],
        "project_keywords": ["REST API", "PostgreSQL"],
    })
    result = evaluate_applicability(
        title="Backend Engineering Intern",
        description="Build Python FastAPI services, REST APIs, PostgreSQL data models, Docker images, and Kubernetes deployments.",
        location="Bengaluru, India",
        candidate=candidate,
        source_observed_active=True,
    )
    assert result.candidate_evidence_missing is False
    assert {"Python", "FastAPI", "REST API", "PostgreSQL", "Docker"} <= set(result.matched_skills)
    assert "Kubernetes" in result.posting_skills
    assert result.candidate_fit_score >= 80
    assert result.evidence["candidate_skill_matches"] == result.matched_skills


def test_technology_alias_matching_preserves_word_boundaries() -> None:
    result = _evaluate(
        "JavaScript Engineering Intern",
        "Build JavaScript applications with reactive state and durable storage.",
        "Bengaluru, India",
    )
    assert "JavaScript" in result.posting_skills
    assert "Java" not in result.posting_skills
    assert "React" not in result.posting_skills
    assert "RAG" not in result.posting_skills


def test_fast_alias_matcher_is_boundary_equivalent_for_every_taxonomy_alias() -> None:
    for aliases in TECH_TAXONOMY.values():
        for alias in aliases:
            lower = alias.lower()
            reference = re.compile(rf"(?<![\w]){re.escape(lower)}(?![\w])")
            for text in (lower, f"({lower})", f"x{lower}", f"{lower}x", f"x{lower}x"):
                assert _contains_bounded_alias(text, lower) is bool(reference.search(text))


def test_fast_graduation_year_extraction_matches_bounded_context_semantics() -> None:
    reference_clause = re.compile(
        r"[^.\n]{0,80}\b(?:graduates?|graduating|graduation|class of|batch)\b[^.\n]{0,80}",
        re.I,
    )
    year = re.compile(r"\b(20[2-4]\d)\b")
    cases = [
        "Open to 2027 graduates in computer science.",
        "Class of 2026 or 2027 may apply.",
        "2025." + ("x" * 50) + " graduating students in 2028.",
        "2026 " + ("x" * 74) + " graduates",
        "2026 " + ("x" * 81) + " graduates",
        "graduates " + ("x" * 74) + " 2029",
        "graduates " + ("x" * 81) + " 2029",
        "Graduation in 2027\nClass of 2028",
        "Intern - Software Developer - 2028 Batch",
        ("ordinary engineering description " * 2_000),
    ]
    for description in cases:
        expected = {
            int(value)
            for clause in reference_clause.findall(description)
            for value in year.findall(clause)
        }
        assert _graduation_years(description) == expected

    overlapping_signals = (
        "Current graduate college student with an expected graduation between "
        "December 2027 and May/June 2028."
    )
    assert _graduation_years(overlapping_signals) == {2027, 2028}


def test_title_only_batch_year_blocks_a_different_graduation_cohort() -> None:
    result = _evaluate(
        "Intern - Software Developer (Product) - 2028 Batch",
        "Build full-stack software products in Python and React.",
        "Gurugram, India",
    )

    assert result.decision == Decision.SKIP
    assert result.graduation_years == [2028]
    assert "graduation_year" in result.hard_blockers
    assert result.evidence["graduation_year"] == ["allowed_years:[2028]"]


def test_data_analytics_intern_is_a_data_role() -> None:
    result = _evaluate(
        "Advanced Data Analytics Intern",
        "Use SQL, Python, and dashboards to analyze customer datasets.",
        "Hyderabad, India",
    )

    assert result.technical_track == TechnicalTrack.DATA
    assert "technical_track_unknown" not in result.hard_blockers


def test_it_administrator_intern_is_a_cloud_devops_role() -> None:
    result = _evaluate(
        "IT Administrator (Intern)",
        "Manage endpoints, software, identity access, networking, and infrastructure automation.",
        "Bengaluru, India",
    )

    assert result.technical_track == TechnicalTrack.CLOUD_DEVOPS
    assert "technical_track_unknown" not in result.hard_blockers


@pytest.mark.parametrize("title", ["AI Program Coordinator Intern", "Design Engineering Intern"])
def test_nontechnical_program_and_design_internships_do_not_enter_the_cse_lane(title: str) -> None:
    result = _evaluate(
        title,
        "Coordinate curriculum delivery and create solar product design documentation.",
        "Bengaluru, India",
    )

    assert result.decision == Decision.SKIP
    assert result.technical_track == TechnicalTrack.NON_TECHNICAL
