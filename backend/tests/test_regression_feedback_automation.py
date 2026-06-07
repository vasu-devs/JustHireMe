from regression_support import *  # noqa: F401,F403

class RegressionTests(unittest.TestCase):
    def test_feedback_body_accepts_lead_quality_labels(self):
        from core.types import FeedbackBody

        body = FeedbackBody.model_validate({"feedback": "incorrect_category"})
        self.assertEqual(body.feedback, "incorrect_category")

    def test_feedback_ranker_boosts_matching_future_leads(self):
        from ranking.feedback_ranker import apply_feedback_learning

        examples = [{
            "feedback": "relevant",
            "platform": "github",
            "company": "owner/repo",
            "kind": "job",
            "signal_tags": ["ai", "job"],
            "tech_stack": ["AI", "FastAPI"],
            "source_meta": {"source": "github"},
        }]
        lead = {
            "platform": "github",
            "company": "owner/repo",
            "kind": "job",
            "signal_score": 55,
            "signal_reason": "intent",
            "signal_tags": ["ai", "job"],
            "tech_stack": ["AI"],
            "source_meta": {"source": "github"},
        }

        ranked = apply_feedback_learning(lead, examples)

        self.assertGreater(ranked["signal_score"], 55)
        self.assertGreater(ranked["learning_delta"], 0)
        self.assertEqual(ranked["base_signal_score"], 55)
        self.assertIn("feedback learning +", ranked["signal_reason"])

    def test_feedback_ranker_penalizes_rejected_patterns(self):
        from ranking.feedback_ranker import apply_feedback_learning

        examples = [{
            "feedback": "not_relevant",
            "platform": "reddit",
            "kind": "job",
            "signal_tags": ["course", "job"],
            "tech_stack": ["AI"],
            "source_meta": {"source": "reddit"},
        }]
        lead = {
            "platform": "reddit",
            "kind": "job",
            "signal_score": 60,
            "signal_tags": ["course", "job"],
            "tech_stack": ["AI"],
            "source_meta": {"source": "reddit"},
        }

        ranked = apply_feedback_learning(lead, examples)

        self.assertLess(ranked["signal_score"], 60)
        self.assertLess(ranked["learning_delta"], 0)
        self.assertIn("Feedback penalty", ranked["learning_reason"])

    def test_fire_blocker_requires_real_resume_and_cover_letter(self):
        from api.routers.automation import fire_blocker

        existing_path = __file__
        lead = {"url": "https://example.com/apply", "cover_letter_asset": existing_path}
        self.assertEqual(fire_blocker(lead, existing_path), (0, ""))

        missing_cover = {"url": "https://example.com/apply", "cover_letter_asset": ""}
        self.assertEqual(fire_blocker(missing_cover, existing_path)[0], 409)
        self.assertEqual(fire_blocker({}, existing_path)[0], 404)

    def test_actuator_submit_gate_requires_upload_and_work(self):
        from automation.actuator import _ready_to_submit

        self.assertFalse(_ready_to_submit({"uploaded": False, "fields": ["email"], "vision_actions": 0}))
        self.assertFalse(_ready_to_submit({"uploaded": True, "fields": [], "vision_actions": 0}))
        self.assertTrue(_ready_to_submit({"uploaded": True, "fields": ["email"], "vision_actions": 0}))
        # SECURITY (0.1): vision actions alone no longer authorize a submit — only
        # DOM-verified field fills do, since LLM pixel coordinates are unverifiable.
        self.assertFalse(_ready_to_submit({"uploaded": True, "fields": [], "vision_actions": 2}))

class TestBrowserRuntimePackaging(unittest.TestCase):
    def test_sidecar_default_release_features_include_browser(self):
        spec = (Path(__file__).resolve().parents[1] / "backend.spec").read_text(encoding="utf-8")

        self.assertIn('"core,graph,browser"', spec)
        self.assertNotIn('"core,graph,vector,browser"', spec)

    def test_browser_runtime_asset_name_is_platform_specific(self):
        from automation import browser_runtime

        with mock.patch.object(browser_runtime, "sys_platform", return_value="windows"):
            self.assertEqual(browser_runtime.browser_runtime_asset_name(), "JustHireMe-browser-runtime-windows.zip")
        with mock.patch.object(browser_runtime, "sys_platform", return_value="darwin"):
            self.assertEqual(browser_runtime.browser_runtime_asset_name(), "JustHireMe-browser-runtime-macos.zip")
        with mock.patch.object(browser_runtime, "sys_platform", return_value="linux"):
            self.assertEqual(browser_runtime.browser_runtime_asset_name(), "JustHireMe-browser-runtime-linux.zip")

    def test_browser_runtime_ready_detects_chromium_payload(self):
        from automation.browser_runtime import browser_runtime_ready

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "ms-playwright"
            runtime.mkdir()
            self.assertFalse(browser_runtime_ready(runtime))
            (runtime / "chromium-1200").mkdir()
            self.assertTrue(browser_runtime_ready(runtime))

    def test_browser_runtime_finds_pruned_runtime_chromium_executable(self):
        from automation import browser_runtime

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "ms-playwright"
            chrome = runtime / "chromium-1200" / "chrome-win64" / "chrome.exe"
            chrome.parent.mkdir(parents=True)
            chrome.write_text("", encoding="utf-8")

            with (
                mock.patch.object(browser_runtime, "browser_runtime_dir", return_value=runtime),
                mock.patch.object(browser_runtime, "sys_platform", return_value="windows"),
            ):
                self.assertEqual(browser_runtime._runtime_chromium_executable(), str(chrome))

    def test_browser_runtime_installs_through_required_runtime_pack(self):
        from automation import browser_runtime

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "ms-playwright"
            calls = []

            def fake_install():
                calls.append("install")
                (runtime / "chromium-1200").mkdir(parents=True)

            with (
                mock.patch.object(browser_runtime, "browser_runtime_dir", return_value=runtime),
                mock.patch.object(browser_runtime, "install_vector_runtime", side_effect=fake_install),
            ):
                self.assertEqual(browser_runtime.ensure_browser_runtime(), runtime)

            self.assertEqual(calls, ["install"])

    def test_vector_runtime_asset_name_is_platform_specific(self):
        from data.vector import runtime

        with mock.patch.object(runtime, "sys_platform", return_value="windows"):
            self.assertEqual(runtime.vector_runtime_asset_name(), "JustHireMe-vector-runtime-windows.zip")
            self.assertEqual(runtime.runtime_pack_asset_name(), "JustHireMe-runtime-pack-windows.zip")
        with mock.patch.object(runtime, "sys_platform", return_value="darwin"):
            self.assertEqual(runtime.vector_runtime_asset_name(), "JustHireMe-vector-runtime-macos.zip")
            self.assertEqual(runtime.runtime_pack_asset_name(), "JustHireMe-runtime-pack-macos.zip")
        with mock.patch.object(runtime, "sys_platform", return_value="linux"):
            self.assertEqual(runtime.vector_runtime_asset_name(), "JustHireMe-vector-runtime-linux.zip")
            self.assertEqual(runtime.runtime_pack_asset_name(), "JustHireMe-runtime-pack-linux.zip")
