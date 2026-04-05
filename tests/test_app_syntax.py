import py_compile
from pathlib import Path


def test_app_py_compiles_without_syntax_errors():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    py_compile.compile(str(app_path), doraise=True)


def test_init_openai_client_block_has_no_global_statement():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    text = app_path.read_text()

    start = text.find("def init_openai_client")
    assert start != -1, "init_openai_client definition missing"

    end = text.find("\n\ndef ", start + 1)
    if end == -1:
        end = len(text)

    init_block = text[start:end]
    assert "global OPENAI_AVAILABLE, ai_client, ai_provider" not in init_block
