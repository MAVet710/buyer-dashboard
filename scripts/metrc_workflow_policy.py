#!/usr/bin/env python3
"""Safety policy for manually executing bounded MA Metrc sandbox evaluation work.

This module contains no credentials and performs no network requests. It exists so
GitHub Actions and tests share one authoritative classification of read-only versus
sandbox-write evaluation operations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.metrc_evaluation_lab import LAB_EVALUATION_ACTIONS
from services.metrc_evaluation_lifecycle import LIFECYCLE_EVALUATION_ACTIONS
from services.metrc_evaluation_master_data import MASTER_DATA_EVALUATION_ACTIONS
from services.metrc_evaluation_reads import READ_EVALUATION_ACTIONS
from services.metrc_evaluation_sales import SALES_EVALUATION_ACTIONS
from services.metrc_evaluation_transfers import (
    TRANSFER_READ_EVALUATION_ACTIONS,
    TRANSFER_WRITE_EVALUATION_ACTIONS,
)

WRITE_CONFIRMATION = "I_APPROVE_MA_SANDBOX_WRITE"

READ_ONLY_OPERATIONS = frozenset(
    {
        "workbook_plan",
        "facilities",
        *READ_EVALUATION_ACTIONS,
        *TRANSFER_READ_EVALUATION_ACTIONS,
    }
)

ALL_OPERATIONS = frozenset(
    {
        *READ_ONLY_OPERATIONS,
        *MASTER_DATA_EVALUATION_ACTIONS,
        *LIFECYCLE_EVALUATION_ACTIONS,
        *LAB_EVALUATION_ACTIONS,
        *SALES_EVALUATION_ACTIONS,
        *TRANSFER_WRITE_EVALUATION_ACTIONS,
    }
)

WRITE_OPERATIONS = frozenset(ALL_OPERATIONS - READ_ONLY_OPERATIONS)


def classify_operation(operation: str) -> str:
    selected = str(operation or "").strip()
    if selected not in ALL_OPERATIONS:
        raise ValueError("Selected operation is not a bounded MA Metrc evaluation operation.")
    return "read_only" if selected in READ_ONLY_OPERATIONS else "write"


def authorize_operation(operation: str, *, github_ref: str, confirmation: str = "") -> dict[str, object]:
    selected = str(operation or "").strip()
    classification = classify_operation(selected)
    if classification == "write":
        if str(github_ref or "").strip() != "refs/heads/main":
            raise ValueError("MA Metrc sandbox write operations may only run from refs/heads/main.")
        if str(confirmation or "") != WRITE_CONFIRMATION:
            raise ValueError(f"MA Metrc sandbox write operations require confirmation: {WRITE_CONFIRMATION}")
    return {
        "operation": selected,
        "classification": classification,
        "read_only": classification == "read_only",
        "write_approved": classification == "write",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--github-ref", default="")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--github-env", default="", help="Optional GITHUB_ENV file to receive classification flags.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = authorize_operation(
            args.operation,
            github_ref=args.github_ref,
            confirmation=args.confirmation,
        )
    except ValueError as exc:
        print(json.dumps({"authorized": False, "message": str(exc)}, sort_keys=True))
        return 2

    if args.github_env:
        target = Path(args.github_env)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"METRC_OPERATION_READ_ONLY={'true' if result['read_only'] else 'false'}\n")
            handle.write(f"METRC_OPERATION_CLASSIFICATION={result['classification']}\n")

    # Deliberately do not print the confirmation token or any credential-bearing values.
    print(json.dumps({"authorized": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
