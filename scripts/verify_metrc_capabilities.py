#!/usr/bin/env python3
"""Audit official Metrc documentation against DoobieLogic's capability registry.

This command is intentionally unauthenticated and read-only. It requests each
jurisdiction's public Metrc documentation page, reduces the HTML to searchable
text, and reports whether the representative v2 endpoint evidence currently
recorded in the registry is still visible.

It does not update the registry automatically. Human review is required before
capability evidence is added or removed because documentation availability is
not the same thing as regulatory authorization.
"""

from __future__ import annotations

import argparse
from html import unescape
import json
import re
import sys
from typing import Any

import requests

from modules.regulatory import DOCUMENTED_V2_CAPABILITY_ENDPOINTS, get_jurisdiction, list_jurisdictions


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def html_to_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", str(value or ""))
    return _SPACE_RE.sub(" ", unescape(without_tags)).strip()


def inspect_documentation(jurisdiction: str, *, timeout_seconds: int = 12) -> dict[str, Any]:
    profile = get_jurisdiction(jurisdiction)
    if profile is None:
        return {
            "ok": False,
            "jurisdiction": str(jurisdiction or "").strip().upper(),
            "status": "unknown_jurisdiction",
            "message": "Jurisdiction is not present in the verified Metrc market registry.",
        }

    try:
        response = requests.get(
            profile.documentation_url,
            timeout=timeout_seconds,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "DoobieLogic-Metrc-Capability-Audit/1.0",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "ok": False,
            "jurisdiction": profile.code,
            "name": profile.name,
            "documentation_url": profile.documentation_url,
            "status": "documentation_unavailable",
            "message": f"Public documentation request failed: {type(exc).__name__}.",
        }

    text = html_to_text(response.text)
    endpoint_evidence = {
        capability: {
            "endpoint": endpoint,
            "present": _endpoint_present(text, endpoint),
        }
        for capability, endpoint in DOCUMENTED_V2_CAPABILITY_ENDPOINTS.items()
    }
    facilities_present = _endpoint_present(text, "GET /facilities/v2/")
    present_count = sum(1 for row in endpoint_evidence.values() if row["present"])
    missing = [capability for capability, row in endpoint_evidence.items() if not row["present"]]

    return {
        "ok": facilities_present,
        "jurisdiction": profile.code,
        "name": profile.name,
        "documentation_url": profile.documentation_url,
        "http_status": int(response.status_code),
        "status": "verified" if facilities_present else "facilities_evidence_missing",
        "facilities_present": facilities_present,
        "documented_capability_count": present_count,
        "expected_capability_count": len(DOCUMENTED_V2_CAPABILITY_ENDPOINTS),
        "missing_capabilities": missing,
        "capabilities": endpoint_evidence,
    }


def _endpoint_present(text: str, endpoint: str) -> bool:
    method, _, path = str(endpoint or "").partition(" ")
    if not method or not path:
        return False
    normalized = text.casefold()
    return method.casefold() in normalized and path.casefold() in normalized


def build_report(*, jurisdiction: str = "", timeout_seconds: int = 12) -> dict[str, Any]:
    if jurisdiction:
        targets = [jurisdiction]
    else:
        targets = [profile.code for profile in list_jurisdictions()]
    rows = [inspect_documentation(code, timeout_seconds=timeout_seconds) for code in targets]
    return {
        "source": "Official public Metrc jurisdiction API documentation",
        "automatic_registry_updates": False,
        "human_review_required": True,
        "jurisdictions": rows,
        "summary": {
            "checked": len(rows),
            "documentation_reachable": sum(1 for row in rows if row.get("http_status") == 200),
            "facilities_evidence_verified": sum(1 for row in rows if row.get("ok") is True),
            "unavailable_or_unverified": sum(1 for row in rows if row.get("ok") is not True),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jurisdiction", default="", help="Optional state/territory code or name.")
    parser.add_argument("--timeout", type=int, default=12, help="Per-document request timeout in seconds.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any requested jurisdiction documentation cannot verify the facilities endpoint.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(jurisdiction=args.jurisdiction, timeout_seconds=max(1, min(args.timeout, 60)))
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and any(row.get("ok") is not True for row in report["jurisdictions"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
