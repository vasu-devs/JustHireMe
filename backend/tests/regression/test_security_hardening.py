from core.telemetry import redact_sensitive, redact_text


def test_redact_text_removes_common_pii_and_secrets():
    raw = "Email jane@example.com, phone +1 (415) 555-1234, token Bearer abcdefghijklmnopqrstuvwxyz"

    redacted = redact_text(raw)

    assert "jane@example.com" not in redacted
    assert "415" not in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_redact_sensitive_masks_sensitive_keys_recursively():
    payload = {
        "error": "failed for jane@example.com",
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {
            "api_key": "sk-testtesttesttesttest",
            "safe": "hello",
        },
    }

    redacted = redact_sensitive(payload)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "hello"
    assert "jane@example.com" not in redacted["error"]
