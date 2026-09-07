#!/usr/bin/env python3
"""Validate readiness for DoobieLogic's Massachusetts Metrc sandbox pilot.

The default command performs no network request and never prints credentials.
Use ``--live-read`` only after real sandbox credentials are available to verify
authentication with the read-only Facilities endpoint. This script deliberately
has no write flag: the first provider mutation must flow through the application's
human-approved durable action/traceability path so its audit evidence is kept.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

from modules.regulatory.registry import resolve_metrc_base_url


ENVIRONMENT = "sandbox"
BASE_URL, _STATE_CODE = resolve_metrc_base_url("MA", environment=ENVIRONMENT)
REQUIRED_ENV = (
    "METRC_INTEGRATOR_API_KEY",
    "METRC_MA_SANDBOX_USER_API_KEY",
    "METRC_MA_SANDBOX_LICENSE_NUMBER",
)


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
    missing = [name for name in REQUIRED_ENV if not str(values.get(name) or "").strip()]
    if not BASE_URL:
        missing = [*missing, "METRC_MA_SANDBOX_BASE_URL_VERIFICATION"]
    license_number = str(values.get("METRC_MA_SANDBOX_LICENSE_NUMBER") or "").strip()
    return {
        "ready": not missing,
        "status": "ready_for_authenticated_read" if not missing else "credentials_missing",
        "jurisdiction_code": "MA",
        "environment": ENVIRONMENT,
        "api_base": BASE_URL,
        "missing": missing,
        "license_configured": bool(license_number),
        "license_mapping_verified": False,
        "credentials_echoed": False,
        "write_performed": False,
        "next_gate": (
            "Run --live-read to verify authentication and exact facility/license mapping."
            if not missing
            else "Obtain Massachusetts Metrc sandbox credentials before provider validation."
        ),
    }


def live_read(environ: dict[str, str] | None = None, *, timeout_seconds: int = 15) -> dict[str, Any]:
    values = environ if environ is not None else os.environ
    report = readiness(values)
    if not report["ready"]:
        return report
    try:
        response = requests.get(
            f"{BASE_URL}/facilities/v2/",
            auth=(
                str(values["METRC_INTEGRATOR_API_KEY"]).strip(),
                str(values["METRC_MA_SANDBOX_USER_API_KEY"]).strip(),
            ),
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
    facility_count = len(facilities)
    configured_license = str(values["METRC_MA_SANDBOX_LICENSE_NUMBER"]).strip().casefold()
    matched_facility_count = sum(
        1
        for facility in facilities
        if _facility_license_number(facility).casefold() == configured_license
    )
    if matched_facility_count < 1:
        return report | {
            "ready": False,
            "status": "license_mapping_not_found",
            "network_request_sent": True,
            "http_status": response.status_code,
            "facility_count": facility_count,
            "matched_facility_count": 0,
            "license_mapping_verified": False,
            "write_performed": False,
            "next_gate": "Set METRC_MA_SANDBOX_LICENSE_NUMBER to a license returned by the authenticated Facilities response before loading live Facility Setup data.",
        }
    return report | {
        "ready": True,
        "status": "authenticated_read_verified",
        "network_request_sent": True,
        "http_status": response.status_code,
        "facility_count": facility_count,
        "matched_facility_count": matched_facility_count,
        "license_mapping_verified": True,
        "write_performed": False,
        "next_gate": "Facility/license mapping is verified. Use DoobieLogic's bounded MA evaluation workflow for the next workbook operation; do not bypass the application action ledger for regulated mutations.",
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
    if report.get("status") == "credentials_missing":
        return 2
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    sys.exit(main())
