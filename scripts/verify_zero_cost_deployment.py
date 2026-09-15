from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _verify_pc_hosted_contract() -> None:
    invariants = _read("docs/PROJECT_INVARIANTS.md")
    api_client = _read("frontend/src/lib/api.ts")
    auth_gate = _read("frontend/src/components/AuthGate.tsx")

    _require("Cloudflare HTTPS/Tunnel" in invariants, "PC-hosted Cloudflare Tunnel invariant is missing.")
    _require("Caddy on loopback `8080`" in invariants, "Caddy :8080 invariant is missing.")
    _require("FastAPI on loopback `8010`" in invariants, "FastAPI :8010 invariant is missing.")
    _require("Auth gateway on `54321`" in invariants, "Local Supabase Auth :54321 invariant is missing.")
    _require('const API_URL = import.meta.env.VITE_API_URL ?? "";' in api_client, "Production API client must retain same-origin support.")
    _require('/api/v1/account/username-login' in auth_gate, "Durable username login route is missing from the frontend.")

    for path in (
        "doobie_settings.py",
        "services/doobie_connection.py",
        "services/doobie_config.py",
        "services/license_client.py",
    ):
        source = _read(path)
        _require('DEFAULT_DOOBIE_BASE_URL = "http://127.0.0.1:8010"' in source, f"{path} must default to the local FastAPI listener.")


def _verify_retired_hosting_is_absent() -> None:
    retired_blueprint = "ren" + "der.yaml"
    retired_worker = Path("deploy") / "cloudflare" / "worker.mjs"
    retired_worker_test = Path("deploy") / "cloudflare" / "worker.test.mjs"
    retired_wrangler = Path("deploy") / "cloudflare" / "wrangler.jsonc"

    for relative in (Path(retired_blueprint), retired_worker, retired_worker_test, retired_wrangler):
        _require(not (ROOT / relative).exists(), f"Retired hosted deployment artifact must stay deleted: {relative}")

    retired_domain = "on" + "render.com"
    retired_env_prefix = "REN" + "DER_"
    retired_autodeploy = "autoDeployTrigger: checksPass"
    scan_paths: list[Path] = []
    for directory in (WORKFLOWS, ROOT / "deploy", ROOT / "backend", ROOT / "services", ROOT / "frontend"):
        if not directory.exists():
            continue
        scan_paths.extend(path for path in directory.rglob("*") if path.is_file())
    scan_paths.extend(ROOT / name for name in ("doobie_settings.py", "Dockerfile.api") if (ROOT / name).exists())

    violations: list[str] = []
    for path in scan_paths:
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if retired_domain in source.casefold():
            violations.append(f"{path.relative_to(ROOT)}: retired hosted domain")
        if retired_env_prefix in source:
            violations.append(f"{path.relative_to(ROOT)}: retired hosted environment variable")
        if retired_autodeploy in source:
            violations.append(f"{path.relative_to(ROOT)}: retired hosted auto-deploy trigger")
    _require(not violations, "Retired hosted deployment wiring detected: " + "; ".join(violations))


def _verify_release_workflow_is_validation_only() -> None:
    source = _read(".github/workflows/deploy.yml")
    _require("name: Deploy to DoobieLogic" in source, "Release workflow name changed and would break workflow_run consumers.")
    _require("PC-hosted" in source, "Release workflow must be explicitly PC-hosted.")
    _require("python scripts/verify_zero_cost_deployment.py" in source, "Release workflow must enforce the local-first deployment contract.")
    _require("Build API release image locally" in source, "Release workflow must validate the API build locally in CI.")
    _require("No external deployment is performed by this workflow" in source, "Release workflow must state that GitHub does not deploy production.")
    _require("ops.doobielogic.io" in source, "Operator hostname must remain part of the release contract.")
    _require("127.0.0.1" in source, "Local runtime contract must remain represented in the release workflow.")


def _verify_no_billable_google_workflows() -> None:
    forbidden = (
        "google-github-actions/",
        "gcloud ",
        "GCP_PROJECT_ID",
        "GCP_SERVICE_ACCOUNT",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "docker.pkg.dev",
    )
    violations: list[str] = []
    for path in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        source = path.read_text(encoding="utf-8")
        lowered = source.casefold()
        for token in forbidden:
            if token.casefold() in lowered:
                violations.append(f"{path.name}: {token}")
    _require(not violations, "Billable Google workflow dependency detected: " + "; ".join(violations))


def _verify_manual_database_mutations_are_gated() -> None:
    contracts = (
        ("seed-cowboy-kush-demo.yml", "I_APPROVE_COWBOY_KUSH_DEMO_SEED", "python -m scripts.seed_cowboy_kush_ma_coa_demo --apply"),
        ("reset-dev-sandbox-vertical-inventory.yml", "I_APPROVE_DEV_SANDBOX_RESET", "python -m modules.coman.dev_sandbox_reset_job --apply"),
    )
    for name, approval, mutation_command in contracts:
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        _require("workflow_dispatch:" in source, f"{name} must retain an explicit manual trigger.")
        _require(approval in source, f"{name} is missing its exact approval phrase.")
        _require("github.event_name == 'workflow_dispatch'" in source, f"{name} mutation job is not manual-only.")
        _require("inputs.confirmation ==" in source, f"{name} mutation job does not bind the confirmation input.")
        _require(mutation_command in source, f"{name} reviewed mutation command changed unexpectedly.")
        _require("DL_PROD_DB_URL: ${{ secrets.DL_PROD_DB_URL }}" in source, f"{name} must receive its write credential only from GitHub secrets.")


def _verify_storefront_alias_workflow_is_validation_only() -> None:
    source = (WORKFLOWS / "storefront-domain-mappings.yml").read_text(encoding="utf-8")
    _require("validate_storefront_domains.py" in source, "Storefront alias workflow must validate the approved domain file.")
    _require("Cloudflare Tunnel" in source and "PC-hosted Caddy" in source, "Storefront aliases must describe the active tunnel-to-PC routing model.")
    _require("never creates DNS or cloud resources" in source, "Storefront domain validation must remain non-mutating.")


def main() -> None:
    _verify_pc_hosted_contract()
    _verify_retired_hosting_is_absent()
    _verify_release_workflow_is_validation_only()
    _verify_no_billable_google_workflows()
    _verify_manual_database_mutations_are_gated()
    _verify_storefront_alias_workflow_is_validation_only()
    print(
        "Zero-cost deployment contract verified: ops.doobielogic.io -> Cloudflare Tunnel -> "
        "PC-hosted Caddy :8080 -> FastAPI :8010 -> local Supabase Auth :54321; no retired hosted deployment wiring."
    )


if __name__ == "__main__":
    main()
