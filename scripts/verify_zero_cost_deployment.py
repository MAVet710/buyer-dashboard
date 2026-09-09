from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _verify_render() -> None:
    source = _read("render.yaml")
    lowered = source.casefold()
    api = source.split("name: doobielogic-api", 1)[1].split("name: doobielogic-ops", 1)[0] if "name: doobielogic-api" in source and "name: doobielogic-ops" in source else ""
    static = source.split("name: doobielogic-ops", 1)[1] if "name: doobielogic-ops" in source else ""
    db_source = _read("modules/coman/db.py")

    _require("name: doobielogic-api" in source, "Render API service is missing.")
    _require("name: doobielogic-ops" in source, "Render static frontend is missing.")
    _require("runtime: python" in source, "Render API must use the lean native Python runtime.")
    _require("runtime: static" in source, "Render frontend must be a static site.")
    plans = re.findall(r"^\s*plan:\s*([^#\n]+)", source, flags=re.MULTILINE)
    _require(plans == ["free"], f"Render compute must define exactly one free plan, found: {plans}")
    _require(source.count("autoDeployTrigger: checksPass") == 2, "Both Render services must wait for GitHub checks.")
    _require("api.doobielogic.io" in source, "Render API custom domain is missing.")
    _require("ops.doobielogic.io" in source and "doobielogic.io" in source, "Render frontend custom domains are incomplete.")
    _require("healthCheckPath: /health/ready" in source, "Render API must use database-backed readiness.")
    _require("predeploycommand" not in lowered, "Render free services cannot depend on paid pre-deploy commands.")
    _require("alembic upgrade head" not in api, "The public Render web runtime must not receive schema-DDL authority.")
    _require("RENDER_EXTERNAL_HOSTNAME" in api, "Render startup must trust the provider-assigned hostname without hardcoding it.")
    _require("RENDER_GIT_COMMIT" in api, "Render API must expose the exact deployed commit as release identity.")
    _require("backend/requirements.txt" in source, "Render API must not install the oversized Streamlit root environment.")
    _require('- key: DATABASE_POOL_SIZE\n        value: "1"' in api, "Render Free API must reserve Supabase headroom with a one-connection pool.")
    _require('- key: DATABASE_MAX_OVERFLOW\n        value: "0"' in api, "Render Free API must not overflow the Supabase connection pool.")
    _require("--workers" not in api, "Render Free API must not multiply database connections with extra Uvicorn workers.")
    _require("SEALED_DATABASE_URL_PATH" in api and "deploy/sealed/render_database_url.json" in api, "Render API must point at the repository-safe sealed database credential.")
    _require("DATABASE_SEAL_PRIVATE_KEY" in api, "Render API must receive the sealed-database private key out-of-band.")
    _require("X25519PrivateKey" in db_source and "AESGCM" in db_source and "HKDF" in db_source, "Database loader must authenticate and decrypt the sealed credential.")
    _require("pnpm install --frozen-lockfile" in source and "pnpm build" in source, "Render static frontend must use the locked production build.")
    _require("staticPublishPath: ./frontend/dist" in source, "Render must publish the Vite dist directory.")
    _require("source: /*" in source and "destination: /index.html" in source, "Render SPA fallback rewrite is missing.")
    _require("RENDER_GIT_COMMIT" in static and "release.json" in static, "Render static frontend must publish exact commit identity.")
    _require("path: /release.json" in static and "no-store, no-cache, must-revalidate" in static, "Static release identity must never be served from cache.")
    _require("AI_ALLOW_CLOUD_FALLBACK" in source and 'value: "false"' in source, "Cloud AI fallback must stay disabled.")
    _require("RESEND_API_KEY" in api, "Render API must use HTTPS transactional mail instead of blocked SMTP egress.")
    _require("SPACEMAIL_SMTP_PASSWORD" not in api, "Render Free API must not depend on SMTP credentials.")

    for key in (
        "DATABASE_URL",
        "DATABASE_SEAL_PRIVATE_KEY",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
        "RESEND_API_KEY",
        "VITE_SUPABASE_URL",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    ):
        pattern = rf"- key: {re.escape(key)}\n\s+sync: false"
        _require(re.search(pattern, source) is not None, f"{key} must be supplied out-of-band to Render.")

    sealed = ROOT / "deploy" / "sealed" / "render_database_url.json"
    if sealed.exists():
        payload = json.loads(sealed.read_text(encoding="utf-8"))
        _require(payload.get("version") == 1, "Sealed database credential version is invalid.")
        _require(payload.get("algorithm") == "X25519-HKDF-SHA256-AES256GCM", "Sealed database credential algorithm changed unexpectedly.")
        _require(bool(payload.get("ciphertext")), "Sealed database credential contains no ciphertext.")
        _require("postgres" not in json.dumps(payload).casefold(), "Sealed database file must not contain a plaintext PostgreSQL URL.")

    _require("SUPABASE_SERVICE_ROLE_KEY" not in source, "The baseline hosted runtime must not require a privileged Supabase service-role key.")
    _require(not (ROOT / "netlify.toml").exists(), "Netlify config must not coexist with the canonical Render deployment contract.")


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
    _require("domain aliases to the free Render static site" in source, "Storefront alias workflow must describe the free-host handoff.")
    _require("50-alias free-host operating limit" in source, "Storefront alias workflow must bound the approved alias set.")
    _require("never creates DNS or cloud resources" in source, "Storefront domain validation must remain non-mutating.")


def main() -> None:
    _verify_render()
    _verify_no_billable_google_workflows()
    _verify_manual_database_mutations_are_gated()
    _verify_storefront_alias_workflow_is_validation_only()
    print(
        "Zero-cost deployment contract verified: Render static frontend + Render free API + Supabase; "
        "sealed database credentials, HTTPS transactional email, no web-runtime DDL, no Google control-plane/registry wiring, and explicitly gated data mutations."
    )


if __name__ == "__main__":
    main()
