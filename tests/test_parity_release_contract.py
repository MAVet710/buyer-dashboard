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


def test_production_deploy_is_blocked_until_strict_and_legacy_evidence_are_complete():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "parity-release-gate:" in workflow
    assert "python scripts/verify_streamlit_parity.py --mode release" in workflow
    assert "deploy-api:\n    needs: parity-release-gate" in workflow


def test_api_deploy_preserves_dedicated_runtime_identity():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    api_deploy = workflow.split("- name: Deploy API candidate without traffic", 1)[1].split("- name: Verify exact API candidate revision and HTTP health", 1)[0]
    assert "buyer-dash-api@${{ secrets.GCP_PROJECT_ID }}.iam.gserviceaccount.com" in api_deploy
    assert "${{ secrets.GCP_SERVICE_ACCOUNT }}" not in api_deploy


def test_api_deploy_preserves_existing_runtime_environment_and_secrets():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    api_deploy = workflow.split("- name: Deploy API candidate without traffic", 1)[1].split("- name: Verify exact API candidate revision and HTTP health", 1)[0]
    assert "--update-env-vars" in api_deploy
    assert "--update-secrets" in api_deploy
    assert "--set-env-vars" not in api_deploy
    assert "--set-secrets" not in api_deploy


def test_eight_phase_execution_control_exists():
    control = (ROOT / "PARITY_EXECUTION_CONTROL.md").read_text(encoding="utf-8")
    for number in range(1, 9):
        assert f"### Phase {number}" in control
    assert "A page name, route, API endpoint, or similar-looking component is not sufficient evidence." in control