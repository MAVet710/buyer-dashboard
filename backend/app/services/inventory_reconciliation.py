from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, InventoryTransaction, Product


_MASS_FACTORS_TO_GRAMS = {
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "oz": 28.349523125,
    "ounce": 28.349523125,
    "ounces": 28.349523125,
    "lb": 453.59237,
    "lbs": 453.59237,
    "pound": 453.59237,
    "pounds": 453.59237,
}
_COUNT_UNITS = {"ea", "each", "unit", "units", "count", "ct"}


class InventoryMetrcReconciliationService:
    """Compare DoobieLogic physical package balances to read-only Metrc packages.

    This service never mutates either system. Local quantities come from the
    append-only inventory transaction ledger, not availability after production
    or wholesale reservations. That keeps operational commitments from being
    misclassified as regulatory discrepancies.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def reconcile(
        self,
        organization_id: str,
        facility_id: str,
        *,
        jurisdiction_code: str,
        license_number: str,
        environment: str,
        metrc_records: list[dict[str, Any]],
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        local_rows = self._local_rows(organization_id, facility_id)
        local_by_package: dict[str, list[dict[str, Any]]] = {}
        untracked_local = 0
        for row in local_rows:
            package_key = _package_key(row.get("package_id"))
            if not package_key:
                untracked_local += 1
                continue
            local_by_package.setdefault(package_key, []).append(row)

        metrc_by_package: dict[str, list[dict[str, Any]]] = {}
        ignored_metrc = 0
        for record in metrc_records:
            package_id = _metrc_package_id(record)
            package_key = _package_key(package_id)
            if not package_key:
                ignored_metrc += 1
                continue
            metrc_by_package.setdefault(package_key, []).append(record)

        discrepancies: list[dict[str, Any]] = []
        matched = 0

        for package_key in sorted(set(local_by_package) | set(metrc_by_package)):
            local_matches = local_by_package.get(package_key, [])
            metrc_matches = metrc_by_package.get(package_key, [])
            display_package = (
                (local_matches[0].get("package_id") if local_matches else "")
                or (_metrc_package_id(metrc_matches[0]) if metrc_matches else "")
                or package_key
            )

            if len(local_matches) > 1:
                discrepancies.append(_discrepancy(
                    code="duplicate_local_package",
                    severity="high",
                    package_id=display_package,
                    local=local_matches[0],
                    metrc=metrc_matches[0] if metrc_matches else None,
                    message=f"{len(local_matches)} DoobieLogic lots use the same traceability package identifier.",
                ))
                continue
            if len(metrc_matches) > 1:
                discrepancies.append(_discrepancy(
                    code="duplicate_metrc_package",
                    severity="high",
                    package_id=display_package,
                    local=local_matches[0] if local_matches else None,
                    metrc=metrc_matches[0],
                    message=f"{len(metrc_matches)} Metrc records resolved to the same package identifier.",
                ))
                continue

            local = local_matches[0] if local_matches else None
            metrc = metrc_matches[0] if metrc_matches else None
            if local is None and metrc is not None:
                metrc_qty = _number(metrc.get("quantity"))
                discrepancies.append(_discrepancy(
                    code="missing_in_doobielogic",
                    severity="high" if metrc_qty is None or metrc_qty > 0 else "medium",
                    package_id=display_package,
                    local=None,
                    metrc=metrc,
                    message="Metrc shows an active package that is not represented in this DoobieLogic facility ledger.",
                ))
                continue
            if local is not None and metrc is None:
                if float(local.get("quantity") or 0.0) <= 1e-9:
                    continue
                discrepancies.append(_discrepancy(
                    code="missing_in_metrc",
                    severity="high",
                    package_id=display_package,
                    local=local,
                    metrc=None,
                    message="DoobieLogic has physical package balance, but the package was not returned by the active Metrc package read.",
                ))
                continue
            if local is None or metrc is None:
                continue

            package_discrepancies = self._compare_pair(display_package, local, metrc)
            if package_discrepancies:
                discrepancies.extend(package_discrepancies)
            else:
                matched += 1

        counts = {"high": 0, "medium": 0, "info": 0}
        code_counts: dict[str, int] = {}
        for row in discrepancies:
            severity = str(row.get("severity") or "info")
            counts[severity] = counts.get(severity, 0) + 1
            code = str(row.get("code") or "unknown")
            code_counts[code] = code_counts.get(code, 0) + 1

        return {
            "provider": "metrc",
            "jurisdiction_code": jurisdiction_code,
            "license_number": license_number,
            "environment": environment,
            "read_only": True,
            "compared_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
            "summary": {
                "status": "clean" if not discrepancies else "attention",
                "local_tracked_lot_count": sum(len(rows) for rows in local_by_package.values()),
                "metrc_package_count": sum(len(rows) for rows in metrc_by_package.values()),
                "matched_package_count": matched,
                "discrepancy_count": len(discrepancies),
                "high_count": counts.get("high", 0),
                "medium_count": counts.get("medium", 0),
                "info_count": counts.get("info", 0),
                "untracked_local_lot_count": untracked_local,
                "ignored_metrc_record_count": ignored_metrc,
                "by_code": code_counts,
            },
            "discrepancies": discrepancies,
        }

    def _local_rows(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        balance = (
            select(
                InventoryTransaction.lot_id.label("lot_id"),
                func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
            )
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
            )
            .group_by(InventoryTransaction.lot_id)
            .subquery()
        )
        statement = (
            select(InventoryLot, Product, func.coalesce(balance.c.balance, 0.0))
            .join(Product, Product.id == InventoryLot.product_id)
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                Product.organization_id == organization_id,
            )
        )
        with Session(self.engine) as session:
            rows = session.execute(statement).all()

        output: list[dict[str, Any]] = []
        for lot, product, quantity in rows:
            metadata = _notes(lot.notes)
            output.append({
                "lot_id": lot.id,
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "package_id": str(lot.compliance_package_id or "").strip(),
                "lot_code": str(lot.lot_code or "").strip(),
                "quantity": float(quantity or 0.0),
                "unit": str(product.base_unit or "").strip(),
                "location": str(lot.location_code or "").strip(),
                "status": str(lot.status or "").strip(),
                "lab_state": str(metadata.get("lab_testing_state") or "").strip(),
            })
        return output

    @staticmethod
    def _compare_pair(package_id: str, local: dict[str, Any], metrc: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        local_qty = _number(local.get("quantity"))
        metrc_qty = _number(metrc.get("quantity"))
        local_unit = str(local.get("unit") or "").strip()
        metrc_unit = str(metrc.get("unit_of_measure") or _source_value(metrc, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure") or "").strip()
        comparison = _comparable_quantities(local_qty, local_unit, metrc_qty, metrc_unit)
        if comparison[0] == "incompatible":
            output.append(_discrepancy(
                code="unit_mismatch",
                severity="medium",
                package_id=package_id,
                local=local,
                metrc=metrc,
                message=f"Unit mismatch prevents a safe quantity comparison ({local_unit or 'unknown'} vs {metrc_unit or 'unknown'}).",
            ))
        elif comparison[0] == "comparable" and not math.isclose(comparison[1], comparison[2], rel_tol=1e-6, abs_tol=0.001):
            output.append(_discrepancy(
                code="quantity_mismatch",
                severity="high",
                package_id=package_id,
                local=local,
                metrc=metrc,
                message="Physical DoobieLogic ledger quantity does not match the active Metrc package quantity.",
            ))

        local_location = _normalized_text(local.get("location"))
        metrc_location = _normalized_text(_metrc_location(metrc))
        if local_location and metrc_location and local_location != metrc_location:
            output.append(_discrepancy(
                code="location_mismatch",
                severity="medium",
                package_id=package_id,
                local=local,
                metrc=metrc,
                message="DoobieLogic and Metrc report different package locations.",
            ))

        local_lab = _lab_state(local.get("lab_state"))
        metrc_lab = _lab_state(metrc.get("status") or _source_value(metrc, "LabTestingState", "LabTestResultStatus"))
        if local_lab and metrc_lab and local_lab != metrc_lab:
            output.append(_discrepancy(
                code="lab_state_mismatch",
                severity="medium",
                package_id=package_id,
                local=local,
                metrc=metrc,
                message="DoobieLogic and Metrc report different lab-testing states for the package.",
            ))
        return output


def _discrepancy(
    *,
    code: str,
    severity: str,
    package_id: str,
    local: dict[str, Any] | None,
    metrc: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "package_id": package_id,
        "local_lot_id": str((local or {}).get("lot_id") or ""),
        "product_id": str((local or {}).get("product_id") or ""),
        "product_name": str((local or {}).get("product_name") or (metrc or {}).get("name") or ""),
        "local_quantity": (local or {}).get("quantity"),
        "metrc_quantity": (metrc or {}).get("quantity"),
        "local_unit": str((local or {}).get("unit") or ""),
        "metrc_unit": str((metrc or {}).get("unit_of_measure") or _source_value(metrc or {}, "UnitOfMeasureName", "UnitOfMeasureAbbreviation") or ""),
        "local_location": str((local or {}).get("location") or ""),
        "metrc_location": _metrc_location(metrc or {}),
        "local_lab_state": str((local or {}).get("lab_state") or ""),
        "metrc_lab_state": str((metrc or {}).get("status") or _source_value(metrc or {}, "LabTestingState", "LabTestResultStatus") or ""),
        "message": message,
    }


def _notes(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _package_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())


def _metrc_package_id(record: dict[str, Any]) -> str:
    return str(record.get("label") or _source_value(record, "Label", "PackageLabel", "PackageTag") or record.get("provider_id") or "").strip()


def _source_value(record: dict[str, Any], *keys: str) -> Any:
    source = record.get("source")
    if not isinstance(source, dict):
        source = {}
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _metrc_location(record: dict[str, Any]) -> str:
    value = _source_value(record, "LocationName", "Location", "CurrentLocationName")
    if isinstance(value, dict):
        value = value.get("Name") or value.get("name") or ""
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unit(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").strip().casefold())


def _comparable_quantities(
    local_qty: float | None,
    local_unit: str,
    metrc_qty: float | None,
    metrc_unit: str,
) -> tuple[str, float, float]:
    if local_qty is None or metrc_qty is None:
        return ("unknown", 0.0, 0.0)
    local_token = _unit(local_unit)
    metrc_token = _unit(metrc_unit)
    if local_token in _MASS_FACTORS_TO_GRAMS and metrc_token in _MASS_FACTORS_TO_GRAMS:
        return (
            "comparable",
            local_qty * _MASS_FACTORS_TO_GRAMS[local_token],
            metrc_qty * _MASS_FACTORS_TO_GRAMS[metrc_token],
        )
    if local_token in _COUNT_UNITS and metrc_token in _COUNT_UNITS:
        return ("comparable", local_qty, metrc_qty)
    if local_token and local_token == metrc_token:
        return ("comparable", local_qty, metrc_qty)
    return ("incompatible", local_qty, metrc_qty)


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _lab_state(value: Any) -> str:
    token = re.sub(r"[^a-z]", "", str(value or "").casefold())
    if not token:
        return ""
    if token in {"testpassed", "passed", "released", "completepassed"}:
        return "passed"
    if token in {"testfailed", "failed", "completefailed"}:
        return "failed"
    if token in {"testing", "inprocess", "submittedforlabtesting", "testingscheduled"}:
        return "testing"
    if token in {"nottested", "notrequired", "notestrequired"}:
        return "not_tested"
    return token
