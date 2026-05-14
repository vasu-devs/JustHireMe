from regression_support import *  # noqa: F401,F403

class RegressionTests(unittest.TestCase):
    def test_extended_llm_provider_catalog_is_configured(self):
        from llm import _DEFAULT_MODELS, _ENV_NAMES, _KEY_NAMES, _OPENAI_COMPAT_BASE_URLS

        providers = {
            "xai", "kimi", "mistral", "openrouter", "together", "fireworks",
            "cerebras", "perplexity", "huggingface", "cohere", "sambanova",
            "qwen", "azure", "custom",
        }
        for provider in providers:
            self.assertIn(provider, _KEY_NAMES)
            self.assertIn(provider, _ENV_NAMES)
            self.assertIn(provider, _DEFAULT_MODELS)
        for provider in providers - {"azure", "custom"}:
            self.assertTrue(_OPENAI_COMPAT_BASE_URLS[provider].startswith("https://"))

    def test_help_assistant_answers_api_and_llm_setup_from_guide(self):
        from help.service import answer

        result = answer("what is an api and what all are available in here for llm and how do i get them")
        text = result["answer"].lower()

        self.assertEqual(result["source"], "guide")
        self.assertIn("api key is", text)
        self.assertIn("settings > global ai", text)
        for provider in ["gemini", "deepseek", "nvidia", "groq", "grok", "kimi", "anthropic", "ollama"]:
            self.assertIn(provider, text)
        self.assertIn("run the provider check", text)

    def test_azure_provider_without_endpoint_falls_back_cleanly(self):
        from pydantic import BaseModel
        from data.repository import create_repository
        from llm import call_llm, configure_repository

        class Payload(BaseModel):
            value: str = ""

        class Settings:
            def get_setting(self, key, default=""):
                return {
                    "llm_provider": "azure",
                    "azure_openai_api_key": "fake-key",
                    "azure_model": "deployment-name",
                }.get(key, default)

        class Repo:
            settings = Settings()

        try:
            configure_repository(Repo())
            result = call_llm("system", "user", Payload)
            self.assertEqual(result.value, "")
        finally:
            configure_repository(create_repository())

    def test_model_facing_agents_have_production_guardrails(self):
        import inspect
        from automation import actuator, scout
        from ranking import evaluator
        from generation import generator

        contracts = [
            evaluator._SYSTEM_PROMPT,
            scout._SCOUT_EXTRACT_SYSTEM,
            scout._WELLFOUND_EXTRACT_SYSTEM,
            actuator._VISION_SYSTEM,
            inspect.getsource(generator._draft_package),
        ]
        joined = "\n".join(contracts).lower()

        self.assertIn("production", joined)
        self.assertIn("untrusted", joined)
        self.assertIn("never invent", joined)
        self.assertIn("do not click final", actuator._VISION_SYSTEM.lower())
        self.assertIn("structured output only", scout._SCOUT_EXTRACT_SYSTEM.lower())
