from pathlib import Path


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
    assert "doobielogic_backup_runtime.fovxtygwcxubjzjgovva" in source
    assert "doobielogic-backup-db-v1" in source
    assert "aws-1-us-east-2.pooler.supabase.com" in source
    assert "--schema=public" in source
    assert "DATABASE_BACKUP_URL" not in source
    assert "DL_PROD_DB_URL" not in source
    assert "pull_request:" not in source


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


def test_retired_hosting_blueprint_and_worker_are_absent():
    retired = (
        ROOT / ("ren" + "der.yaml"),
        ROOT / "deploy" / "cloudflare" / "worker.mjs",
        ROOT / "deploy" / "cloudflare" / "worker.test.mjs",
        ROOT / "deploy" / "cloudflare" / "wrangler.jsonc",
    )
    for path in retired:
        assert not path.exists(), path


def test_pc_hosted_release_is_validation_only_and_preserves_operator_url_and_supabase():
    source = _workflow("deploy.yml")
    assert "Build API release image locally" in source
    assert "Verify PC-hosted API startup contract" in source
    assert "https://ops.doobielogic.io" in source
    assert "Cloudflare Tunnel" in source
    assert "Caddy on 127.0.0.1:8080" in source
    assert "FastAPI on 127.0.0.1:8010" in source
    assert "existing hosted DoobieLogic Supabase project" in source
    assert "https://fovxtygwcxubjzjgovva.supabase.co" in source
    assert "127.0.0.1:54321" not in source
    assert "No external application deployment is performed by this workflow" in source
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source


def test_public_runtime_latency_gate_uses_ops_domain_and_pc_hosted_path():
    source = _workflow("post-deploy-performance-smoke.yml")
    assert "PRODUCTION_ORIGIN: https://ops.doobielogic.io" in source
    assert "$PRODUCTION_ORIGIN/health/ready" in source
    assert "RUNTIME_RECOVERY_LIMIT_SECONDS" in source
    assert "WARM_P95_LIMIT_SECONDS" in source
    assert "schema_matches == true" in source
    assert "Cloudflare Tunnel -> PC-hosted Caddy -> FastAPI" in source
    assert "api.doobielogic.io" not in source
    assert "github.event.workflow_run.head_sha" not in source
    assert "DATABASE_URL" not in source
    assert "password" not in source.casefold()


def test_local_ai_audit_is_fail_closed_and_provider_neutral():
    source = _workflow("ai-runtime-revision-guard.yml")
    assert "python scripts/verify_zero_cost_deployment.py" in source
    assert 'ai_provider_mode: str = "local_only"' in source
    assert 'ai_provider_order: str = "local"' in source
    assert 'ai_allow_cloud_fallback: bool = False' in source
    assert "LOCAL_AI_RUNTIME_STATE" in source
    assert "LOCAL_LLM_BASE_URL" in source
    assert "LOCAL_LLM_MODEL" in source
    assert "paid cloud AI fallback" in source


def test_database_mutation_workflows_are_manual_and_exactly_confirmed():
    contracts = (
        ("seed-cowboy-kush-demo.yml", "I_APPROVE_COWBOY_KUSH_DEMO_SEED", "python -m scripts.seed_cowboy_kush_ma_coa_demo --apply"),
        ("reset-dev-sandbox-vertical-inventory.yml", "I_APPROVE_DEV_SANDBOX_RESET", "python -m modules.coman.dev_sandbox_reset_job --apply"),
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
    assert "Cloudflare Tunnel -> PC-hosted Caddy" in source
    assert "never creates DNS or cloud resources" in source


def test_zero_cost_contract_verifier_runs_in_release_and_rc():
    command = "python scripts/verify_zero_cost_deployment.py"
    assert command in _workflow("deploy.yml")
    assert command in _workflow("rc-preview.yml")


def test_release_and_rc_use_publishable_supabase_auth_not_service_role():
    for name in ("deploy.yml", "rc-preview.yml"):
        source = _workflow(name)
        assert "SUPABASE_PUBLISHABLE_KEY" in source
        assert "SUPABASE_SERVICE_ROLE_KEY" not in source
        assert "https://fovxtygwcxubjzjgovva.supabase.co" in source


def test_rc_proves_constrained_local_resource_envelope_without_external_preview():
    source = _workflow("rc-preview.yml")
    assert "--memory=512m" in source
    assert "--cpus=0.10" in source
    assert "BILLABLE_CLOUD_RESOURCES=none" in source
    assert "CI_MEMORY_ENVELOPE=512m" in source
    assert "CI_CPU_ENVELOPE=0.10" in source
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
    blocks: list[str] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if "uses: actions/upload-artifact@" not in line:
            continue
        blocks.extend(lines[index : index + 12])
    return "\n".join(blocks)
