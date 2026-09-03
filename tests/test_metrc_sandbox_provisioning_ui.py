from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_fastapi_uses_canonical_metrc_bootstrap_and_audits_attempts():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert "from services.metrc_sandbox_bootstrap import" in router
    assert "setup_ma_sandbox_integrator" in router
    assert '@router.post("/metrc/provision-user")' in router
    assert "metrc_sandbox_user_provision_requested" in router
    assert '"required": ("state",)' in router
    assert '"sandbox_user_provisioning_enabled": True' in router


def test_returned_user_key_is_saved_encrypted_and_not_returned_to_browser():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert "returned_user_key = str(result.get(\"user_key\")" in router
    assert "secret=returned_user_key" in router
    assert "user_key_saved" in router
    assert '"user_key": returned_user_key' not in router


def test_facility_discovery_is_metrc_owned_and_bootstraps_bound_facilities():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert 'resource="facilities"' in router
    assert '@router.post("/metrc/discover-facilities")' in router
    assert '@router.post("/metrc/facilities/confirm")' in router
    assert "MetrcFacilityOnboardingService" in router
    assert "MetrcFacilityBootstrapService" in router
    assert "_bootstrap_bound_facilities(" in router
    assert '"facility_discovery_enabled": True' in router


def test_react_exposes_provision_discover_and_one_time_matching_flow():
    panel = _read("frontend/src/components/DeveloperConnectionsPanel.tsx")
    assert "Provision sandbox user" in panel
    assert "Discover Metrc facilities" in panel
    assert "/api/v1/integrations/sandbox/metrc/provision-user" in panel
    assert "/api/v1/integrations/sandbox/metrc/discover-facilities" in panel
    assert "/api/v1/integrations/sandbox/metrc/facilities/confirm" in panel
    assert 'queryKey: ["integrations"]' in panel
    assert "Leave blank — DoobieLogic discovers this from Metrc" in panel
    assert "Connect to {match.name}" in panel
    assert "Create new DoobieLogic facility" in panel
