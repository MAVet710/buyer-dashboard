from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_app_has_no_legacy_provider_selector_ui():
    app_text = _read("app.py")
    assert '["auto", "openai", "ollama"]' not in app_text
    assert "AI Provider: {DOOBIE_PROVIDER_NAME}" in app_text


def test_app_has_no_legacy_openai_or_ollama_init_paths():
    app_text = _read("app.py")
    assert "def _find_openai_key" not in app_text
    assert "def init_openai_client" not in app_text
    assert "build_provider(" not in app_text


def test_legacy_llm_client_routes_to_doobie_only():
    llm_text = _read("ai/llm_client.py")
    assert "DoobieClient" in llm_text
    assert "OpenAI" not in llm_text


def test_buyer_assistant_routes_to_doobie_only():
    assistant_text = _read("modules/buyer_assistant.py")
    assert "client.copilot(" in assistant_text
    assert "ai.retriever" not in assistant_text


def test_doobie_status_codes_standardized():
    app_text = _read("app.py")
    for required in ["connected", "not_connected", "unavailable", "invalid_license"]:
        assert required in app_text
