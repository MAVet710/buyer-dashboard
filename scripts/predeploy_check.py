from __future__ import annotations

import os
import sys
from pathlib import Path

REQUIRED_FILES = ["Dockerfile.api", "frontend/Dockerfile", "frontend/dist/index.html", "deploy/cloudbuild-api.yaml", "migrations/versions/0037_supabase_function_acl_hardening.py"]
REQUIRED_ENV = ["DATABASE_URL", "SUPABASE_URL", "SUPABASE_JWKS_URL", "SUPABASE_SERVICE_ROLE_KEY", "INTEGRATION_ENCRYPTION_KEY"]

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing_files = [name for name in REQUIRED_FILES if not (root / name).exists()]
    missing_env = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    failures = []
    if missing_files: failures.append(f"missing files: {', '.join(missing_files)}")
    if missing_env: failures.append(f"missing environment: {', '.join(missing_env)}")
    if os.environ.get("CORS_ORIGINS") != "https://ops.doobielogic.io": failures.append("CORS_ORIGINS must equal https://ops.doobielogic.io")
    hosts = os.environ.get("ALLOWED_HOSTS", "")
    if "api.doobielogic.io" not in hosts: failures.append("ALLOWED_HOSTS must include api.doobielogic.io")
    if failures:
        print("Predeploy check failed:")
        for failure in failures: print(f"- {failure}")
        return 1
    print("Predeploy configuration contract passed.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
