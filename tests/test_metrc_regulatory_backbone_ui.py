from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_metrc_is_not_presented_as_a_future_connection():
    panel = _read("frontend/src/components/DeveloperConnectionsPanel.tsx")
    assert "Future provider connections" not in panel
    assert "Connected regulatory backbone" in panel
    assert "Metrc is the authoritative source for regulated cannabis state" in panel
    assert "This is the sandbox control plane, not a future-feature area" in panel


def test_operator_health_separates_restrictions_from_failures():
    panel = _read("frontend/src/components/DeveloperConnectionsPanel.tsx")
    natural_sync = _read("backend/app/services/metrc_natural_sync.py")
    capability = _read("services/metrc_capability_matrix.py")

    assert "Regulatory health" in panel
    assert "Modules fed by Metrc" in panel
    assert "Show Metrc resource diagnostics" in panel
    assert "operator_summary" in natural_sync
    assert "resource_capabilities" in natural_sync
    assert "module_health" in natural_sync
    assert 'RESOURCE_RESTRICTED = "restricted"' in capability
    assert 'RESOURCE_NOT_AVAILABLE = "not_available_for_license"' in capability


def test_metrc_writeback_contract_remains_separate_and_fail_closed():
    dispatcher = _read("services/traceability_dispatcher.py")
    native = _read("services/metrc_native.py")
    registry = _read("modules/regulatory/write_registry.py")

    assert "require_metrc_write_contract" in dispatcher
    assert "validate_metrc_action" in dispatcher
    assert "There is intentionally no generic" in native
    assert "dispatch_enabled" in registry
