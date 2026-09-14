#!/usr/bin/env python3
"""Validate the existing Massachusetts Metrc sandbox credential pair.

The live gate performs one read-only GET /facilities/v2 request.  It validates
vendor/user authentication and reports the facilities visible to the existing
API User Key.  It intentionally does not require one global license because the
evaluation contains actions that belong in different facility contexts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_evaluation_credentials import (
    MetrcEvaluationCredentialError,
    resolve_ma_sandbox_evaluation_credentials,
)


ENVIRONMENT = "sandbox"
BASE_URL, _STATE_CODE = resolve_metrc_base_url("MA", environment=ENVIRONMENT)
REQUIRED_ENV = (
    "METRC_INTEGRATOR_API_KEY",
    "METRC_MA_SANDBOX_USER_API_KEY",
)


def _value(values: dict[str, str] | os._Environ[str], name: str) -> str:
    return str(values.get(name) or "").strip()


def _facility_license_number(facility: Any) -> str:
    if not isinstance(facility, dict):
        return ""
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        value = facility.get(key)
        if value:
            return str(value).strip()
    nested = facility.get("License") or facility.get("license")
    if isinstance(nested, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            value = nested.get(key)
            if value:
                return str(value).strip()
    return ""


def readiness(environ: dict[str, str] | None = None) -> dict[str, Any]:
    values = environ if environ is not None else os.environ
    missing: list[str] = []
    if not _value(values, "METRC_INTEGRATOR_API_KEY"):
        missing.append("METRC_INTEGRATOR_API_KEY")
    if not (_value(values, "METRC_MA_SANDBOX_USER_API_KEY") or _value(values, "METRC_USER_API_KEY")):
        missing.append("METRC_MA_SANDBOX_USER_API_KEY")
    if not BASE_URL:
        missing.append("METRC_MA_SANDBOX_BASE_URL_VERIFICATION")

    credential_error = ""
    credentials = None
    if not missing:
        try:
            credentials = resolve_ma_sandbox_evaluation_credentials(values, require_license=False)
        except MetrcEvaluationCredentialError as exc:
            credential_error = str(exc)

    ready = not missing and not credential_error
    return {
        "ready": ready,
        "status": (
            "ready_for_authenticated_read"
            if ready
            else "credential_conflict"
            if credential_error
            else "credentials_missing"
        ),
        "jurisdiction_code": "MA",
        "environment": ENVIRONMENT,
        "api_base": BASE_URL,
        "missing": missing,
        "credential_error": credential_error,
        "user_key_source": credentials.user_key_source if credentials else "",
        "license_required_for_authentication": False,
        "credentials_echoed": False,
        "write_performed": False,
        "next_gate": (
            "Run --live-read to verify the existing key pair and discover the facilities visible to that user key."
            if ready
            else "Clear conflicting MA sandbox credential aliases before any provider request."
            if credential_error
            else "Configure the existing Massachusetts Metrc sandbox credentials before provider validation."
        ),
    }


def live_read(environ: dict[str, str] | None = None, *, timeout_seconds: int = 15) -> dict[str, Any]:
    values = environ if environ is not None else os.environ
    report = readiness(values)
    if not report["ready"]:
        return report
    try:
        credentials = resolve_ma_sandbox_evaluation_credentials(values, require_license=False)
    except MetrcEvaluationCredentialError as exc:
        return report | {
            "ready": False,
            "status": "credential_conflict",
            "credential_error": str(exc),
            "network_request_sent": False,
        }
    try:
        response = requests.get(
            f"{BASE_URL}/facilities/v2/",
            auth=(credentials.integrator_api_key, credentials.user_api_key),
            headers={"Accept": "application/json"},
            timeout=max(1, min(int(timeout_seconds), 60)),
        )
    except requests.RequestException as exc:
        return report | {
            "ready": False,
            "status": "authenticated_read_failed",
            "network_request_sent": True,
            "message": f"Metrc facilities read failed: {type(exc).__name__}.",
        }
    if response.status_code in {401, 403}:
        return report | {
            "ready": False,
            "status": "credentials_rejected",
            "network_request_sent": True,
            "http_status": response.status_code,
        }
    if not response.ok:
        return report | {
            "ready": False,
            "status": "provider_read_error",
            "network_request_sent": True,
            "http_status": response.status_code,
        }
    try:
        payload = response.json()
    except ValueError:
        payload = None
    rows = payload.get("Data") if isinstance(payload, dict) else payload
    facilities = rows if isinstance(rows, list) else []
    licenses = sorted({token for token in (_facility_license_number(row) for row in facilities) if token})
    if not licenses:
        return report | {
            "ready": False,
            "status": "facilities_missing",
            "network_request_sent": True,
            "http_status": response.status_code,
            "facility_count": 0,
            "write_performed": False,
            "next_gate": "The authenticated key pair returned no verifiable facility/license records.",
        }
    return report | {
        "ready": True,
        "status": "authenticated_read_verified",
        "network_request_sent": True,
        "http_status": response.status_code,
        "facility_count": len(facilities),
        "license_count": len(licenses),
        "write_performed": False,
        "next_gate": (
            "Authentication is verified. Select the exact facility per workbook operation from this Facilities response; "
            "do not force one process-global license onto every evaluation task."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-read", action="store_true", help="Perform one read-only authenticated Facilities request.")
    parser.add_argument("--timeout", type=int, default=15, help="Live-read timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = live_read(timeout_seconds=args.timeout) if args.live_read else readiness()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") in {"credentials_missing", "credential_conflict"}:
        return 2
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    sys.exit(main())
