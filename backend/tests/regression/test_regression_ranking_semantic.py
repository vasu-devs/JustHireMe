from regression_support import *  # noqa: F401,F403

class RegressionTests(unittest.TestCase):
    def test_job_evaluator_is_deterministic_and_quantified(self):
        from ranking.evaluator import score

        jd = (
            "Job Title: Applied AI Engineer\n"
            "Company: Acme\n"
            "Description: Build RAG agents with Python, FastAPI, React, "
            "LangGraph, Qdrant. 1+ years. Remote."
        )

        first = score(jd, _sample_scoring_profile())
        second = score(jd, _sample_scoring_profile())

        self.assertEqual(first, second)
        self.assertGreaterEqual(first["score"], 85)
        self.assertTrue(any("Stack overlap" in point and "/100" in point for point in first["match_points"]))
        self.assertTrue(any("Proof of work" in point and "Waldo" in point for point in first["match_points"]))

    def test_job_evaluator_uses_llm_when_configured(self):
        from ranking.evaluator import score

        expected = {
            "score": 88,
            "reason": "LLM fit based on projects and certifications.",
            "match_points": ["Waldo proves RAG agent work."],
            "gaps": ["No Kubernetes production experience."],
        }

        with mock.patch("ranking.evaluator._evaluator_llm_requested", return_value=True), \
             mock.patch("ranking.evaluator._score_with_llm", return_value=expected) as score_with_llm:
            result = score(
                "Job Title: Applied AI Engineer\nDescription: Build RAG agents.",
                {**_sample_scoring_profile(), "certifications": ["AWS Cloud Practitioner"]},
            )

        self.assertEqual(result, expected)
        score_with_llm.assert_called_once()

    def test_evaluator_prompt_includes_profile_extras(self):
        from ranking.evaluator import _user_prompt

        profile = {
            **_sample_scoring_profile(),
            "certifications": ["AWS Cloud Practitioner"],
            "education": ["B.Tech Computer Science"],
            "achievements": ["Winner, AI hackathon"],
            "portfolio": "https://example.com",
        }
        prompt = _user_prompt("Job Title: AI Engineer", profile, {"score": 80, "reason": "baseline"})

        self.assertIn("AWS Cloud Practitioner", prompt)
        self.assertIn("B.Tech Computer Science", prompt)
        self.assertIn("Winner, AI hackathon", prompt)
        self.assertIn("https://example.com", prompt)

    def test_job_evaluator_applies_wrong_field_and_seniority_caps(self):
        from ranking.evaluator import score

        profile = _sample_scoring_profile()
        nurse = score("Job Title: Registered Nurse\nDescription: ICU nurse needed.", profile)
        senior = score(
            "Job Title: Senior Platform Engineer\n"
            "Description: Requires 7+ years Kubernetes, AWS, Go, and distributed systems.",
            profile,
        )

        self.assertLessEqual(nurse["score"], 15)
        self.assertTrue(any("wrong-field cap" in gap for gap in nurse["gaps"]))
        self.assertLessEqual(senior["score"], 30)
        self.assertTrue(any("seniority cap" in gap for gap in senior["gaps"]))

    def test_zero_experience_vs_senior_role_gets_hard_capped(self):
        from ranking.evaluator import score

        # Profile with strong stack match but ZERO professional experience
        zero_exp_profile = {
            "n": "Candidate",
            "s": "Full Stack AI Engineer based in India",
            "skills": [
                {"n": "React"},
                {"n": "Next.js"},
                {"n": "TypeScript"},
                {"n": "Node.js"},
                {"n": "FastAPI"},
                {"n": "PostgreSQL"},
                {"n": "Docker"},
            ],
            "projects": [
                {
                    "title": "BranchGPT",
                    "stack": ["Next.js", "TypeScript", "Drizzle ORM", "Neon Postgres"],
                    "impact": "Conversation DAG product.",
                },
                {
                    "title": "Waldo",
                    "stack": ["Python", "FastAPI", "React", "Qdrant", "LangGraph"],
                    "impact": "Production-grade agentic RAG pipeline.",
                },
                {
                    "title": "Vaani",
                    "stack": ["Python", "FastAPI", "LiveKit Agents", "Deepgram"],
                    "impact": "Voice AI debt recovery command center.",
                },
            ],
            "exp": [],  # No professional experience at all
        }

        senior_react = score(
            "Job Title: Senior Full stack React Developer\n"
            "Company: Lemon.io\n"
            "Description: Looking for a senior full-stack React developer "
            "with strong TypeScript, Node.js, and PostgreSQL skills. Remote.",
            zero_exp_profile,
        )

        # Must NOT be in the "strong fit" or "excellent fit" bands —
        # zero professional experience vs Senior title is a hard mismatch.
        self.assertLessEqual(senior_react["score"], 30,
            f"Zero-experience candidate got {senior_react['score']}/100 for a Senior role — "
            "seniority cap should prevent this")
        self.assertTrue(any("seniority cap" in gap for gap in senior_react["gaps"]))

    def test_semantic_falls_back_to_local_profile_when_vector_tables_are_missing(self):
        from ranking import semantic

        with mock.patch.object(semantic, "_vec_store", return_value=_FakeSemanticStore({})), \
             mock.patch.object(semantic, "_embed_jd", side_effect=AssertionError("embedding should not load")):
            result = semantic.semantic_fit("Need Python RAG engineer", candidate_data=_sample_scoring_profile())

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "local-profile")
        self.assertTrue(result["project_matches"])

    def test_semantic_search_is_scoped_to_current_profile_vectors(self):
        from ranking import semantic

        profile = {
            "skills": [{"n": "FastAPI"}],
            "projects": [{"title": "Waldo"}],
        }
        store = _FakeSemanticStore({
            "skills": [
                {"id": semantic._h("StaleSkill"), "n": "StaleSkill", "_distance": 0.01},
                {"id": semantic._h("FastAPI"), "n": "FastAPI", "_distance": 0.12},
            ],
            "projects": [
                {"id": semantic._h("Old Project"), "title": "Old Project", "_distance": 0.01},
                {"id": semantic._h("Waldo"), "title": "Waldo", "_distance": 0.10},
            ],
        })

        with mock.patch.object(semantic, "_vec_store", return_value=store), \
             mock.patch.object(semantic, "_embed_jd", return_value=[0.0, 1.0]):
            result = semantic.semantic_fit("Build a FastAPI RAG platform", candidate_data=profile)

        self.assertIsNotNone(result)
        self.assertEqual([name for name, _sim in result["skill_matches"]], ["FastAPI"])
        self.assertEqual([name for name, _sim in result["project_matches"]], ["Waldo"])

    def test_semantic_uses_profile_signal_when_vector_fallback_is_weak(self):
        from ranking import semantic

        profile = {
            "n": "Candidate",
            "s": "Applied AI engineer",
            "desired_position": "AI Engineer",
            "skills": [
                {"n": "Python"},
                {"n": "FastAPI"},
                {"n": "React"},
                {"n": "LangGraph"},
                {"n": "RAG"},
            ],
            "projects": [{
                "title": "ProbeGraph",
                "stack": ["FastAPI", "React", "LangGraph", "RAG"],
                "impact": "Built knowledge graph ingestion and semantic search.",
            }],
            "exp": [{
                "role": "AI Engineer",
                "co": "Probe Labs",
                "d": "Built RAG systems with FastAPI and React.",
            }],
            "certifications": ["Vector Search Systems"],
        }
        store = _FakeSemanticStore({
            "skills": [
                {"id": semantic._h("FastAPI"), "n": "FastAPI", "_distance": 0.86},
                {"id": semantic._h("React"), "n": "React", "_distance": 0.86},
                {"id": semantic._h("LangGraph"), "n": "LangGraph", "_distance": 0.86},
            ],
            "projects": [
                {"id": semantic._h("ProbeGraph"), "title": "ProbeGraph", "_distance": 0.80},
            ],
            "experiences": [
                {
                    "id": semantic._h("AI EngineerProbe Labs"),
                    "role": "AI Engineer",
                    "_distance": 0.82,
                },
            ],
            "credentials": [],
        })

        with mock.patch.object(semantic, "_vec_store", return_value=store), \
             mock.patch.object(semantic, "_embed_jd", return_value=[0.0, 1.0]), \
             mock.patch.object(semantic, "_embedding_mode", return_value="hashing"):
            result = semantic.semantic_fit(
                "Need Python FastAPI React LangGraph RAG engineer for knowledge graph ingestion and semantic search",
                candidate_data=profile,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "local-profile")
        self.assertGreaterEqual(result["score"], 70)
        self.assertTrue(any(name == "FastAPI" for name, _sim in result["skill_matches"]))
        self.assertTrue(any(name == "ProbeGraph" for name, _sim in result["project_matches"]))

    def test_local_profile_score_is_mode_independent(self):
        """The local-profile fallback ALWAYS computes similarities with the hash
        embedder, so its score must not depend on the active embedding provider mode.
        Regression: with ONNX/OpenAI active but the vector store empty, the hash-derived
        similarity was pushed through the wider semantic stretch window, collapsing a
        genuine match's score (~95 -> ~27)."""
        from ranking import semantic

        profile = {
            "n": "Candidate",
            "s": "Applied AI engineer",
            "skills": [{"n": "Python"}, {"n": "FastAPI"}, {"n": "React"}, {"n": "LangGraph"}, {"n": "RAG"}],
            "projects": [{
                "title": "ProbeGraph",
                "stack": ["FastAPI", "React", "LangGraph", "RAG"],
                "impact": "Built knowledge graph ingestion and semantic search.",
            }],
            "exp": [{"role": "AI Engineer", "co": "Probe Labs", "d": "Built RAG systems with FastAPI and React."}],
            "certifications": ["Vector Search Systems"],
        }
        jd = "Need Python FastAPI React LangGraph RAG engineer for knowledge graph ingestion and semantic search"

        def run(mode):
            with mock.patch.object(semantic, "_vec_store", return_value=_FakeSemanticStore({})), \
                 mock.patch.object(semantic, "_embed_jd", side_effect=AssertionError("vector path must not run")), \
                 mock.patch.object(semantic, "_embedding_mode", return_value=mode):
                return semantic.semantic_fit(jd, candidate_data=profile)

        hashing = run("hashing")
        onnx = run("onnx")
        self.assertEqual(hashing["source"], "local-profile")
        self.assertEqual(onnx["source"], "local-profile")
        # Same hash-derived similarities -> identical score regardless of provider mode,
        # and a genuine match must still land in a high band.
        self.assertEqual(hashing["score"], onnx["score"])
        self.assertGreaterEqual(onnx["score"], 70)

    def test_semantic_local_fallback_uses_experience_and_credentials(self):
        from ranking import semantic

        profile = {
            "skills": [],
            "projects": [],
            "exp": [{
                "role": "Data Engineer",
                "co": "Acme",
                "period": "2025",
                "d": "Built Airflow pipelines for warehouse automation.",
            }],
            "certifications": ["AWS Data Analytics Specialty"],
        }

        with mock.patch.object(semantic, "_vec_store", return_value=_FakeSemanticStore({})), \
             mock.patch.object(semantic, "_embed_jd", side_effect=AssertionError("embedding should not load")):
            result = semantic.semantic_fit("Need AWS data engineer for Airflow pipelines", candidate_data=profile)

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "local-profile")
        self.assertTrue(result["experience_matches"])
        self.assertTrue(result["credential_matches"])

    def test_evaluator_passes_current_profile_into_semantic_signal(self):
        from ranking.evaluator import score

        profile = _sample_scoring_profile()
        semantic_result = {
            "score": 82,
            "skill_matches": [("FastAPI", 0.71)],
            "project_matches": [("Waldo", 0.76)],
        }
        with mock.patch("ranking.semantic.semantic_fit", return_value=semantic_result) as semantic_fit:
            result = score(
                "Job Title: Applied AI Engineer\nDescription: Build RAG agents with FastAPI and Qdrant.",
                profile,
            )

        self.assertIs(semantic_fit.call_args.kwargs["candidate_data"], profile)
        self.assertTrue(any("Semantic fit" in point for point in result["match_points"]))
