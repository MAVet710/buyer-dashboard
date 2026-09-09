from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_post_release_workflow_run_consumers_are_bound_to_main():
    for name in (
        "database-backup.yml",
        "ma-metrc-sandbox-readonly.yml",
        "post-deploy-performance-smoke.yml",
        "ai-runtime-revision-guard.yml",
    ):
        source = _workflow(name)
        assert 'workflows: ["Deploy to DoobieLogic"]' in source, name
        assert "github.event.workflow_run.conclusion == 'success'" in source, name
        assert "github.event.workflow_run.head_branch == 'main'" in source, name


def test_automatic_ma_metrc_gate_is_read_only_and_redacts_uploaded_evidence():
    source = _workflow("ma-metrc-sandbox-readonly.yml")
    assert "validate_ma_metrc_sandbox.py --live-read" in source
    assert "--allow-write" not in source
    assert "I_APPROVE_MA_SANDBOX_WRITE" not in source
    assert "artifacts/metrc-readonly-safe/summary.json" in source
    assert "artifacts/metrc-readonly/provider-evidence.json" not in _artifact_upload_paths(source)


def test_backup_proves_auth_and_restore_before_retaining_encrypted_artifact():
    source = _workflow("database-backup.yml")
    auth = source.index("Prove production backup credentials before dumping")
    dump = source.index("Create consistent production backup")
    restore = source.index("Prove the backup restores")
    encrypt = source.index("Encrypt and checksum backup")
    retain = source.index("Retain encrypted backup")
    assert auth < dump < restore < encrypt < retain
    assert "PGCONNECT_TIMEOUT=15" in source
    assert "select count(*) from alembic_version" in source
    assert "AES256" in source


def test_all_action_workflows_are_free_of_google_control_plane_wiring():
    forbidden = (
        "google-github-actions/",
        "gcloud ",
        "GCP_PROJECT_ID",
        "GCP_SERVICE_ACCOUNT",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "docker.pkg.dev",
    )
    for path in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token.casefold() not in source.casefold(), (path.name, token)


def test_render_blueprint_is_free_only_and_waits_for_checks():
    source = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "name: doobielogic-api" in source
    assert "runtime: docker" in source
    assert source.count("plan: free") == 1
    assert "autoDeployTrigger: checksPass" in source
    assert "healthCheckPath: /health/ready" in source
    assert "api.doobielogic.io" in source
    assert "preDeployCommand" not in source
    assert "alembic upgrade head" in source
    assert "RENDER_EXTERNAL_HOSTNAME" in source
    assert "AI_ALLOW_CLOUD_FALLBACK" in source
    assert '- key: AI_PROVIDER_MODE\n        value: disabled' in source
    assert '- key: AI_PROVIDER_ORDER\n        value: none' in source
    assert '- key: AI_ALLOW_CLOUD_FALLBACK\n        value: "false"' in source
    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
    ):
        assert f"- key: {key}\n        sync: false" in source


def test_netlify_frontend_is_static_and_lockfile_reproducible():
    config = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))
    build = config["build"]
    assert build["base"] == "frontend"
    assert build["publish"] == "dist"
    assert "pnpm install --frozen-lockfile" in build["command"]
    assert "pnpm build" in build["command"]
    assert build["environment"]["VITE_API_URL"] == "https://api.doobielogic.io"
    assert "functions" not in config
    assert any(
        rule.get("from") == "/*" and rule.get("to") == "/index.html" and rule.get("status") == 200
        for rule in config.get("redirects", [])
    )


def test_post_deploy_latency_gate_is_public_only_and_free_tier_aware():
    source = _workflow("post-deploy-performance-smoke.yml")
    assert "/health/ready" in source
    assert "github.event.workflow_run.head_sha" in source
    assert "FREE_COLD_START_LIMIT_SECONDS" in source
    assert "WARM_P95_LIMIT_SECONDS" in source
    assert "schema_matches == true" in source
    assert "DATABASE_URL" not in source
    assert "password" not in source.casefold()


def test_hosted_ai_audit_is_provider_neutral_and_fail_closed():
    source = _workflow("ai-runtime-revision-guard.yml")
    assert "python scripts/verify_zero_cost_deployment.py" in source
    assert "AI_PROVIDER_MODE" in source
    assert "AI_ALLOW_CLOUD_FALLBACK" in source
    assert "GEMINI_API_KEY" in source
    assert "OPENAI_API_KEY" in source
    assert "Hosted Render API remains decoupled" in source


def test_database_mutation_workflows_are_manual_and_exactly_confirmed():
    contracts = (
        (
            "seed-cowboy-kush-demo.yml",
            "I_APPROVE_COWBOY_KUSH_DEMO_SEED",
            "python -m scripts.seed_cowboy_kush_ma_coa_demo --apply",
        ),
        (
            "reset-dev-sandbox-vertical-inventory.yml",
            "I_APPROVE_DEV_SANDBOX_RESET",
            "python -m modules.coman.dev_sandbox_reset_job --apply",
        ),
    )
    for name, approval, mutation in contracts:
        source = _workflow(name)
        assert "workflow_dispatch:" in source
        assert approval in source
        assert "github.event_name == 'workflow_dispatch'" in source
        assert "inputs.confirmation ==" in source
        assert mutation in source
        assert "DL_PROD_DB_URL: ${{ secrets.DL_PROD_DB_URL }}" in source
        assert "Automatic main-push behavior: validation only; no database write" in source


def test_storefront_domain_workflow_is_validation_only():
    source = _workflow("storefront-domain-mappings.yml")
    assert "validate_storefront_domains.py" in source
    assert "50-alias free-host operating limit" in source
    assert "domain aliases to the free Netlify site" in source
    assert "never creates DNS or cloud resources" in source


def test_zero_cost_contract_verifier_runs_in_release_and_rc():
    command = "python scripts/verify_zero_cost_deployment.py"
    assert command in _workflow("deploy.yml")
    assert command in _workflow("rc-preview.yml")


def test_rc_proves_render_free_resource_envelope_without_external_preview():
    source = _workflow("rc-preview.yml")
    assert "--memory=512m" in source
    assert "--cpus=0.10" in source
    assert "BILLABLE_CLOUD_RESOURCES=none" in source
    assert "Smoke test local synthetic API and static frontend pair" in source


def test_browser_ci_uses_locked_playwright_dependency():
    source = _workflow("web-ci.yml")
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    lockfile = (ROOT / "frontend" / "pnpm-lock.yaml").read_text(encoding="utf-8")
    assert '"@playwright/test": "1.55.0"' in package
    assert "@playwright/test" in lockfile
    assert "pnpm add --save-dev @playwright/test" not in source
    assert "--lockfile=false" not in source
    assert "playwright-chromium-${{ runner.os }}-1.55.0" in source


def _artifact_upload_paths(source: str) -> str:
    """Return only upload-artifact path blocks so private working files can exist safely."""
    blocks: list[str] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if "uses: actions/upload-artifact@" not in line:
            continue
        blocks.extend(lines[index : index + 12])
    return "\n".join(blocks)
