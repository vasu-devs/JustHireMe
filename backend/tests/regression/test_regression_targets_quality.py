from regression_support import *  # noqa: F401,F403

class RegressionTests(unittest.TestCase):
    def test_job_targets_only_drop_freelance_sources(self):
        from discovery.targets import job_targets

        targets = job_targets("\n".join([
            "site:linkedin.com/jobs",
            "site:indeed.com/jobs",
            "site:jobs.lever.co",
            "https://remoteok.com/api",
            "site:freelancer.com/projects",
        ]))

        self.assertIn("site:jobs.lever.co", targets)
        self.assertIn("https://remoteok.com/api", targets)
        self.assertIn("site:linkedin.com/jobs", targets)
        self.assertIn("site:indeed.com/jobs", targets)
        self.assertNotIn("site:freelancer.com/projects", targets)

    def test_hn_only_job_targets_are_broadened(self):
        from discovery.targets import job_targets

        targets = job_targets("hn-hiring")

        self.assertIn("hn-hiring", targets)
        self.assertIn("https://remoteok.com/api", targets)
        self.assertIn("https://remotive.com/api/remote-jobs", targets)
        self.assertFalse(any(target.startswith("site:") for target in targets))

    def test_india_job_targets_use_india_only_fallback_and_filter(self):
        from discovery.targets import job_targets

        defaults = job_targets("", "india")
        self.assertIn("site:naukri.com jobs India", defaults)
        self.assertIn("site:foundit.in jobs India", defaults)
        self.assertIn("site:internshala.com/jobs India", defaults)
        self.assertNotIn("software engineer", " ".join(defaults).lower())

        targets = job_targets("\n".join([
            "https://remoteok.com/api",
            "site:jobs.lever.co India",
            "site:cutshort.io/jobs India startup",
        ]), "india")

        self.assertIn("site:jobs.lever.co India", targets)
        self.assertIn("site:cutshort.io/jobs India startup", targets)
        self.assertNotIn("https://remoteok.com/api", targets)

    def test_global_job_targets_are_general_market_defaults(self):
        from discovery.targets import job_targets

        targets = job_targets("", "global")

        # Keyless defaults must be callable feeds, not inert search-engine
        # queries. Company-direct Lever/Greenhouse/Workday coverage is supplied
        # separately by the production company registry.
        self.assertIn("https://remoteok.com/api", targets)
        self.assertIn("https://remotive.com/api/remote-jobs", targets)
        self.assertIn("https://www.arbeitnow.com/api/job-board-api", targets)
        self.assertFalse(any(target.startswith("site:") for target in targets))
        self.assertNotIn("software engineer", " ".join(targets).lower())

    def test_india_query_generation_keeps_location_clause_on_fallback(self):
        from discovery import query_gen

        with mock.patch("llm.call_llm", side_effect=RuntimeError("offline")):
            queries = query_gen.generate(_sample_scoring_profile(), ["site:jobs.lever.co"], "india")

        self.assertEqual(len(queries), 1)
        self.assertIn("site:jobs.lever.co", queries[0])
        self.assertIn("India", queries[0])
        self.assertIn("Indian startup", queries[0])

    def test_query_generation_fallback_is_not_tech_only(self):
        from discovery import query_gen

        profile = {
            "s": "Growth marketing specialist with SEO and lifecycle experience",
            "skills": [{"n": "SEO"}, {"n": "Lifecycle marketing"}],
            "projects": [{"title": "Marketing Site", "stack": ["Analytics", "Content"]}],
            "exp": [{"role": "Growth Marketer"}],
        }

        with mock.patch("llm.call_llm", side_effect=RuntimeError("offline")):
            queries = query_gen.generate(profile, ["site:linkedin.com/jobs"], "global")

        self.assertEqual(len(queries), 1)
        self.assertIn("site:linkedin.com/jobs", queries[0])
        self.assertIn("SEO", queries[0])
        self.assertNotIn("software engineer", queries[0].lower())

    def test_desired_position_is_merged_into_discovery_profile(self):
        from discovery.targets import profile_for_discovery

        profile = {"s": "Experienced with SEO and lifecycle campaigns.", "skills": [{"n": "SEO"}]}
        cfg = {"onboarding_target_role": "Growth Marketing Manager"}

        merged = profile_for_discovery(profile, cfg)

        self.assertIn("Growth Marketing Manager", merged["s"])
        self.assertEqual(merged["desired_position"], "Growth Marketing Manager")

    def test_query_generation_enriches_supported_api_sources_with_profile_terms(self):
        from discovery import query_gen

        profile = {"s": "Growth Marketing Manager", "skills": [{"n": "SEO"}], "projects": []}

        with mock.patch("llm.call_llm", side_effect=RuntimeError("offline")):
            queries = query_gen.generate(
                profile,
                [
                    "https://remotive.com/api/remote-jobs",
                    "https://jobicy.com/api/v2/remote-jobs?count=50",
                    "site:linkedin.com/jobs",
                ],
                "global",
            )

        self.assertIn("https://remotive.com/api/remote-jobs?search=Growth+Marketing+Manager", queries)
        self.assertIn("https://jobicy.com/api/v2/remote-jobs?count=50&tag=Growth+Marketing+Manager", queries)
        self.assertTrue(any(q.startswith("site:linkedin.com/jobs") and "Growth Marketing Manager" in q for q in queries))

    def test_query_generation_enriches_api_sources_without_site_targets(self):
        from discovery import query_gen

        profile = {"s": "Growth Marketing Manager", "skills": [{"n": "SEO"}], "projects": []}

        queries = query_gen.generate(
            profile,
            [
                "https://remotive.com/api/remote-jobs",
                "https://jobicy.com/api/v2/remote-jobs?count=50",
            ],
            "global",
        )

        self.assertEqual(queries, [
            "https://remotive.com/api/remote-jobs?search=Growth+Marketing+Manager",
            "https://jobicy.com/api/v2/remote-jobs?count=50&tag=Growth+Marketing+Manager",
        ])

    def test_profile_free_source_targets_are_profile_derived(self):
        from discovery.targets import has_profile_discovery_signal, profile_free_source_targets

        empty_targets = profile_free_source_targets({})
        profile_targets = profile_free_source_targets({"s": "Python developer", "skills": [{"n": "FastAPI"}]})
        project_only_targets = profile_free_source_targets({
            "projects": [{"title": "Realtime chat platform", "stack": ["React", "FastAPI"]}],
        })

        self.assertEqual(empty_targets, "")
        self.assertTrue(has_profile_discovery_signal({"projects": [{"stack": ["React"]}]}))
        self.assertIn("Python developer", profile_targets)
        self.assertIn("Realtime chat platform", project_only_targets)
        self.assertNotIn("github:jobs", project_only_targets)
        self.assertNotIn("openai", profile_targets.lower())
        self.assertNotIn("anthropic", profile_targets.lower())
        self.assertNotIn("perplexity", profile_targets.lower())

    def test_explicit_discovery_targets_are_real_user_configuration(self):
        from discovery.targets import has_explicit_discovery_targets

        self.assertFalse(has_explicit_discovery_targets({}))
        self.assertFalse(has_explicit_discovery_targets({"x_bearer_token": "token-only"}))
        self.assertTrue(has_explicit_discovery_targets({"job_boards": "site:jobs.lever.co"}))
        self.assertTrue(has_explicit_discovery_targets({"free_source_targets": "github:backend hiring"}))
        self.assertTrue(has_explicit_discovery_targets({"company_watchlist": "greenhouse,<company-slug>"}))
        self.assertTrue(has_explicit_discovery_targets({"x_search_queries": '"hiring" "backend"'}))
        self.assertTrue(has_explicit_discovery_targets({"x_watchlist": "@target_company"}))
        self.assertTrue(has_explicit_discovery_targets({
            "custom_connectors_enabled": "true",
            "custom_connectors": '[{"name":"JobFeed","url":"https://jobs-api.your-domain.test/jobs"}]',
        }))

class TestScoringEngineCaps(unittest.TestCase):
    def _profile(self, work_months: int = 0, embedded: bool = False) -> dict:
        from ranking.scoring_engine import infer_experience_level

        period = "Jan 2021 to Dec 2025" if work_months >= 60 else ""
        profile = {
            "n": "Candidate",
            "s": "Frontend and full-stack web developer.",
            "skills": [
                {"n": "React"},
                {"n": "TypeScript"},
                {"n": "JavaScript"},
                {"n": "Node.js"},
                {"n": "Python"},
                {"n": "HTML"},
                {"n": "CSS"},
            ],
            "projects": [
                {
                    "title": "Frontend Platform",
                    "stack": ["React", "TypeScript", "Node.js"],
                    "impact": "Built production UI and API workflows.",
                }
            ],
            "exp": [],
        }
        if work_months >= 60:
            profile["exp"] = [{
                "role": "Senior Software Engineer",
                "co": "Acme",
                "period": period,
                "s": ["React", "TypeScript", "Node.js"],
                "d": "Built React, TypeScript, and Node.js applications.",
            }]
        if embedded:
            profile["skills"] = [{"n": "HTML"}, {"n": "CSS"}, {"n": "React"}, {"n": "JavaScript"}]
            profile["projects"] = [{
                "title": "Marketing Site",
                "stack": ["HTML", "CSS", "React", "JavaScript"],
                "impact": "Built responsive web pages.",
            }]
        profile["level"] = infer_experience_level(profile)
        return profile

    def _score(self, job_text: str, profile: dict):
        from ranking.scoring_engine import build_proof_text, score_job_lead

        self.assertIsInstance(build_proof_text(profile), str)
        return score_job_lead(job_text, profile)

    def test_senior_role_zero_experience_is_capped(self):
        result = self._score(
            "Senior Software Engineer - 5+ years required. React, TypeScript, Node.",
            self._profile(0),
        )
        self.assertLessEqual(result.score, 38, "Senior role + 0 experience must be capped at 38")

    def test_junior_role_strong_match_is_not_penalised(self):
        result = self._score(
            "Junior Frontend Developer - React, TypeScript",
            self._profile(0),
        )
        self.assertGreaterEqual(result.score, 45, "Strong stack match for a junior role should not be capped low")

    def test_experienced_candidate_senior_role_can_score_high(self):
        result = self._score(
            "Senior Engineer - React, TypeScript, Node, 4+ years",
            self._profile(60),
        )
        self.assertGreaterEqual(
            result.score,
            55,
            "A well-matched experienced candidate should score above mid-band for a senior role",
        )

    def test_completely_wrong_domain_scores_low(self):
        result = self._score(
            "Embedded Systems Engineer - C, RTOS, ARM Cortex, CAN bus, AUTOSAR",
            self._profile(0, embedded=True),
        )
        self.assertLessEqual(result.score, 40, "A domain mismatch should score low regardless of candidate quality")

    def test_score_is_within_valid_range(self):
        scenarios = [
            ("Senior Software Engineer - 5+ years required. React, TypeScript, Node.", self._profile(0)),
            ("Junior Frontend Developer - React, TypeScript", self._profile(0)),
            ("Senior Engineer - React, TypeScript, Node, 4+ years", self._profile(60)),
            ("Embedded Systems Engineer - C, RTOS, ARM Cortex, CAN bus, AUTOSAR", self._profile(0, embedded=True)),
        ]
        for job_text, profile in scenarios:
            result = self._score(job_text, profile)
            self.assertIsInstance(result.score, int)
            self.assertGreaterEqual(result.score, 0)
            self.assertLessEqual(result.score, 100)

    def test_local_semantic_fallback_is_used_when_vector_store_is_empty(self):
        result = self._score(
            "Junior Frontend Developer - React, TypeScript",
            self._profile(0),
        )
        self.assertTrue(
            any("Semantic fit" in point and "local-profile" in point for point in result.match_points),
            "Fallback semantic matching should still be visible in the score evidence",
        )

class TestLeadQualityGate(unittest.TestCase):
    def _quality(self, lead: dict, min_quality: int = 60, target_level: str = "any"):
        from discovery.quality_gate import evaluate_lead_quality

        return evaluate_lead_quality(lead, min_quality=min_quality, target_level=target_level)

    def test_valid_junior_job_is_accepted(self):
        quality = self._quality({
            "title": "Junior React Developer",
            "company": "Acme",
            "url": "https://jobs.example.com/junior-react",
            "platform": "greenhouse",
            "description": "Entry-level remote role building React, TypeScript, API workflows. Apply with portfolio.",
            "posted_date": "today",
            "signal_score": 88,
        })
        self.assertTrue(quality["accepted"])
        self.assertGreaterEqual(quality["score"], 60)

    def test_senior_only_role_is_rejected_for_beginner_feed(self):
        # The seniority penalty is now an explicit opt-in (target_level="beginner");
        # the default feed is seniority-neutral (field/location-agnostic goal).
        quality = self._quality({
            "title": "Senior Staff Software Engineer",
            "company": "Acme",
            "url": "https://jobs.example.com/staff",
            "platform": "lever",
            "description": "Senior Staff engineer role. Requires 7+ years with React, Node, system design, and team leadership.",
            "posted_date": "today",
            "signal_score": 90,
        }, target_level="beginner")
        self.assertFalse(quality["accepted"])
        self.assertIn("senior-only", quality["reason"])

    def test_senior_role_is_accepted_by_default_neutral_feed(self):
        # Same senior role, default (neutral) gate: must be accepted — proves the
        # quality gate carries no seniority bias unless a beginner feed is requested.
        quality = self._quality({
            "title": "Senior Staff Software Engineer",
            "company": "Acme",
            "url": "https://jobs.example.com/staff",
            "platform": "lever",
            "description": "Senior Staff engineer role. Requires 7+ years with React, Node, system design, and team leadership.",
            "posted_date": "today",
            "signal_score": 90,
        })
        self.assertTrue(quality["accepted"])

    def test_stale_lead_is_rejected(self):
        quality = self._quality({
            "title": "Junior Python Developer",
            "company": "Acme",
            "url": "https://jobs.example.com/old",
            "platform": "rss",
            "description": "Junior Python FastAPI role with remote work, clear apply path, and API integrations.",
            "posted_date": "2020-01-01",
            "signal_score": 85,
        })
        self.assertFalse(quality["accepted"])
        self.assertIn("stale posting", quality["reason"])

    def test_thin_post_is_penalized(self):
        quality = self._quality({
            "title": "React dev",
            "company": "",
            "url": "https://jobs.example.com/thin",
            "platform": "search",
            "description": "React job apply",
            "posted_date": "today",
            "signal_score": 65,
        })
        self.assertFalse(quality["accepted"])
        self.assertIn("thin scraped posting", quality["reason"])

    def test_red_flag_lead_is_rejected(self):
        quality = self._quality({
            "title": "Frontend Developer",
            "company": "Unknown",
            "url": "https://jobs.example.com/free-trial",
            "platform": "reddit",
            "description": "Build React frontend and API integration. This is unpaid and for exposure, apply today.",
            "posted_date": "today",
            "signal_score": 82,
        })
        self.assertFalse(quality["accepted"])
        self.assertIn("red flags", quality["reason"])
