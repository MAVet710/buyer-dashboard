"""Fail-closed finalization for the Massachusetts Metrc evaluation workbook.

This module does not claim regulator approval. It converts locally captured runner
outputs into an auditable 47-task readiness report. A task is ready for Metrc
review only when the canonical evaluator recorded HTTP 200, stage=complete, and
passed=true for the matching workbook operation.

Credentials are intentionally excluded. Vendor/User API keys belong only in the
local submission workbook and must never be copied into evidence JSON or reports.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable

from services.metrc_evaluation_submission import (
    COMPANY_INFORMATION_OPTIONAL_FIELDS,
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    SECRET_WORKBOOK_FIELDS,
)
from services.metrc_evaluation_workbook import MA_WORKBOOK_TASKS, ma_workbook_plan


_GENERATED_REPORT_NAMES = {
    "final_report.json",
    "final-report.json",
    "workbook_plan.json",
    "workbook-plan.json",
}
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "vendor_key",
    "user_key",
    "integrator_key",
    "authorization",
    "password",
    "secret",
    "token",
)
_TASK_HINT_RE = re.compile(r"^(?:task[-_ ]*)?(\d{1,2})(?:[-_ .]|$)", re.IGNORECASE)


class MetrcEvaluationFinalizationError(RuntimeError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text(value).casefold()).strip("_")


def _secret_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = _normalize_key(key)
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(part in key_text for part in _SECRET_KEY_PARTS):
                findings.append(path)
            findings.extend(_secret_key_paths(nested, prefix=path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            findings.extend(_secret_key_paths(nested, prefix=path))
    return findings


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetrcEvaluationFinalizationError(f"Could not read evaluation evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetrcEvaluationFinalizationError(f"Evaluation evidence must be a JSON object: {path}")
    secret_paths = _secret_key_paths(payload)
    if secret_paths:
        joined = ", ".join(secret_paths[:5])
        raise MetrcEvaluationFinalizationError(
            f"Evidence file contains credential-like fields and is not safe to finalize: {path} ({joined})"
        )
    return payload


def discover_evidence_files(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        raise MetrcEvaluationFinalizationError(f"Evidence directory does not exist: {root}")
    paths = [
        path
        for path in root.rglob("*.json")
        if path.is_file()
        and path.name.casefold() not in _GENERATED_REPORT_NAMES
        and not path.name.casefold().endswith((".local.json", ".manifest.json"))
    ]
    return sorted(paths, key=lambda path: path.as_posix().casefold())


def _task_hint(path: Path, payload: dict[str, Any]) -> int | None:
    raw = payload.get("task_number")
    if raw not in (None, ""):
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None
        return number if 1 <= number <= len(MA_WORKBOOK_TASKS) else None
    match = _TASK_HINT_RE.match(path.stem)
    if match:
        number = int(match.group(1))
        return number if 1 <= number <= len(MA_WORKBOOK_TASKS) else None
    return None


def _load_evidence(directory: str | Path) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _read_json_object(path)) for path in discover_evidence_files(directory)]


def _complete_pass(payload: dict[str, Any]) -> bool:
    try:
        http_status = int(payload.get("http_status") or 0)
    except (TypeError, ValueError):
        http_status = 0
    return (
        payload.get("passed") is True
        and _text(payload.get("stage")).casefold() == "complete"
        and http_status == 200
        and _text(payload.get("state")).upper() == "MA"
        and _text(payload.get("environment")).casefold() == "sandbox"
    )


def _evidence_rank(record: tuple[Path, dict[str, Any]]) -> tuple[int, int, str]:
    path, payload = record
    try:
        modified = path.stat().st_mtime_ns
    except OSError:
        modified = 0
    return (1 if _complete_pass(payload) else 0, modified, path.as_posix().casefold())


def _assign_evidence(
    records: Iterable[tuple[Path, dict[str, Any]]],
) -> tuple[dict[int, tuple[Path, dict[str, Any]]], list[dict[str, Any]]]:
    tasks_by_number = {task.number: task for task in MA_WORKBOOK_TASKS}
    hinted: dict[int, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    unhinted: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    extras: list[dict[str, Any]] = []

    for path, payload in records:
        operation = _text(payload.get("operation_type")).casefold()
        hint = _task_hint(path, payload)
        if hint is not None:
            task = tasks_by_number[hint]
            if operation != task.operation_type.casefold():
                extras.append({
                    "file": str(path),
                    "reason": "task_number_operation_mismatch",
                    "task_number": hint,
                    "operation_type": operation,
                    "expected_operation_type": task.operation_type,
                })
                continue
            hinted[hint].append((path, payload))
        else:
            unhinted[operation].append((path, payload))

    assigned: dict[int, tuple[Path, dict[str, Any]]] = {}
    for task_number, candidates in hinted.items():
        ranked = sorted(candidates, key=_evidence_rank, reverse=True)
        assigned[task_number] = ranked[0]
        for path, payload in ranked[1:]:
            extras.append({
                "file": str(path),
                "reason": "superseded_task_evidence",
                "task_number": task_number,
                "operation_type": _text(payload.get("operation_type")).casefold(),
            })

    tasks_for_operation: dict[str, list[int]] = defaultdict(list)
    for task in MA_WORKBOOK_TASKS:
        if task.number not in assigned:
            tasks_for_operation[task.operation_type.casefold()].append(task.number)

    for operation, candidates in unhinted.items():
        ranked = sorted(candidates, key=_evidence_rank, reverse=True)
        task_numbers = tasks_for_operation.get(operation, [])
        for task_number, record in zip(task_numbers, ranked):
            assigned[task_number] = record
        for path, _payload in ranked[len(task_numbers):]:
            extras.append({
                "file": str(path),
                "reason": "superseded_or_extra_evidence",
                "operation_type": operation,
            })
    return assigned, extras


def _validate_task_evidence(task, path: Path, payload: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    operation = _text(payload.get("operation_type")).casefold()
    if operation != task.operation_type.casefold():
        reasons.append("operation_type_mismatch")
    if _text(payload.get("state")).upper() != "MA":
        reasons.append("state_not_ma")
    if _text(payload.get("environment")).casefold() != "sandbox":
        reasons.append("environment_not_sandbox")
    try:
        http_status = int(payload.get("http_status") or 0)
    except (TypeError, ValueError):
        http_status = 0
    if http_status != 200:
        reasons.append("http_status_not_200")
    if _text(payload.get("stage")).casefold() != "complete":
        reasons.append("stage_not_complete")
    if payload.get("passed") is not True:
        reasons.append("runner_not_passed")
    return ("passed" if not reasons else "failed"), reasons


def sanitize_company_information(value: dict[str, Any] | None) -> tuple[dict[str, str], list[str]]:
    source = value or {}
    if not isinstance(source, dict):
        raise MetrcEvaluationFinalizationError("Company information must be a JSON object.")

    normalized = {_normalize_key(key): _text(raw) for key, raw in source.items()}
    secret_norm = {_normalize_key(field) for field in SECRET_WORKBOOK_FIELDS}
    supplied_secret_fields = [key for key in normalized if key in secret_norm and normalized[key]]
    if supplied_secret_fields:
        raise MetrcEvaluationFinalizationError(
            "Vendor/User keys must not be supplied to the report finalizer. Put them only in environment variables used by the local workbook-preservation step."
        )

    safe: dict[str, str] = {}
    missing: list[str] = []
    for field in (*COMPANY_INFORMATION_REQUIRED_FIELDS, *COMPANY_INFORMATION_OPTIONAL_FIELDS):
        if field in SECRET_WORKBOOK_FIELDS:
            continue
        clean = normalized.get(_normalize_key(field), "")
        if clean:
            safe[field] = clean
        elif field in COMPANY_INFORMATION_REQUIRED_FIELDS:
            missing.append(field)
    return safe, missing


def build_final_report(
    *,
    evidence_directory: str | Path,
    company_information: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = _load_evidence(evidence_directory)
    assigned, extras = _assign_evidence(records)
    safe_company, missing_company = sanitize_company_information(company_information)

    task_rows: list[dict[str, Any]] = []
    passed_count = failed_count = missing_count = 0
    for task in MA_WORKBOOK_TASKS:
        pair = assigned.get(task.number)
        row = asdict(task)
        if pair is None:
            row.update({"status": "missing", "evidence_file": "", "reasons": ["missing_evidence"]})
            missing_count += 1
        else:
            path, payload = pair
            status, reasons = _validate_task_evidence(task, path, payload)
            try:
                http_status = int(payload.get("http_status") or 0)
            except (TypeError, ValueError):
                http_status = 0
            row.update({
                "status": status,
                "evidence_file": str(path),
                "reasons": reasons,
                "http_status": http_status,
                "stage": _text(payload.get("stage")),
                "provider_id": _text(payload.get("provider_id")),
                "correlation_id": _text(payload.get("correlation_id")),
            })
            if status == "passed":
                passed_count += 1
            else:
                failed_count += 1
        task_rows.append(row)

    workbook = ma_workbook_plan()
    evidence_ready = passed_count == len(MA_WORKBOOK_TASKS) and failed_count == 0 and missing_count == 0
    company_ready = not missing_company
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbook": workbook["workbook"],
        "state": "MA",
        "environment": "sandbox",
        "sheet_count": workbook["sheet_count"],
        "applicable_task_count": workbook["applicable_task_count"],
        "pass_rule": workbook["pass_rule"],
        "status": "ready_for_metrc_review" if evidence_ready and company_ready else "not_ready",
        "submission_ready": bool(evidence_ready and company_ready),
        "regulator_approval_claimed": False,
        "regulator_approval_note": (
            "This report verifies DoobieLogic's local evidence package only. Metrc remains the authority that accepts or rejects the official evaluation."
        ),
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "missing": missing_count,
            "total": len(MA_WORKBOOK_TASKS),
            "evidence_files_seen": len(records),
            "extra_or_unmatched_evidence": len(extras),
        },
        "company_information": safe_company,
        "missing_company_information": missing_company,
        "secret_workbook_fields": list(SECRET_WORKBOOK_FIELDS),
        "secret_handling": "Never stored in this report; fill only into the local submission workbook from environment variables.",
        "extra_or_unmatched_evidence": extras,
        "tasks": task_rows,
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# Massachusetts Metrc Evaluation Evidence Report",
        "",
        f"Status: **{report.get('status', 'not_ready')}**",
        "",
        (
            f"Evidence tasks: {summary.get('passed', 0)} passed / "
            f"{summary.get('failed', 0)} failed / {summary.get('missing', 0)} missing "
            f"of {summary.get('total', 0)} applicable tasks."
        ),
        "",
        "> This is a DoobieLogic evidence-readiness report, not a claim that Metrc has approved the evaluation.",
        "",
    ]
    missing_company = report.get("missing_company_information") or []
    if missing_company:
        lines.extend(["## Missing submission information", ""])
        lines.extend(f"- {field}" for field in missing_company)
        lines.append("")

    lines.extend([
        "## Task results",
        "",
        "| # | Sheet | Step | Operation | Status | Evidence |",
        "|---:|---|---|---|---|---|",
    ])
    for row in report.get("tasks") or []:
        evidence = Path(_text(row.get("evidence_file"))).name if row.get("evidence_file") else ""
        lines.append(
            f"| {row.get('number')} | {row.get('sheet')} | {row.get('step')} | "
            f"`{row.get('operation_type')}` | {row.get('status')} | {evidence} |"
        )
    lines.append("")
    extras = report.get("extra_or_unmatched_evidence") or []
    if extras:
        lines.extend(["## Extra or superseded evidence", ""])
        lines.extend(f"- `{item.get('file')}` — {item.get('reason')}" for item in extras)
        lines.append("")
    return "\n".join(lines)
