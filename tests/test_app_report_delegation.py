import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


EXPECTED_REPORT_DELEGATES = {
    "_build_buyer_executive_report_bytes": (
        "reports.buyer_report",
        "_build_buyer_executive_report_bytes",
    ),
    "_build_buyer_executive_report_pdf": (
        "reports.buyer_report",
        "_build_buyer_executive_report_pdf",
    ),
    "_build_extraction_executive_report_pdf": (
        "reports.extraction_report",
        "_build_extraction_executive_report_pdf",
    ),
    "_build_white_label_repack_report_pdf": (
        "reports.white_label_report",
        "_build_white_label_repack_report_pdf",
    ),
}


def _app_functions() -> dict[str, list[ast.FunctionDef]]:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    functions: dict[str, list[ast.FunctionDef]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.setdefault(node.name, []).append(node)
    return functions


def test_report_entrypoints_are_defined_once():
    functions = _app_functions()

    for function_name in EXPECTED_REPORT_DELEGATES:
        assert len(functions.get(function_name, [])) == 1


def test_report_entrypoints_are_thin_module_delegates():
    functions = _app_functions()

    for function_name, (module_name, imported_name) in EXPECTED_REPORT_DELEGATES.items():
        function = functions[function_name][0]

        assert len(function.body) == 2
        import_node, return_node = function.body
        assert isinstance(import_node, ast.ImportFrom)
        assert import_node.module == module_name
        assert len(import_node.names) == 1
        assert import_node.names[0].name == imported_name
        assert import_node.names[0].asname == "build_report"
        assert isinstance(return_node, ast.Return)
        assert isinstance(return_node.value, ast.Call)
        assert isinstance(return_node.value.func, ast.Name)
        assert return_node.value.func.id == "build_report"
