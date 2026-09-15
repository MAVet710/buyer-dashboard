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
    assert "local-runtime-release-gate:\n    needs: parity-release-gate" in workflow


def test_pc_hosted_release_preserves_runtime_identity_without_external_application_deployment():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "RELEASE_ID: ${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "Cloudflare Tunnel" in workflow
    assert "Caddy on 127.0.0.1:8080" in workflow
    assert "FastAPI on 127.0.0.1:8010" in workflow
    assert "existing hosted DoobieLogic Supabase project" in workflow
    assert "https://fovxtygwcxubjzjgovva.supabase.co" in workflow
    assert "No external application deployment is performed by this workflow" in workflow
    assert "127.0.0.1:54321" not in workflow


def test_pc_hosted_runtime_preserves_secrets_as_out_of_band_configuration():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    config = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")

    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
    ):
        assert key in workflow or key in config
    assert "SUPABASE_SERVICE_ROLE_KEY=test" not in workflow


def test_local_ai_runtime_uses_durable_declared_configuration():
    config = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ai-runtime-revision-guard.yml").read_text(encoding="utf-8")

    assert 'ai_provider_mode: str = "local_only"' in config
    assert 'ai_provider_order: str = "local"' in config
    assert 'ai_allow_cloud_fallback: bool = False' in config
    assert "LOCAL_AI_RUNTIME_STATE" in workflow
    assert "LOCAL_LLM_BASE_URL" in workflow
    assert "LOCAL_LLM_MODEL" in workflow
    assert "gcloud run revisions list" not in workflow
    assert "--to-revisions" not in workflow
    assert "paid cloud AI fallback" in workflow


def test_eight_phase_execution_control_exists():
    control = (ROOT / "PARITY_EXECUTION_CONTROL.md").read_text(encoding="utf-8")
    for number in range(1, 9):
        assert f"### Phase {number}" in control
    assert "A page name, route, API endpoint, or similar-looking component is not sufficient evidence." in control
