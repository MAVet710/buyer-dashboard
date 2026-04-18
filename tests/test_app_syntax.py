import py_compile
from pathlib import Path


def test_app_py_compiles_without_syntax_errors():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    py_compile.compile(str(app_path), doraise=True)


def test_streamlit_app_entrypoint_compiles_without_syntax_errors():
    entrypoint_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    py_compile.compile(str(entrypoint_path), doraise=True)
