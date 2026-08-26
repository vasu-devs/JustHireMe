from regression_support import *  # noqa: F401,F403

class RegressionTests(unittest.TestCase):
    def test_cleanup_flags_hn_discussion_comments_but_not_jobs(self):
        from data.sqlite.leads import lead_cleanup_reasons

        bad = {
            "title": "Maybe Claude code/anthropic should deprecate hooks",
            "company": "HN user",
            "url": "https://news.ycombinator.com/item?id=123",
            "platform": "hn_hiring",
            "description": "It understands the rule but treats it as optional instead of enforcing it.",
        }
        good = {
            "title": "Acme AI | Remote | Full-time | Backend Engineer",
            "company": "Acme AI",
            "url": "https://news.ycombinator.com/item?id=456",
            "platform": "hn_hiring",
            "description": "Acme AI | Remote | Full-time | Backend Engineer\nWe are hiring Python and React engineers. Salary range shown. Apply by email.",
        }

        self.assertTrue(lead_cleanup_reasons(bad))
        self.assertEqual(lead_cleanup_reasons(good), [])

    def test_weworkremotely_html_is_not_treated_as_rss(self):
        from automation.scout import _is_rss_target

        self.assertFalse(_is_rss_target("https://weworkremotely.com/categories/remote-programming-jobs"))
        self.assertTrue(_is_rss_target("https://weworkremotely.com/remote-jobs.rss"))

    def test_hn_hiring_story_filter_requires_who_is_hiring_title(self):
        from automation.scout import _is_hn_hiring_story

        self.assertTrue(_is_hn_hiring_story({"title": "Ask HN: Who is hiring? (April 2026)"}))
        self.assertFalse(_is_hn_hiring_story({"title": "Ask HN: Why is Claude Code ignoring hooks?"}))

    def test_hn_hiring_post_filter_rejects_discussion_comments(self):
        from automation.scout import _hn_company_role, _looks_like_hn_job_post, _strip_html_text

        bad = (
            "Maybe Claude code&#x2F;anthropic should deprecate certain features."
            "<p>It understands the rule but treats it as optional instead of enforcing it."
        )
        good = (
            "Acme AI | Remote (US) | Full-time | Backend Engineer"
            "<p>We are hiring Python and React engineers. Salary range shown. Apply by email."
        )

        self.assertEqual(_strip_html_text("Claude code&#x2F;anthropic"), "Claude code/anthropic")
        self.assertFalse(_looks_like_hn_job_post(bad))
        self.assertTrue(_looks_like_hn_job_post(good))
        self.assertEqual(_hn_company_role(good), ("Acme AI", "Backend Engineer"))

    def test_hn_hiring_role_extraction_uses_role_not_thread_title(self):
        from automation.scout import _hn_company_role, _looks_like_hn_job_post

        text = """
Baseten Labs | San Francisco, New York | ONSITE, REMOTE, HYBRID | VISA SPONSORSHIP | RELOCATION SUPPORT
We are Baseten. We're growing quickly and hiring for multiple core roles: 1 Solution Architect.
This role is a great fit for customer-facing technical professionals. Apply here: https://jobs.ashbyhq.com/baseten
"""

        self.assertTrue(_looks_like_hn_job_post(text))
        self.assertEqual(_hn_company_role(text), ("Baseten Labs", "Solution Architect"))

    def test_job_seniority_classifier_segregates_roles(self):
        from automation.scout import _passes_beginner_job_filter, classify_job_seniority

        junior = {
            "title": "Junior AI Engineer",
            "description": "Entry level Python and React role. Posted: today. 0-2 years.",
        }
        senior = {
            "title": "Senior AI Engineer",
            "description": "Requires 5+ years. Posted: today.",
        }
        unknown = {
            "title": "Python Engineer",
            "description": "No seniority or posted date shown.",
        }

        self.assertEqual(classify_job_seniority(junior), "junior")
        self.assertEqual(classify_job_seniority(senior), "senior")
        self.assertEqual(classify_job_seniority({
            "title": "Backend Engineer",
            "description": "Requires 3+ years building APIs.",
        }), "mid")
        self.assertEqual(classify_job_seniority(unknown), "unknown")
        self.assertTrue(_passes_beginner_job_filter(junior))
        self.assertFalse(_passes_beginner_job_filter(senior))

    def test_target_parser_ignores_comments_without_swallowing_urls(self):
        from discovery.targets import split_configured_targets

        raw = "\n".join([
            "# Beginner fallback feeds",
            "https://remotive.com/api/remote-jobs?search=junior,",
            "",
            "# ATS",
            "site:jobs.lever.co,",
            "https://remoteok.com/api",
        ])

        self.assertEqual(
            split_configured_targets(raw),
            [
                "https://remotive.com/api/remote-jobs?search=junior",
                "site:jobs.lever.co",
                "https://remoteok.com/api",
            ],
        )

    def test_x_scout_classifies_and_saves_beginner_job_signals(self):
        from automation import x_scout

        saved = []
        tweets = [{
            "id": "12345",
            "author_id": "u1",
            "text": "We are hiring a junior AI engineer for FastAPI and React. Entry level, 0-2 years. Apply today.",
            "created_at": "2026-04-30T10:00:00Z",
            "public_metrics": {"like_count": 4, "retweet_count": 1, "reply_count": 2},
        }]
        users = {"u1": {"id": "u1", "username": "startup_ai", "name": "Startup AI"}}

        with mock.patch.object(x_scout, "_search_recent", new=mock.AsyncMock(return_value=(tweets, users))) as search_recent, \
             mock.patch.object(x_scout, "url_exists", return_value=False), \
             mock.patch.object(x_scout, "save_lead", side_effect=lambda *args, **kwargs: saved.append((args, kwargs))):
            leads = x_scout.run(bearer_token="token", raw_queries="junior AI engineer", kind_filter="job")

        search_recent.assert_called_once()
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["kind"], "job")
        self.assertEqual(leads[0]["platform"], "x")
        self.assertEqual(leads[0]["budget"], "")
        self.assertGreaterEqual(leads[0]["signal_score"], 60)
        self.assertIn("job", leads[0]["signal_tags"])
        self.assertIn("apply", leads[0]["outreach_reply"].lower())
        self.assertIn("proposal_draft", leads[0])
        self.assertIn("proof_snippet", leads[0])
        self.assertIn("AI", leads[0]["tech_stack"])
        self.assertEqual(saved[0][1]["kind"], "job")
        self.assertGreaterEqual(saved[0][1]["signal_score"], 60)
        self.assertIn("proposal_draft", saved[0][1])

    def test_x_scout_accepts_non_tech_role_job_signals(self):
        from automation import x_scout

        kind = x_scout.classify_post("We are hiring a Growth Marketing Manager for SEO and lifecycle campaigns. Apply today.")

        self.assertEqual(kind, "job")

    def test_x_scout_builds_watchlist_queries(self):
        from automation.x_scout import build_watchlist_queries

        queries = build_watchlist_queries("@client_ai\nhttps://x.com/founder_1\nbad/extra")

        self.assertEqual(len(queries), 2)
        self.assertTrue(queries[0].startswith("from:client_ai "))
        self.assertTrue(queries[1].startswith("from:founder_1 "))

    def test_manual_lead_extracts_signal_and_outreach(self):
        from discovery.lead_intel import manual_lead_from_text

        lead = manual_lead_from_text(
            "Junior AI Engineer opening for Python, React, and automation. Entry level, remote, apply this week.",
            "https://example.com/jobs/1",
            "job",
        )

        self.assertEqual(lead["kind"], "job")
        self.assertEqual(lead["budget"], "")
        self.assertGreaterEqual(lead["signal_score"], 60)
        self.assertIn("job", lead["signal_tags"])
        self.assertIn("apply", lead["outreach_reply"].lower())
        self.assertIn("Subject:", lead["outreach_email"])
        self.assertIn("Role-fit pitch", lead["proposal_draft"])
        self.assertIn("Credibility block", lead["proof_snippet"])
        self.assertIn("AI", lead["tech_stack"])
        self.assertIn("this week", lead["urgency"])
        self.assertEqual(len(lead["followup_sequence"]), 3)

    def test_free_scout_builds_ats_watchlist_targets(self):
        from automation.free_scout import _ats_targets_from_watchlist

        self.assertEqual(
            _ats_targets_from_watchlist("greenhouse,openai\nlever|perplexity\nashby,linear\nworkable,acme"),
            ["ats:greenhouse:openai", "ats:lever:perplexity", "ats:ashby:linear", "ats:workable:acme"],
        )

    def test_free_scout_has_no_company_specific_runtime_defaults(self):
        from automation import free_scout

        self.assertEqual(free_scout.targets_from_settings("", ""), [])
        with mock.patch.object(free_scout, "_scrape_target", new=mock.AsyncMock()) as scrape_target:
            leads = free_scout.run(raw_targets="", raw_watchlist="", custom_connectors_enabled=False)

        scrape_target.assert_not_called()
        self.assertEqual(leads, [])
        self.assertIn("No free-source targets configured", free_scout.LAST_ERRORS[0])
        self.assertNotIn("openai", " ".join(free_scout.DEFAULT_TARGETS).lower())
        self.assertNotIn("anthropic", " ".join(free_scout.DEFAULT_TARGETS).lower())
        self.assertNotIn("perplexity", " ".join(free_scout.DEFAULT_TARGETS).lower())

    def test_free_scout_runs_custom_connectors_through_save_pipeline(self):
        from automation import free_scout

        async def fake_connector(_connector, _headers):
            return [free_scout._text_lead({
                "title": "Junior AI Engineer",
                "company": "PremiumCo",
                "url": "https://premium.example/jobs/1",
                "platform": "connector:PremiumCo",
                "description": "Entry level Python and React role. Remote. Apply this week.",
                "posted_date": "today",
                "source_meta": {"source": "custom_connector", "connector": "PremiumCo"},
            })]

        saved = []
        with mock.patch.object(free_scout, "_scrape_custom_connector", side_effect=fake_connector), \
             mock.patch.object(free_scout, "_scrape_target", new=mock.AsyncMock(return_value=[])), \
             mock.patch.object(free_scout, "url_exists", return_value=False), \
             mock.patch.object(free_scout, "save_lead", side_effect=lambda *args, **kwargs: saved.append((args, kwargs))):
            leads = free_scout.run(
                raw_targets="",
                raw_watchlist="",
                raw_custom_connectors='[{"name":"PremiumCo","url":"https://premium.example/jobs","items_path":"jobs"}]',
                raw_custom_headers='{"PremiumCo":{"Authorization":"Bearer secret"}}',
                custom_connectors_enabled=True,
                targets=["noop"],
                max_requests=3,
                min_signal_score=40,
            )

        self.assertEqual(len(leads), 1)
        self.assertEqual(saved[0][0][3], "https://premium.example/jobs/1")
        self.assertEqual(saved[0][1]["source_meta"]["source"], "custom_connector")

    def test_free_scout_reports_duplicates_and_filtered_candidates(self):
        from automation import free_scout

        batch = [
            free_scout._text_lead({
                "title": "Junior AI Engineer",
                "company": "PremiumCo",
                "url": "https://premium.example/jobs/1",
                "platform": "connector:PremiumCo",
                "description": "Entry level Python and React role. Remote. Apply this week.",
                "posted_date": "today",
            }),
            free_scout._text_lead({
                "title": "Unpaid Senior Staff Engineer Trial",
                "company": "PremiumCo",
                "url": "https://premium.example/jobs/2",
                "platform": "connector:PremiumCo",
                "description": "Senior Staff engineer role requiring 10+ years. Unpaid free trial for exposure with no budget.",
                "posted_date": "today",
            }),
        ]

        with mock.patch.object(free_scout, "_scrape_target", new=mock.AsyncMock(return_value=batch)), \
             mock.patch.object(free_scout, "url_exists", side_effect=[True, False]), \
             mock.patch.object(free_scout, "save_lead"):
            leads = free_scout.run(targets=["noop"], max_requests=1, min_signal_score=40)

        self.assertEqual(leads, [])
        self.assertEqual(free_scout.LAST_USAGE["candidates"], 2)
        self.assertEqual(free_scout.LAST_USAGE["duplicates"], 1)
        self.assertEqual(free_scout.LAST_USAGE["filtered"], 1)

    def test_custom_connector_headers_are_sensitive_settings(self):
        from api.routers.settings import sensitive_keys

        self.assertIn("custom_connector_headers", sensitive_keys({"custom_connector_headers": "secret"}))
