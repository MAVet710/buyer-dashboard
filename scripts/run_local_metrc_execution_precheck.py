#!/usr/bin/env python3
"""Run the local DoobieLogic auth + MA Metrc GET-only execution precheck.

This command is designed for Nelson's Windows-hosted DoobieLogic stack. It does
not reset credentials, create users, rotate Metrc keys, or send provider
mutations. It combines the existing safe username diagnostic with the existing
GET-only Massachusetts Metrc rebaseline and writes one local evidence artifact.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from backend.app.config import Settings
from backend.app.database import get_engine
from backend.app.services.metrc_evaluation_rebaseline import run_server_evaluation_rebaseline
from scripts.diagnose_local_username_login import diagnose


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "http://127.0.0.1:8080"


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _auth_healthy(report: dict[str, Any]) -> bool:
    return bool(
        report.get("local_api_healthy")
        and report.get("username_login_route_registered")
        and report.get("app_user_found")
        and report.get("app_user_active")
        and report.get("auth_identity_found")
        and report.get("identity_id_match")
        and report.get("server_supabase_url_configured")
        and report.get("server_supabase_normal_auth_key_configured")
    )


def _default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"local-precheck-{stamp}"[:36]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PC-hosted DoobieLogic login diagnostic and GET-only MA Metrc execution precheck."
    )
    parser.add_argument("--username", default="God")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Defaults to artifacts/metrc-evaluation/local-execution-precheck-<run-id>.json.",
    )
    args = parser.parse_args()

    run_id = str(args.run_id or _default_run_id()).strip()[:36]
    auth = diagnose(args.username, args.api_url)
    auth_ok = _auth_healthy(auth)

    metrc: dict[str, Any]
    metrc_error = ""
    try:
        metrc = run_server_evaluation_rebaseline(get_engine(), Settings(), run_id)
    except Exception as exc:
        # Preserve only the exception class. Provider/database connection strings,
        # credentials, and secret-bearing exception text must not enter evidence.
        metrc = {
            "run_id": run_id,
            "status": "failed",
            "read_only": True,
            "mutations_sent": 0,
            "secrets_included": False,
        }
        metrc_error = type(exc).__name__

    facility_count = int(metrc.get("facility_count") or 0)
    metrc_ok = bool(
        metrc.get("read_only") is True
        and int(metrc.get("mutations_sent") or 0) == 0
        and (facility_count > 0 or metrc.get("status") == "already_completed")
    )

    result = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "hosting_contract": {
            "application_host": "local_windows_pc",
            "public_edge": "cloudflare_tunnel",
            "vite_port": 5173,
            "fastapi_port": 8080,
            "port_8000_is_doobielogic": False,
        },
        "auth": auth,
        "auth_healthy": auth_ok,
        "metrc_rebaseline": metrc,
        "metrc_error_class": metrc_error,
        "metrc_precheck_healthy": metrc_ok,
        "provider_mutations_sent": 0,
        "credentials_changed": False,
        "user_changed": False,
        "ready_for_family_execution_plan": bool(auth_ok and metrc_ok),
    }

    output = Path(args.output) if args.output else Path(
        f"artifacts/metrc-evaluation/local-execution-precheck-{run_id}.json"
    )
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"Evidence written: {output}")
    raise SystemExit(0 if result["ready_for_family_execution_plan"] else 2)


if __name__ == "__main__":
    main()
