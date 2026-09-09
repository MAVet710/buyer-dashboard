from __future__ import annotations

import re
import tomllib
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

    _require("name: doobielogic-api" in source, "Render API service is missing.")
    _require("runtime: docker" in source, "Render API must use the reviewed Docker runtime.")
    plans = re.findall(r"^\s*plan:\s*([^#\n]+)", source, flags=re.MULTILINE)
    _require(plans == ["free"], f"Render must define exactly one free plan, found: {plans}")
    _require("autoDeployTrigger: checksPass" in source, "Render deploys must wait for GitHub checks.")
    _require("api.doobielogic.io" in source, "Render API custom domain is missing.")
    _require("healthCheckPath: /health/ready" in source, "Render must use database-backed readiness.")
    _require("predeploycommand" not in lowered, "Render free services cannot depend on paid pre-deploy commands.")
    _require("alembic upgrade head" in source, "Free Render startup must apply idempotent Alembic migrations.")
    _require("RENDER_EXTERNAL_HOSTNAME" in source, "Render startup must trust the provider-assigned hostname without hardcoding it.")
    _require("AI_ALLOW_CLOUD_FALLBACK" in source and 'value: "false"' in source, "Cloud AI fallback must stay disabled.")

    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "INTEGRATION_ENCRYPTION_KEY",
    ):
        pattern = rf"- key: {re.escape(key)}\n\s+sync: false"
        _require(re.search(pattern, source) is not None, f"{key} must be supplied out-of-band as a Render secret.")


def _verify_netlify() -> None:
    raw = (ROOT / "netlify.toml").read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    build = config.get("build", {})
    environment = build.get("environment", {})

    _require(build.get("base") == "frontend", "Netlify build base must be frontend.")
    _require(build.get("publish") == "dist", "Netlify must publish the Vite dist directory.")
    command = str(build.get("command") or "")
    _require("pnpm install --frozen-lockfile" in command, "Netlify dependency installation must be lockfile-reproducible.")
    _require("pnpm build" in command, "Netlify must run the production frontend build.")
    _require(environment.get("VITE_API_URL") == "https://api.doobielogic.io", "Frontend API origin must use the production custom domain.")

    redirects = config.get("redirects", [])
    _require(
        any(rule.get("from") == "/*" and rule.get("to") == "/index.html" and rule.get("status") == 200 for rule in redirects),
        "Netlify SPA fallback rewrite is missing.",
    )
    _require("functions" not in config, "Static frontend must not introduce metered Netlify Functions.")


def _verify_no_billable_google_workflows() -> None:
    # These tokens identify executable Google control-plane / registry wiring. The
    # zero-cost contract intentionally rejects them anywhere under Actions so a
    # side workflow cannot quietly reintroduce a billable path later.
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
    _require("domain aliases to the free Netlify site" in source, "Storefront alias workflow must describe the free-host handoff.")
    _require("50-alias free-host operating limit" in source, "Storefront alias workflow must bound the approved alias set.")


def main() -> None:
    _verify_render()
    _verify_netlify()
    _verify_no_billable_google_workflows()
    _verify_manual_database_mutations_are_gated()
    _verify_storefront_alias_workflow_is_validation_only()
    print(
        "Zero-cost deployment contract verified: Netlify static frontend + Render free API; "
        "all GitHub workflows are free of Google control-plane/registry wiring and data mutations are explicitly gated."
    )


if __name__ == "__main__":
    main()
