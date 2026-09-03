from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_label_print_test_pass_is_canonical_dev_sandbox_only():
    policy = _read("modules/coman/dev_sandbox_policy.py")
    assert 'DEV_SANDBOX_ORGANIZATION_SLUG = "dev-sandbox"' in policy
    assert 'DEV_SANDBOX_FACILITY_CODE = "SANDBOX"' in policy
    assert 'casefold() != "dev"' in policy
    assert "facility.organization_id == organization.id" in policy
    assert '"data_classification": "synthetic_test_data"' in policy
    assert '"production_effect": "none"' in policy


def test_production_label_routes_pass_authenticated_role_to_server_side_guard():
    router = _read("backend/app/routers/label_printing.py")
    workflow = _read("modules/label_studio_workflow.py")
    assert router.count("role=context.role") >= 2
    assert "dev_sandbox_test_pass_active" in workflow
    assert "DEV Sandbox test pass refused because this sandbox is mapped to a production METRC environment." in workflow
    assert '"dev_sandbox_test_pass"' in workflow
    assert '"bypassed_checks"' in workflow
    assert '"synced_metrc_package_tag_availability"' in workflow
    assert "any(ch.isspace() for ch in clean)" in workflow
    assert "metrc_package_tag == clean" in workflow


def test_advanced_labelguard_printing_keeps_real_tenant_guards():
    printing = _read("modules/operational_moats/printing.py")
    assert "dev_sandbox_test_pass_active" in printing
    assert 'if template.status != "active" and not sandbox_test_pass' in printing
    assert 'if review.status == "fail" and not sandbox_test_pass' in printing
    assert 'review.status == "warning" and not sandbox_test_pass' in printing
    assert "DEV_SANDBOX_TEST_PASS_REASON" in printing


def test_label_studio_makes_sandbox_data_and_test_pass_unmistakable():
    workspace = _read("frontend/src/pages/LabelStudioWorkspacePage.tsx")
    workflow = _read("frontend/src/components/InventoryDrivenLabelWorkflow.tsx")
    assert 'toLowerCase()==="dev"' in workspace
    assert 'toLowerCase()==="dev-sandbox"' in workspace
    assert 'toUpperCase()==="SANDBOX"' in workspace
    assert "ALL OPERATIONAL DATA IS TEST DATA" in workspace
    assert "Production and customer-tenant safeguards are not changed." in workspace
    assert "sandboxTestPass={sandboxTestPass}" in workspace
    assert "PRINT TEST PASS ACTIVE" in workflow
    assert "primaryReady=sandboxTestPass||primaryVerified" in workflow
    assert "DEV Sandbox test-pass use is written into the run audit trail." in workflow
