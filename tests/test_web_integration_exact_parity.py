from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_non_dev_surface_is_metrc_only_and_matches_streamlit_controls():
    source = read("frontend/src/pages/IntegrationsPage.tsx")
    backend = read("backend/app/routers/integrations.py")
    streamlit = read("modules/admin/integrations.py")

    for label in (
        "METRC Integrations",
        "METRC User API Key",
        "METRC State",
        "METRC License / Facility",
        "Test Connection",
        "Save",
        "Clear / Reset",
    ):
        assert label in source
        assert label in streamlit

    assert 'if context.role == "dev"' in backend
    assert 'result["doobie"] = service.public' in backend
    assert 'if context.role != "dev":' in backend
    assert "Level DEV access is required for platform AI settings." in backend


def test_dev_surface_preserves_doobie_and_metrc_controls_with_audited_reset():
    source = read("frontend/src/pages/IntegrationsPage.tsx")
    backend = read("backend/app/routers/integrations.py")
    service = read("modules/integrations/service.py")
    streamlit = read("modules/admin/integrations.py")

    for label in (
        "AI & METRC Integrations",
        "Doobie Base URL",
        "Doobie Service API Key",
        "Clear / Reset",
    ):
        assert label in source
        assert label in streamlit

    assert '@router.post("/metrc/clear")' in backend
    assert '@router.post("/doobie/clear")' in backend
    assert "configuration_cleared" in service
    assert "AuditEvent" in service
    assert 'scope_type="user"' in backend
    assert 'scope_type="platform"' in backend
    assert "metrc_scope_key(context)" in backend
