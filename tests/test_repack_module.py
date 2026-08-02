import ast
from pathlib import Path

from modules.repack.logic import grams_from_unit


ROOT = Path(__file__).resolve().parents[1]


def test_bulk_weight_conversion_preserves_existing_units():
    assert grams_from_unit(1.0, "g") == 1.0
    assert grams_from_unit(1.0, "oz") == 28.349523125
    assert grams_from_unit(1.0, "lb") == 453.59237


def test_repack_workspace_is_not_defined_in_app_monolith():
    app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    app_functions = {
        node.name for node in app_tree.body if isinstance(node, ast.FunctionDef)
    }

    assert "render_white_label_repack_workspace" not in app_functions
    assert "_grams_from_unit" not in app_functions


def test_repack_workspace_has_a_single_module_entrypoint():
    ui_tree = ast.parse(
        (ROOT / "modules" / "repack" / "ui.py").read_text(encoding="utf-8")
    )
    ui_functions = [
        node.name for node in ui_tree.body if isinstance(node, ast.FunctionDef)
    ]

    assert ui_functions.count("render_white_label_repack_workspace") == 1
    assert "_grams_from_unit" not in ui_functions


def test_repack_leftover_guidance_is_consolidated_in_results():
    source = (ROOT / "modules" / "repack" / "ui.py").read_text(encoding="utf-8")

    assert source.count("Package-size rounding leaves partial grams") == 1
    assert "This package size produces leftover grams" not in source
