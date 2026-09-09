from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_uses_strict_contract_mode_not_obsolete_tracker_gate():
    workflow = (ROOT / ".github" / "workflows" / "web-ci.yml").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_streamlit_parity.py").read_text(encoding="utf-8")

    assert "python scripts/verify_streamlit_parity.py --mode contract" in workflow
    assert 'STRICT_AUDIT = ROOT / "STREAMLIT_EXACT_PARITY_AUDIT.md"' in verifier
    assert 'LEGACY_EVIDENCE = ROOT / "LEGACY_STREAMLIT_PRODUCT_EVIDENCE.md"' in verifier
    assert "MIGRATION_PARITY_TRACKER.md" in verifier
    assert "retained as history only" in verifier


def test_production_release_is_blocked_until_strict_and_legacy_evidence_are_complete():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "parity-release-gate:" in workflow
    assert "python scripts/verify_streamlit_parity.py --mode release" in workflow
    assert "zero-cost-release-gate:\n    needs: parity-release-gate" in workflow


def test_render_api_preserves_provider_runtime_identity_without_cloud_service_account():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    api = blueprint.split("name: doobielogic-api", 1)[1].split("name: doobielogic-ops", 1)[0]

    assert "RENDER_EXTERNAL_HOSTNAME" in api
    assert "RENDER_GIT_COMMIT" in api
    assert "GCP_SERVICE_ACCOUNT" not in api
    assert "google-github-actions" not in api


def test_render_api_preserves_secrets_as_out_of_band_configuration():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    api = blueprint.split("name: doobielogic-api", 1)[1].split("name: doobielogic-ops", 1)[0]

    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
    ):
        assert f"- key: {key}\n        sync: false" in api
    assert "SUPABASE_SERVICE_ROLE_KEY" not in api
    assert "autoDeployTrigger: checksPass" in api


def test_local_ai_runtime_uses_durable_declared_configuration():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ai-runtime-revision-guard.yml").read_text(encoding="utf-8")

    assert '- key: AI_PROVIDER_MODE\n        value: disabled' in blueprint
    assert '- key: AI_PROVIDER_ORDER\n        value: none' in blueprint
    assert '- key: AI_ALLOW_CLOUD_FALLBACK\n        value: "false"' in blueprint
    assert "LOCAL_AI_RUNTIME_STATE" in workflow
    assert "LOCAL_LLM_BASE_URL" in workflow
    assert "LOCAL_LLM_MODEL" in workflow
    assert "gcloud run revisions list" not in workflow
    assert "historical revision" not in workflow.lower()
    assert "--to-revisions" not in workflow
    assert "hosted Render API remains decoupled" in workflow


def test_eight_phase_execution_control_exists():
    control = (ROOT / "PARITY_EXECUTION_CONTROL.md").read_text(encoding="utf-8")
    for number in range(1, 9):
        assert f"### Phase {number}" in control
    assert "A page name, route, API endpoint, or similar-looking component is not sufficient evidence." in control
