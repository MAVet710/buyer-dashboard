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


def _verify_no_billable_google_release_path() -> None:
    forbidden = (
        "google-github-actions/",
        "gcloud ",
        "GCP_PROJECT_ID",
        "GCP_SERVICE_ACCOUNT",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "us-east1-docker.pkg.dev",
        "cloud run",
        "artifact registry",
    )
    for name in ("deploy.yml", "rc-preview.yml", "post-deploy-performance-smoke.yml"):
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        lowered = source.casefold()
        for token in forbidden:
            _require(token.casefold() not in lowered, f"{name} still contains paid-Google release dependency: {token}")


def main() -> None:
    _verify_render()
    _verify_netlify()
    _verify_no_billable_google_release_path()
    print("Zero-cost deployment contract verified: Netlify static frontend + Render free API, no paid-Google release path.")


if __name__ == "__main__":
    main()
