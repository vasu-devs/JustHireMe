"""SSRF guard on the Azure OpenAI endpoint used by the provider probe/model-list.

api/routers/settings.py rebuilds the Azure endpoint from user settings and
fetches it to validate the key / list models. That duplicated the LLM client's
URL construction but skipped the client's ``_validate_base_url`` SSRF guard, so a
loopback / metadata / private endpoint could be reached. These tests pin the fix:
a non-public Azure endpoint must never be probed (it resolves to "unreachable"
without any network call, because validation raises before the request).
"""

import asyncio

import pytest

from api.routers.settings import probe_provider_key


@pytest.mark.unit
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1",  # loopback
        "http://localhost",  # loopback name
        "http://169.254.169.254",  # cloud metadata
        "http://10.0.0.5",  # private
        "http://192.168.1.10",  # private
    ],
)
def test_azure_non_public_endpoint_not_probed(endpoint):
    result = asyncio.run(probe_provider_key("azure", "any-key", {"azure_openai_endpoint": endpoint}))
    assert result["status"] == "unreachable"


@pytest.mark.unit
def test_azure_missing_endpoint_is_unchecked():
    result = asyncio.run(probe_provider_key("azure", "k", {}))
    assert result["status"] == "unchecked"
