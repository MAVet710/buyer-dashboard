import py_compile
from pathlib import Path


def test_app_py_compiles_without_syntax_errors():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    py_compile.compile(str(app_path), doraise=True)
