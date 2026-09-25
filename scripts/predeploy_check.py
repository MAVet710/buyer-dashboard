from __future__ import annotations

import sys
from pathlib import Path

from backend.app.config import Settings

REQUIRED_FILES = [
    "Dockerfile.api",
    "frontend/Dockerfile",
    "frontend/dist/index.html",
    "deploy/cloudbuild-api.yaml",
    "migrations/versions/0037_supabase_function_acl_hardening.py",
]


def _host_allowed(hosts: list[str], target: str) -> bool:
    return any(host == target or (host.startswith("*.") and target.endswith(host[1:])) for host in hosts)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = []
    missing_files = [name for name in REQUIRED_FILES if not (root / name).exists()]
    if missing_files:
        failures.append(f"missing files: {', '.join(missing_files)}")
    settings = Settings()
    try:
        settings.validate_production()
    except RuntimeError as exc:
        failures.append(str(exc))
    if settings.cors_origins != "https://ops.doobielogic.io":
        failures.append("CORS_ORIGINS must equal https://ops.doobielogic.io")
    if not _host_allowed(settings.trusted_hosts, "api.doobielogic.io"):
        failures.append("Trusted hosts must allow api.doobielogic.io")
    if failures:
        print("Predeploy check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Predeploy configuration contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
