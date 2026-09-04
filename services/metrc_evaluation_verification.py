"""Workbook-level evidence rules layered over safe Metrc read execution."""

from __future__ import annotations

from typing import Any


class MetrcWorkbookVerificationError(RuntimeError):
    pass


def _record_id(record: dict[str, Any]) -> str:
    direct = str(record.get("provider_id") or "").strip()
    if direct:
        return direct
    source = record.get("source")
    if isinstance(source, dict):
        for key in ("Id", "id", "TransferTemplateId", "TemplateId"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def _record_name(record: dict[str, Any]) -> str:
    direct = str(record.get("name") or "").strip()
    if direct:
        return direct
    source = record.get("source")
    if isinstance(source, dict):
        return str(source.get("Name") or source.get("name") or "").strip()
    return ""


def verify_transfer_workbook_read(
    operation_type: str,
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Require actual provider evidence, not merely an HTTP-200 empty list.

    Every transfer workbook row says to *find* an object. A successful empty
    collection is therefore not a proficiency pass. The template-list row is
    stricter: it must prove both templates created in workbook Steps 1a/1b.
    """

    operation = str(operation_type or "").strip().casefold()
    output = dict(evidence)
    if not output.get("passed"):
        return output
    records = [dict(row) for row in (output.get("records") or []) if isinstance(row, dict)]
    if not records:
        output["passed"] = False
        output["stage"] = "verification"
        output["message"] = "Metrc returned HTTP 200 across all pages, but the workbook task requires a verifiable provider record and none was found."
        return output

    if operation == "transfer_template_list":
        expected_ids = {
            str(value).strip()
            for value in (payload.get("expected_provider_ids") or [])
            if str(value).strip()
        }
        expected_names = {
            str(value).strip()
            for value in (payload.get("expected_names") or [])
            if str(value).strip()
        }
        if len(expected_ids) < 2 and len(expected_names) < 2:
            raise MetrcWorkbookVerificationError(
                "transfer_template_list requires expected_provider_ids or expected_names for both templates created in Steps 1a and 1b."
            )
        observed_ids = {_record_id(row) for row in records} - {""}
        observed_names = {_record_name(row) for row in records} - {""}
        ids_ok = bool(expected_ids) and expected_ids.issubset(observed_ids)
        names_ok = bool(expected_names) and expected_names.issubset(observed_names)
        if not (ids_ok or names_ok):
            output["passed"] = False
            output["stage"] = "verification"
            output["message"] = "The complete paginated template list did not contain both evaluation templates."
            output["expected_provider_ids"] = sorted(expected_ids)
            output["expected_names"] = sorted(expected_names)
            output["observed_provider_ids"] = sorted(observed_ids)
            output["observed_names"] = sorted(observed_names)
            return output

    output["record_count"] = len(records)
    return output
