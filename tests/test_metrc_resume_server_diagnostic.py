from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_resume_start_hook_is_explicit_and_off_by_default():
    source = (ROOT / "backend" / "app" / "__init__.py").read_text(encoding="utf-8")
    assert "METRC_RESUME_DIAGNOSTIC_RUN_ID" in source
    assert "if not run_id" in source
    assert "run_server_resume_diagnostic" in source


def test_server_resume_diagnostic_is_get_only_and_sandbox_scoped():
    source = (ROOT / "backend" / "app" / "services" / "metrc_resume_diagnostics.py").read_text(encoding="utf-8")
    assert "requests.get(" in source
    assert "requests.post(" not in source
    assert "requests.put(" not in source
    assert "requests.delete(" not in source
    assert 'resolve_metrc_base_url("MA", environment="sandbox")' in source
    assert '"mutations_sent": 0' in source
    assert 'metrc.environment == "sandbox"' in source
    assert "metrc.trusted_mapping" in source


def test_server_resume_diagnostic_records_exactly_once_run_marker():
    source = (ROOT / "backend" / "app" / "services" / "metrc_resume_diagnostics.py").read_text(encoding="utf-8")
    assert 'AuditEvent.entity_type == "metrc_resume_diagnostic"' in source
    assert 'AuditEvent.action == "completed"' in source
    assert 'entity_type="metrc_resume_diagnostic"' in source
    assert 'action="completed"' in source
