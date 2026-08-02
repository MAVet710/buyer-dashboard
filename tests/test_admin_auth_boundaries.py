import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }


def test_admin_and_access_context_renderers_are_outside_app_monolith():
    app_functions = _top_level_functions(ROOT / "app.py")

    assert "_render_admin_user_management" not in app_functions
    assert "_render_admin_integrations_page" not in app_functions
    assert "_render_user_metrc_integrations_page" not in app_functions
    assert "_render_access_context" not in app_functions


def test_admin_modules_have_single_public_entrypoints():
    user_functions = _top_level_functions(
        ROOT / "modules" / "admin" / "user_management.py"
    )
    integration_functions = _top_level_functions(
        ROOT / "modules" / "admin" / "integrations.py"
    )
    access_functions = _top_level_functions(
        ROOT / "modules" / "authentication" / "access_context.py"
    )

    assert "render_admin_user_management" in user_functions
    assert "render_admin_integrations_page" in integration_functions
    assert "render_user_metrc_integrations_page" in integration_functions
    assert "render_access_context" in access_functions


def test_first_login_gate_precedes_workspace_access():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    gate_position = source.index("render_legal_acceptance_gate(")
    workspace_position = source.index("workspace_options = build_workspace_options(")
    assert gate_position < workspace_position
    assert "st.stop()" in source[gate_position:workspace_position]


def test_policy_acceptance_requires_an_explicit_unchecked_checkbox():
    source = (
        ROOT / "modules" / "legal_acceptance" / "ui.py"
    ).read_text(encoding="utf-8")

    assert "accepted = st.checkbox(" in source
    assert "disabled=not accepted" in source
    assert "store.record_acceptance(" in source
    assert "return True" in source


