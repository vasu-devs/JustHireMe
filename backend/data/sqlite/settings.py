from __future__ import annotations

from data.sqlite.connection import DEFAULT_DB_PATH, get_connection, init_sql


SETTINGS_SCHEMA = {
    "x_max_requests_per_scan": {"type": "int", "min": 1, "max": 50, "default": 5},
    "x_max_results_per_query": {"type": "int", "min": 10, "max": 100, "default": 50},
    "free_source_min_signal_score": {"type": "int", "min": 0, "max": 100, "default": 60},
    "free_source_max_requests": {"type": "int", "min": 1, "max": 80, "default": 20},
    "board_scan_batch_size": {"type": "int", "min": 1, "max": 12, "default": 4},
    # How many board-scan batches run at once. Each in-flight batch can hold a
    # live browser, so the ceiling stays deliberately small.
    "board_scan_concurrency": {"type": "int", "min": 1, "max": 8, "default": 3},
    "x_hot_lead_threshold": {"type": "int", "min": 1, "max": 100, "default": 80},
    "llm_provider": {
        "type": "str",
        "allowed": [
            "", "ollama", "anthropic", "gemini", "groq", "nvidia", "openai",
            "deepseek", "xai", "kimi", "mistral", "openrouter", "together",
            "fireworks", "cerebras", "perplexity", "huggingface", "cohere",
            "sambanova", "qwen", "azure", "custom",
            "claude_cli", "codex_cli", "gemini_cli", "antigravity_cli", "copilot_cli",  # subscription CLIs (no API key)
        ],
        "default": "",
    },
    "evaluator_provider": {
        "type": "str",
        "allowed": [
            "", "ollama", "anthropic", "gemini", "groq", "nvidia", "openai",
            "deepseek", "xai", "kimi", "mistral", "openrouter", "together",
            "fireworks", "cerebras", "perplexity", "huggingface", "cohere",
            "sambanova", "qwen", "azure", "custom",
            "claude_cli", "codex_cli", "gemini_cli", "antigravity_cli", "copilot_cli",  # subscription CLIs (no API key)
        ],
        "default": "",
    },
    "resume_style_preset": {
        "type": "str",
        "allowed": ["classic", "harvard", "modern"],  # visual PDF looks (#90)
        "default": "classic",
    },
    "embedding_provider": {
        "type": "str",
        "allowed": ["onnx", "openai", "hash"],
        "default": "onnx",
    },
}


def validate_setting(key: str, value: object) -> tuple[bool, str]:
    schema = SETTINGS_SCHEMA.get(key)
    if not schema:
        return True, ""
    text = "" if value is None else str(value)
    if schema["type"] == "int":
        try:
            parsed = int(text)
        except (TypeError, ValueError):
            return False, f"{key} must be a number"
        if parsed < schema["min"] or parsed > schema["max"]:
            return False, f"{key} must be between {schema['min']} and {schema['max']}"
    elif schema["type"] == "str" and "allowed" in schema:
        if text not in schema["allowed"]:
            allowed = ", ".join(schema["allowed"])
            return False, f"{key} must be one of: {allowed}"
    return True, ""


def validate_settings_payload(data: dict) -> None:
    errors = []
    for key, value in data.items():
        ok, message = validate_setting(key, value)
        if not ok:
            errors.append(message)
    if errors:
        raise ValueError("; ".join(errors))


def _ensure_settings_table(db_path: str = DEFAULT_DB_PATH) -> None:
    init_sql(db_path)


def save_settings(data: dict, db_path: str = DEFAULT_DB_PATH) -> None:
    _ensure_settings_table(db_path)
    validate_settings_payload(data)
    conn = get_connection(db_path)
    try:
        for key, value in data.items():
            conn.execute("INSERT OR REPLACE INTO settings(key,val) VALUES(?,?)", (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def get_settings(db_path: str = DEFAULT_DB_PATH) -> dict:
    _ensure_settings_table(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT key,val FROM settings").fetchall()
    finally:
        conn.close()
    return {row["key"]: row["val"] for row in rows}


def get_setting(key: str, default: str = "", db_path: str = DEFAULT_DB_PATH) -> str:
    _ensure_settings_table(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT val FROM settings WHERE key=?", (key,)).fetchone()
    finally:
        conn.close()
    return row["val"] if row else default
