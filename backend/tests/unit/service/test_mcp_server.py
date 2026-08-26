import json
import unittest

from mcp_server import _handle


class MCPServerTests(unittest.TestCase):
    def test_initialize_returns_tool_capability(self):
        response = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list_exposes_job_intelligence_tools(self):
        response = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertEqual(
            names,
            {"score_job_fit", "evaluate_lead_quality", "extract_lead_intel"},
        )

    def test_extract_lead_intel_tool_returns_text_content(self):
        response = _handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "extract_lead_intel",
                    "arguments": {
                        "text": "Acme is hiring a remote Python FastAPI React engineer. Apply today."
                    },
                },
            }
        )

        result = response["result"]
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(result["isError"])
        self.assertEqual(payload["location"], "Remote")
        self.assertIn("Python", payload["tech_stack"])
