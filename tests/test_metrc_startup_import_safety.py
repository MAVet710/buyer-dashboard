from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _top_level_calls(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    calls: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        function = node.value.func
        if isinstance(function, ast.Name):
            calls.add(function.id)
    return calls


def test_app_import_never_starts_mutation_capable_metrc_evaluation_workers() -> None:
    calls = _top_level_calls("backend/app/__init__.py")

    assert "_start_metrc_package_eval_if_requested" not in calls
    assert "_start_metrc_package_alt_item_if_requested" not in calls


def test_app_import_keeps_only_get_only_metrc_resume_diagnostics_runtime_gated() -> None:
    calls = _top_level_calls("backend/app/__init__.py")

    assert "_start_metrc_resume_diagnostic_if_requested" in calls
    assert "_start_metrc_resume_detail_if_requested" in calls
