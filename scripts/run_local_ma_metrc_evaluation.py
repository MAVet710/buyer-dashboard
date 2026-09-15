#!/usr/bin/env python3
"""Run one bounded MA Metrc evaluation action from the PC-hosted stack.

This local launcher reuses the existing encrypted, trusted, facility-scoped
Metrc sandbox credentials already saved in DoobieLogic. It never prints raw
credentials, never provisions or rotates keys, and never calls integrator setup.

Write operations require both:
- this checkout's HEAD to equal origin/main; and
- the exact I_APPROVE_MA_SANDBOX_WRITE confirmation.

The actual workbook validation, facility preflight, source-state preflight,
provider request, and provider readback remain owned by run_ma_metrc_evaluation.py.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.database import get_engine
from backend.app.services.metrc_context import resolve_metrc_context
from modules.integrations.models import IntegrationConfiguration
from scripts.metrc_workflow_policy import authorize_operation


WRITE_CONFIRMATION = "I_APPROVE_MA_SANDBOX_WRITE"


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _require_current_origin_main() -> str:
    head = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "origin/main")
    if not head or head != origin_main:
        raise RuntimeError(
            "Local MA sandbox execution is blocked because this checkout is not the exact current origin/main commit."
        )
    return head


def _scope_user_id(row: IntegrationConfiguration) -> str:
    scope = str(row.scope_key or "")
    if "|" in scope:
        return scope.split("|", 1)[0].strip()
    return str(row.updated_by or "local-metrc-evaluation").strip()


def _saved_credentials_for_license(license_number: str) -> tuple[str, str]:
    wanted = str(license_number or "").strip()
    if not wanted:
        raise RuntimeError("--license-number is required when using saved local Metrc credentials.")

    settings = Settings()
    if not str(settings.integration_encryption_key or "").strip():
        raise RuntimeError("Local encrypted integration storage is not configured in this PowerShell environment.")

    engine = get_engine()
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(IntegrationConfiguration).where(
                    IntegrationConfiguration.provider == "metrc",
                    IntegrationConfiguration.scope_type == "user",
                    IntegrationConfiguration.status == "connected",
                    IntegrationConfiguration.encrypted_secret != "",
                    IntegrationConfiguration.organization_id.is_not(None),
                    IntegrationConfiguration.facility_id.is_not(None),
                )
            )
        )

    unique_pairs: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        organization_id = str(row.organization_id or "").strip()
        facility_id = str(row.facility_id or "").strip()
        if not organization_id or not facility_id:
            continue
        context = RequestContext(
            _scope_user_id(row),
            organization_id,
            facility_id,
            "dev",
        )
        _service, metrc = resolve_metrc_context(engine, settings, context)
        if not (
            metrc.configured
            and metrc.trusted_mapping
            and metrc.status.casefold() == "connected"
            and metrc.environment.casefold() == "sandbox"
            and metrc.state.upper() == "MA"
            and metrc.license_number == wanted
            and metrc.integrator_api_key
            and metrc.user_api_key
            and metrc.integrator_api_key != metrc.user_api_key
        ):
            continue
        pair = (metrc.integrator_api_key, metrc.user_api_key)
        unique_pairs[pair] = pair

    if not unique_pairs:
        raise RuntimeError(
            f"No connected, trusted, encrypted MA sandbox credential pair is saved for license {wanted}."
        )
    if len(unique_pairs) != 1:
        raise RuntimeError(
            f"Multiple distinct saved MA sandbox credential pairs match license {wanted}; refusing to guess."
        )
    return next(iter(unique_pairs.values()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded MA sandbox evaluation action using DoobieLogic's saved local Metrc connection."
    )
    parser.add_argument("--operation", required=True)
    parser.add_argument("--payload-file", default="")
    parser.add_argument("--output", default="artifacts/metrc-evaluation/latest.json")
    parser.add_argument("--facility-family", default="")
    parser.add_argument("--license-number", required=True)
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()

    _require_current_origin_main()
    try:
        policy = authorize_operation(
            args.operation,
            github_ref="refs/heads/main",
            confirmation=args.confirmation,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    if policy["classification"] == "write" and args.confirmation != WRITE_CONFIRMATION:
        raise RuntimeError(f"MA Metrc sandbox writes require confirmation: {WRITE_CONFIRMATION}")

    integrator_key, user_key = _saved_credentials_for_license(args.license_number)

    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(ROOT)
    child_env["METRC_INTEGRATOR_API_KEY"] = integrator_key
    child_env["METRC_MA_SANDBOX_USER_API_KEY"] = user_key
    # Remove generic aliases so a stale shell value can never conflict with the
    # exact trusted facility-scoped credentials selected above.
    child_env.pop("METRC_USER_API_KEY", None)
    child_env.pop("METRC_LICENSE_NUMBER", None)
    child_env.pop("METRC_MA_SANDBOX_LICENSE_NUMBER", None)

    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_ma_metrc_evaluation.py"),
        "--operation",
        args.operation,
        "--output",
        args.output,
        "--license-number",
        args.license_number,
    ]
    if args.payload_file:
        command.extend(["--payload-file", args.payload_file])
    if args.facility_family:
        command.extend(["--facility-family", args.facility_family])

    completed = subprocess.run(command, cwd=ROOT, env=child_env, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
