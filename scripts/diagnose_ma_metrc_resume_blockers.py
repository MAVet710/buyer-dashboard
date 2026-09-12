#!/usr/bin/env python3
"""Read-only diagnostics for resuming the MA Metrc proficiency evaluation.

This script deliberately performs GET requests only. It is intended to answer the
four outstanding resume questions without consuming tags, plants, packages, or
other sandbox resources:

* whether any accessible facility advertises task-17 immature-package capability;
* whether accessible facilities already contain active package candidates for sales;
* whether lab facilities expose lab-sample package candidates and current test types;
* whether sales reference data is readable for the same facility scope.

It never prints or writes API keys. The detailed output may contain sandbox license,
package, and provider identifiers and therefore belongs in short-lived/private
artifacts only. The redacted summary contains counts and capability totals only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

from modules.regulatory.registry import resolve_metrc_base_url


MAX_PAGE_SIZE = 20
MAX_CAPTURED_CANDIDATES = 10
TIMEOUT_SECONDS = 30


class ResumeDiagnosticError(RuntimeError):
    pass


def _secret(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ResumeDiagnosticError(f"Missing required environment variable: {name}")
    return value


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("Data")
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
    return []


def _meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("Meta")
    return dict(value) if isinstance(value, dict) else {}


def _license_number(facility: dict[str, Any]) -> str:
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        value = str(facility.get(key) or "").strip()
        if value:
            return value
    license_payload = facility.get("License") or facility.get("license")
    if isinstance(license_payload, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            value = str(license_payload.get(key) or "").strip()
            if value:
                return value
    return ""


def _facility_type(facility: dict[str, Any]) -> dict[str, Any]:
    value = facility.get("FacilityType") or facility.get("facilityType")
    return dict(value) if isinstance(value, dict) else {}


def _facility_alias(license_number: str) -> str:
    digest = hashlib.sha256(license_number.encode("utf-8")).hexdigest()[:10]
    return f"facility-{digest}"


def _response_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ResumeDiagnosticError(
            f"Metrc returned non-JSON content for a read-only request (HTTP {response.status_code})."
        ) from exc


def _get(
    *,
    base_url: str,
    path: str,
    auth: tuple[str, str],
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        auth=auth,
        params=params or {},
        timeout=TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )
    payload = _response_json(response) if response.content else None
    return int(response.status_code), payload


def _paged_get(
    *,
    base_url: str,
    path: str,
    auth: tuple[str, str],
    license_number: str,
) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    statuses: list[int] = []
    page = 1
    provider_total_pages = 1

    while page <= provider_total_pages:
        status, payload = _get(
            base_url=base_url,
            path=path,
            auth=auth,
            params={
                "licenseNumber": license_number,
                "pageNumber": page,
                "pageSize": MAX_PAGE_SIZE,
            },
        )
        statuses.append(status)
        if status != 200:
            return {
                "ok": False,
                "http_status": status,
                "statuses": statuses,
                "record_count": len(all_rows),
                "records": all_rows,
            }

        page_rows = _rows(payload)
        all_rows.extend(page_rows)
        meta = _meta(payload)
        try:
            reported = int(meta.get("TotalPages") or meta.get("totalPages") or 1)
        except (TypeError, ValueError):
            reported = 1
        provider_total_pages = max(1, reported)
        page += 1

    return {
        "ok": True,
        "http_status": 200,
        "statuses": statuses,
        "record_count": len(all_rows),
        "records": all_rows,
        "page_count": len(statuses),
        "provider_total_pages": provider_total_pages,
    }


def _compact_package(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    location = row.get("Location") if isinstance(row.get("Location"), dict) else {}
    return {
        "id": row.get("Id") or row.get("id"),
        "label": row.get("Label") or row.get("label"),
        "item_name": item.get("Name") or item.get("name") or row.get("ItemName"),
        "quantity": row.get("Quantity") or row.get("quantity"),
        "unit_of_measure": (
            row.get("UnitOfMeasureName")
            or row.get("UnitOfMeasure")
            or row.get("UnitOfWeight")
        ),
        "lab_testing_state": row.get("LabTestingState") or row.get("labTestingState"),
        "is_finished": row.get("IsFinished") if "IsFinished" in row else row.get("isFinished"),
        "is_on_hold": row.get("IsOnHold") if "IsOnHold" in row else row.get("isOnHold"),
        "location": location.get("Name") or location.get("name") or row.get("LocationName"),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _compact_lab_type(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "name": row.get("Name") or row.get("name"),
        "category": row.get("Category") or row.get("category"),
        "unit": row.get("UnitOfMeasureName") or row.get("Unit") or row.get("unit"),
    }


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only MA Metrc resume diagnostics.")
    parser.add_argument("--output", default="artifacts/metrc-resume/full.local.json")
    parser.add_argument("--summary-output", default="artifacts/metrc-resume/summary.json")
    args = parser.parse_args()

    integrator_key = _secret("METRC_INTEGRATOR_API_KEY")
    user_key = str(
        os.environ.get("METRC_MA_SANDBOX_USER_API_KEY")
        or os.environ.get("METRC_USER_API_KEY")
        or ""
    ).strip()
    if not user_key:
        raise ResumeDiagnosticError("Missing MA sandbox user API key.")
    if integrator_key == user_key:
        raise ResumeDiagnosticError("Integrator and user API keys must be distinct credentials.")

    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if not base_url or state != "MA" or "sandbox" not in base_url.casefold():
        raise ResumeDiagnosticError("Refusing diagnostics because MA sandbox routing was not verified.")

    auth = (integrator_key, user_key)
    facilities_status, facilities_payload = _get(
        base_url=base_url,
        path="facilities/v2/",
        auth=auth,
    )
    if facilities_status != 200:
        raise ResumeDiagnosticError(
            f"Facilities authentication gate failed with HTTP {facilities_status}; no scoped diagnostics were sent."
        )

    facilities = _rows(facilities_payload)
    if not facilities and isinstance(facilities_payload, list):
        facilities = [dict(row) for row in facilities_payload if isinstance(row, dict)]
    if not facilities:
        raise ResumeDiagnosticError("Facilities gate returned no usable facility records.")

    detailed_facilities: list[dict[str, Any]] = []
    safe_facilities: list[dict[str, Any]] = []
    capability_true = capability_false = capability_missing = 0
    active_package_total = lab_sample_total = 0
    facilities_with_active_packages = facilities_with_lab_samples = 0
    facilities_with_lab_types = facilities_with_sales_reference = 0

    for facility in facilities:
        license_number = _license_number(facility)
        if not license_number:
            continue
        facility_type = _facility_type(facility)
        capability = facility_type.get("CanCreateImmaturePlantPackagesFromPlants")
        if capability is True:
            capability_true += 1
        elif capability is False:
            capability_false += 1
        else:
            capability_missing += 1

        active = _paged_get(
            base_url=base_url,
            path="packages/v2/active",
            auth=auth,
            license_number=license_number,
        )
        labsamples = _paged_get(
            base_url=base_url,
            path="packages/v2/labsamples",
            auth=auth,
            license_number=license_number,
        )
        lab_types = _paged_get(
            base_url=base_url,
            path="labtests/v2/types",
            auth=auth,
            license_number=license_number,
        )
        sales_types = _paged_get(
            base_url=base_url,
            path="sales/v2/customertypes",
            auth=auth,
            license_number=license_number,
        )

        active_count = int(active.get("record_count") or 0)
        labsample_count = int(labsamples.get("record_count") or 0)
        lab_type_count = int(lab_types.get("record_count") or 0)
        sales_type_count = int(sales_types.get("record_count") or 0)

        active_package_total += active_count
        lab_sample_total += labsample_count
        facilities_with_active_packages += int(active_count > 0)
        facilities_with_lab_samples += int(labsample_count > 0)
        facilities_with_lab_types += int(lab_type_count > 0)
        facilities_with_sales_reference += int(sales_type_count > 0)

        detailed_facilities.append(
            {
                "license_number": license_number,
                "name": facility.get("Name") or facility.get("DisplayName") or "",
                "facility_type": facility_type,
                "task17_capability": capability,
                "active_packages": {
                    "ok": active.get("ok"),
                    "http_status": active.get("http_status"),
                    "record_count": active_count,
                    "candidates": [
                        _compact_package(row)
                        for row in list(active.get("records") or [])[:MAX_CAPTURED_CANDIDATES]
                    ],
                },
                "lab_sample_packages": {
                    "ok": labsamples.get("ok"),
                    "http_status": labsamples.get("http_status"),
                    "record_count": labsample_count,
                    "candidates": [
                        _compact_package(row)
                        for row in list(labsamples.get("records") or [])[:MAX_CAPTURED_CANDIDATES]
                    ],
                },
                "lab_test_types": {
                    "ok": lab_types.get("ok"),
                    "http_status": lab_types.get("http_status"),
                    "record_count": lab_type_count,
                    "types": [
                        _compact_lab_type(row)
                        for row in list(lab_types.get("records") or [])[:MAX_CAPTURED_CANDIDATES]
                    ],
                },
                "sales_customer_types": {
                    "ok": sales_types.get("ok"),
                    "http_status": sales_types.get("http_status"),
                    "record_count": sales_type_count,
                },
            }
        )
        safe_facilities.append(
            {
                "facility": _facility_alias(license_number),
                "task17_capability": capability,
                "active_package_count": active_count,
                "lab_sample_package_count": labsample_count,
                "lab_test_type_count": lab_type_count,
                "sales_customer_type_count": sales_type_count,
                "active_packages_http": active.get("http_status"),
                "lab_samples_http": labsamples.get("http_status"),
                "lab_types_http": lab_types.get("http_status"),
                "sales_types_http": sales_types.get("http_status"),
            }
        )

    full = {
        "schema_version": 1,
        "state": "MA",
        "environment": "sandbox",
        "read_only": True,
        "mutations_sent": 0,
        "facility_count": len(detailed_facilities),
        "task17_capability": {
            "true": capability_true,
            "false": capability_false,
            "missing": capability_missing,
        },
        "active_package_total": active_package_total,
        "lab_sample_package_total": lab_sample_total,
        "facilities_with_active_packages": facilities_with_active_packages,
        "facilities_with_lab_samples": facilities_with_lab_samples,
        "facilities_with_lab_types": facilities_with_lab_types,
        "facilities_with_sales_reference": facilities_with_sales_reference,
        "facilities": detailed_facilities,
        "secrets_included": False,
    }
    summary = {
        "schema_version": 1,
        "state": "MA",
        "environment": "sandbox",
        "read_only": True,
        "mutations_sent": 0,
        "facility_count": len(safe_facilities),
        "task17_capability": full["task17_capability"],
        "active_package_total": active_package_total,
        "lab_sample_package_total": lab_sample_total,
        "facilities_with_active_packages": facilities_with_active_packages,
        "facilities_with_lab_samples": facilities_with_lab_samples,
        "facilities_with_lab_types": facilities_with_lab_types,
        "facilities_with_sales_reference": facilities_with_sales_reference,
        "facilities": safe_facilities,
        "secrets_included": False,
    }

    _write(args.output, full)
    _write(args.summary_output, summary)
    print(
        "MA Metrc resume diagnostics complete: "
        f"{len(safe_facilities)} facilities, "
        f"{active_package_total} active package record(s), "
        f"{lab_sample_total} lab-sample package record(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
