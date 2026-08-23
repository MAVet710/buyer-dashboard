"""Tenant-safe physical inventory audit and reconciliation operations."""

from __future__ import annotations

import json
import math
import re
import hashlib
from urllib.parse import unquote
from collections.abc import Iterable, Mapping

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import (
    AuditEvent,
    Facility,
    InventoryAudit,
    InventoryAuditLine,
    InventoryAuditScan,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    utc_now,
)


class InventoryAuditRepository:
    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def list_audits(
        self,
        organization_id: str,
        facility_id: str,
        operation_type: str | None = None,
    ) -> list[InventoryAudit]:
        with self._session_factory() as session:
            statement = select(InventoryAudit).where(
                InventoryAudit.organization_id == organization_id,
                InventoryAudit.facility_id == facility_id,
            )
            if operation_type:
                statement = statement.where(InventoryAudit.operation_type == operation_type)
            return list(
                session.scalars(
                    statement.order_by(InventoryAudit.started_at.desc(), InventoryAudit.audit_number.desc())
                )
            )

    def list_lines(self, organization_id: str, audit_id: str) -> list[InventoryAuditLine]:
        with self._session_factory() as session:
            audit = self._require_audit(session, organization_id, audit_id)
            return list(
                session.scalars(
                    select(InventoryAuditLine)
                    .where(
                        InventoryAuditLine.organization_id == organization_id,
                        InventoryAuditLine.audit_id == audit.id,
                    )
                    .order_by(InventoryAuditLine.created_at, InventoryAuditLine.id)
                )
            )

    def create_audit(
        self,
        organization_id: str,
        facility_id: str,
        *,
        audit_number: str,
        actor: str,
        scope_label: str = "Full facility",
        notes: str = "",
        lot_ids: Iterable[str] | None = None,
        operation_type: str = "production",
        blind_count: bool = True,
        recount_tolerance: float = 0.0,
    ) -> InventoryAudit:
        clean_number = str(audit_number).strip().upper()
        if not clean_number:
            raise ValueError("Audit number is required.")
        requested_ids = {str(value) for value in lot_ids or [] if str(value)}
        clean_operation_type = str(operation_type).strip().lower()
        if clean_operation_type not in {"retail", "production"}:
            raise ValueError("Audit operation type must be retail or production.")
        tolerance = float(recount_tolerance)
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("Recount tolerance cannot be negative.")
        audit = InventoryAudit(
            organization_id=organization_id,
            facility_id=facility_id,
            audit_number=clean_number,
            operation_type=clean_operation_type,
            blind_count=bool(blind_count),
            recount_tolerance=tolerance,
            scope_label=str(scope_label).strip() or "Full facility",
            notes=str(notes or ""),
            created_by=str(actor),
        )
        with self._session_factory.begin() as session:
            self._require_scope(session, organization_id, facility_id)
            duplicate = session.scalar(
                select(InventoryAudit.id).where(
                    InventoryAudit.organization_id == organization_id,
                    InventoryAudit.audit_number == clean_number,
                )
            )
            if duplicate:
                raise ValueError("That audit name / number already exists in this organization.")
            statement = select(InventoryLot, Product).join(Product, Product.id == InventoryLot.product_id).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            )
            if requested_ids:
                statement = statement.where(InventoryLot.id.in_(requested_ids))
            lots = list(session.execute(statement.order_by(InventoryLot.location_code, InventoryLot.lot_code)))
            if requested_ids and {lot.id for lot, _ in lots} != requested_ids:
                raise ValueError("One or more selected lots were not found in this facility.")
            if not lots:
                raise ValueError("At least one inventory lot is required to start an audit.")
            session.add(audit)
            session.flush()
            for lot, product in lots:
                balance = self._lot_balance(session, lot.id)
                session.add(
                    InventoryAuditLine(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        audit_id=audit.id,
                        lot_id=lot.id,
                        expected_quantity=max(0.0, balance),
                        unit=product.base_unit,
                    )
                )
            self._audit_event(
                session,
                audit,
                "created",
                actor,
                {
                    "audit_number": clean_number,
                    "line_count": len(lots),
                    "scope": audit.scope_label,
                    "operation_type": clean_operation_type,
                    "blind_count": bool(blind_count),
                },
            )
        return audit

    def list_scans(self, organization_id: str, audit_id: str) -> list[InventoryAuditScan]:
        with self._session_factory() as session:
            audit = self._require_audit(session, organization_id, audit_id)
            return list(
                session.scalars(
                    select(InventoryAuditScan)
                    .where(InventoryAuditScan.audit_id == audit.id)
                    .order_by(InventoryAuditScan.scanned_at.desc())
                )
            )

    def import_retail_snapshot(
        self,
        organization_id: str,
        facility_id: str,
        *,
        rows: Iterable[Mapping[str, object]],
        actor: str,
        reference: str,
    ) -> dict[str, int]:
        """Upsert a retail product/lot snapshot and append balance corrections."""

        submitted = list(rows)
        if not submitted:
            raise ValueError("The retail inventory snapshot is empty.")
        stats = {"rows": 0, "products_created": 0, "lots_created": 0, "adjustments": 0}
        with self._session_factory.begin() as session:
            self._require_scope(session, organization_id, facility_id)
            products = {
                product.sku: product
                for product in session.scalars(select(Product).where(Product.organization_id == organization_id))
            }
            lots = {
                lot.lot_code: lot
                for lot in session.scalars(
                    select(InventoryLot).where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                    )
                )
            }
            for row in submitted:
                name = str(row.get("product_name") or "").strip()
                if not name:
                    continue
                quantity = _numeric_value(row.get("quantity"))
                if not math.isfinite(quantity) or quantity < 0:
                    raise ValueError(f"Invalid inventory quantity for {name}.")
                upc = str(row.get("upc") or "").strip()
                external_product_id = str(row.get("external_product_id") or "").strip()
                sku = str(row.get("sku") or upc or external_product_id).strip().upper()
                if not sku:
                    sku = f"RETAIL-{hashlib.sha1(name.casefold().encode('utf-8')).hexdigest()[:10].upper()}"
                unit = str(row.get("unit") or "unit").strip().lower()
                unit_cost = _numeric_value(row.get("unit_cost"))
                retail_price = _numeric_value(row.get("retail_price"))
                if min(unit_cost, retail_price) < 0:
                    raise ValueError(f"Invalid cost or price for {name}.")
                product = products.get(sku)
                if product is None:
                    product = Product(
                        organization_id=organization_id,
                        sku=sku,
                        name=name,
                        item_type="finished_good",
                        base_unit=unit,
                        unit_cost=unit_cost,
                        retail_price=retail_price,
                        upc=upc,
                        external_product_id=external_product_id,
                        active=True,
                    )
                    session.add(product)
                    session.flush()
                    products[sku] = product
                    stats["products_created"] += 1
                else:
                    product.name = name
                    product.base_unit = unit
                    product.unit_cost = unit_cost
                    product.retail_price = retail_price
                    product.upc = upc or product.upc
                    product.external_product_id = external_product_id or product.external_product_id
                    product.active = True
                package_id = str(row.get("compliance_package_id") or "").strip()
                external_inventory_id = str(row.get("external_inventory_id") or "").strip()
                location = str(row.get("location_code") or "UNASSIGNED").strip().upper()
                lot_code = str(
                    row.get("lot_code")
                    or package_id
                    or external_inventory_id
                    or f"RETAIL-{sku}-{location}"
                ).strip().upper()
                barcode_value = str(row.get("barcode_value") or package_id or upc or "").strip()
                lot = lots.get(lot_code)
                if lot is None:
                    lot = InventoryLot(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        product_id=product.id,
                        lot_code=lot_code,
                        compliance_package_id=package_id,
                        external_inventory_id=external_inventory_id,
                        barcode_value=barcode_value,
                        location_code=location,
                        status="available",
                        received_at=utc_now(),
                        notes="Imported from retail inventory snapshot.",
                    )
                    session.add(lot)
                    session.flush()
                    lots[lot_code] = lot
                    stats["lots_created"] += 1
                else:
                    lot.product_id = product.id
                    lot.compliance_package_id = package_id or lot.compliance_package_id
                    lot.external_inventory_id = external_inventory_id or lot.external_inventory_id
                    lot.barcode_value = barcode_value or lot.barcode_value
                    lot.location_code = location
                    lot.status = "available"
                live_balance = self._lot_balance(session, lot.id)
                correction = quantity - live_balance
                if abs(correction) > 1e-9:
                    session.add(
                        InventoryTransaction(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            lot_id=lot.id,
                            transaction_type="adjustment",
                            quantity_delta=correction,
                            unit=unit,
                            reason="Retail inventory snapshot synchronization",
                            reference=str(reference or "Retail inventory import"),
                            actor=str(actor),
                        )
                    )
                    stats["adjustments"] += 1
                stats["rows"] += 1
            if not stats["rows"]:
                raise ValueError("No rows contained a product name.")
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="retail_inventory_snapshot",
                    entity_id=facility_id,
                    action="imported",
                    actor=str(actor),
                    changes_json=json.dumps(stats | {"reference": str(reference or "")}),
                )
            )
        return stats

    def _matching_scan_lines(
        self,
        session: Session,
        audit_id: str,
        raw_code: str,
    ) -> tuple[set[str], list[InventoryAuditLine]]:
        candidates = _identifier_candidates(raw_code)
        result_rows = list(
            session.execute(
                select(InventoryAuditLine, InventoryLot, Product)
                .join(InventoryLot, InventoryLot.id == InventoryAuditLine.lot_id)
                .join(Product, Product.id == InventoryLot.product_id)
                .where(InventoryAuditLine.audit_id == audit_id)
            )
        )
        matches: list[InventoryAuditLine] = []
        for line, lot, product in result_rows:
            identifiers = {
                _normalize_identifier(value)
                for value in (
                    lot.compliance_package_id,
                    lot.lot_code,
                    lot.external_inventory_id,
                    lot.barcode_value,
                    product.sku,
                    product.upc,
                    product.external_product_id,
                )
                if str(value or "").strip()
            }
            if identifiers.intersection(candidates):
                matches.append(line)
        return candidates, matches

    def preview_scanned_item(
        self,
        organization_id: str,
        facility_id: str,
        audit_id: str,
        *,
        raw_code: str,
        actor: str,
        recount: bool = False,
    ) -> InventoryAuditLine:
        """Resolve a live scan before asking the operator for its physical count."""

        raw = str(raw_code or "").strip()
        if not raw:
            raise ValueError("Scan or enter a product code first.")
        failure: str | None = None
        matched_line: InventoryAuditLine | None = None
        with self._session_factory.begin() as session:
            audit = self._require_audit(session, organization_id, audit_id, facility_id)
            if audit.status in {"completed", "cancelled"}:
                raise ValueError("Completed or cancelled audits cannot be edited.")
            candidates, matches = self._matching_scan_lines(session, audit.id, raw)
            status = "matched"
            if not matches:
                status = "unmatched"
                failure = "No product, lot, UPC, Dutchie ID, or METRC package matched that scan."
            elif len(matches) > 1:
                status = "ambiguous"
                failure = "That code matches multiple lots. Scan the lot/package-specific label or choose the lot manually."
            else:
                matched_line = matches[0]
                if recount and not matched_line.recount_required:
                    failure = "This item is not currently waiting for a recount."
                elif not recount and matched_line.first_count_quantity is not None:
                    failure = "This item already has a first-pass count. Use its recount or correction workflow instead."
            if failure:
                session.add(
                    InventoryAuditScan(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        audit_id=audit.id,
                        audit_line_id=matched_line.id if matched_line else None,
                        raw_code=raw,
                        normalized_code=next(iter(candidates), _normalize_identifier(raw))[:512],
                        match_status=status,
                        scan_stage="recount" if recount else "first_count",
                        scanned_by=str(actor),
                    )
                )
        if failure:
            raise ValueError(failure)
        assert matched_line is not None
        return matched_line

    def record_scanned_count(
        self,
        organization_id: str,
        facility_id: str,
        audit_id: str,
        *,
        raw_code: str,
        quantity: float,
        actor: str,
        recount: bool = False,
        replace_existing: bool = False,
        reason: str = "",
        notes: str = "",
    ) -> InventoryAuditLine:
        raw = str(raw_code or "").strip()
        if not raw:
            raise ValueError("Scan or enter a product code first.")
        count = float(quantity)
        if not math.isfinite(count) or count < 0:
            raise ValueError("Physical counts cannot be negative.")
        failure: str | None = None
        matched_line: InventoryAuditLine | None = None
        with self._session_factory.begin() as session:
            audit = self._require_audit(session, organization_id, audit_id, facility_id)
            if audit.status in {"completed", "cancelled"}:
                raise ValueError("Completed or cancelled audits cannot be edited.")
            candidates, matches = self._matching_scan_lines(session, audit.id, raw)
            status = "matched"
            if not matches:
                status = "unmatched"
                failure = "No product, lot, UPC, Dutchie ID, or METRC package matched that scan."
            elif len(matches) > 1:
                status = "ambiguous"
                failure = "That code matches multiple lots. Scan the lot/package-specific label or choose the lot manually."
            else:
                matched_line = matches[0]
                if recount:
                    if not matched_line.recount_required:
                        failure = "This item is not currently waiting for a recount."
                    else:
                        matched_line.recount_quantity = count
                        matched_line.counted_quantity = count
                        matched_line.variance_quantity = count - float(matched_line.expected_quantity)
                        matched_line.recount_required = False
                else:
                    if matched_line.first_count_quantity is not None and not replace_existing:
                        failure = "This item already has a first-pass count. Use its recount or correction workflow instead."
                    else:
                        matched_line.first_count_quantity = count
                        matched_line.counted_quantity = count
                        matched_line.variance_quantity = count - float(matched_line.expected_quantity)
                        matched_line.recount_required = (
                            abs(matched_line.variance_quantity) > float(audit.recount_tolerance)
                        )
                if not failure:
                    matched_line.reason = str(reason or "").strip()
                    matched_line.notes = str(notes or "").strip()
                    matched_line.counted_by = str(actor)
                    matched_line.counted_at = utc_now()
                    audit.status = "in_progress"
            session.add(
                InventoryAuditScan(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    audit_id=audit.id,
                    audit_line_id=matched_line.id if matched_line else None,
                    raw_code=raw,
                    normalized_code=next(iter(candidates), _normalize_identifier(raw))[:512],
                    match_status=status,
                    scan_stage="recount" if recount else "first_count",
                    scanned_by=str(actor),
                )
            )
            if matched_line and not failure:
                self._audit_event(
                    session,
                    audit,
                    "recount_recorded" if recount else "count_recorded",
                    actor,
                    {
                        "line_id": matched_line.id,
                        "quantity": count,
                        "recount_required": matched_line.recount_required,
                    },
                )
        if failure:
            raise ValueError(failure)
        assert matched_line is not None
        return matched_line

    def save_counts(
        self,
        organization_id: str,
        facility_id: str,
        audit_id: str,
        *,
        counts: Iterable[Mapping[str, object]],
        actor: str,
    ) -> InventoryAudit:
        submitted = list(counts)
        with self._session_factory.begin() as session:
            audit = self._require_audit(session, organization_id, audit_id, facility_id)
            if audit.status in {"completed", "cancelled"}:
                raise ValueError("Completed or cancelled audits cannot be edited.")
            lines = {
                line.id: line
                for line in session.scalars(
                    select(InventoryAuditLine).where(InventoryAuditLine.audit_id == audit.id)
                )
            }
            changed = 0
            for row in submitted:
                line = lines.get(str(row.get("line_id") or ""))
                if not line:
                    raise ValueError("An audit line was not found in this audit.")
                value = row.get("counted_quantity")
                if value is None or str(value).strip() == "":
                    continue
                count = float(value)
                if not math.isfinite(count) or count < 0:
                    raise ValueError("Physical counts cannot be negative.")
                line.first_count_quantity = count
                line.counted_quantity = count
                line.variance_quantity = count - float(line.expected_quantity)
                line.recount_required = abs(line.variance_quantity) > float(audit.recount_tolerance)
                line.reason = str(row.get("reason") or "").strip()
                line.notes = str(row.get("notes") or "").strip()
                line.counted_by = str(actor)
                line.counted_at = utc_now()
                changed += 1
            if changed:
                audit.status = "in_progress"
                self._audit_event(session, audit, "counts_saved", actor, {"line_count": changed})
        return audit

    def complete_audit(
        self,
        organization_id: str,
        facility_id: str,
        audit_id: str,
        *,
        actor: str,
        post_adjustments: bool,
    ) -> InventoryAudit:
        with self._session_factory.begin() as session:
            audit = self._require_audit(session, organization_id, audit_id, facility_id)
            if audit.status in {"completed", "cancelled"}:
                raise ValueError("This audit is already closed.")
            lines = list(
                session.scalars(
                    select(InventoryAuditLine).where(InventoryAuditLine.audit_id == audit.id)
                )
            )
            if not lines or any(line.first_count_quantity is None for line in lines):
                raise ValueError("Count every lot before completing the audit.")
            if any(line.recount_required for line in lines):
                raise ValueError("Finish every required recount before completing the audit.")
            adjustments = 0
            if post_adjustments:
                for line in lines:
                    live_balance = self._lot_balance(session, line.lot_id)
                    correction = float(line.counted_quantity) - live_balance
                    if abs(correction) <= 1e-9:
                        continue
                    transaction = InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=line.lot_id,
                        transaction_type="adjustment",
                        quantity_delta=correction,
                        unit=line.unit,
                        reason=line.reason or "Physical inventory reconciliation",
                        reference=audit.audit_number,
                        actor=str(actor),
                    )
                    session.add(transaction)
                    session.flush()
                    line.adjustment_transaction_id = transaction.id
                    adjustments += 1
            audit.status = "completed"
            audit.completed_at = utc_now()
            audit.completed_by = str(actor)
            self._audit_event(
                session,
                audit,
                "completed",
                actor,
                {"adjustments_posted": adjustments, "post_adjustments": bool(post_adjustments)},
            )
        return audit

    @staticmethod
    def _lot_balance(session: Session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _require_scope(session: Session, organization_id: str, facility_id: str) -> None:
        organization = session.get(Organization, organization_id)
        facility = session.get(Facility, facility_id)
        if not organization:
            raise ValueError("Organization was not found.")
        if not facility or facility.organization_id != organization_id:
            raise ValueError("Facility was not found in this organization.")

    @staticmethod
    def _require_audit(
        session: Session,
        organization_id: str,
        audit_id: str,
        facility_id: str | None = None,
    ) -> InventoryAudit:
        audit = session.get(InventoryAudit, audit_id)
        if not audit or audit.organization_id != organization_id:
            raise ValueError("Inventory audit was not found.")
        if facility_id and audit.facility_id != facility_id:
            raise ValueError("Inventory audit was not found in this facility.")
        return audit

    @staticmethod
    def _audit_event(
        session: Session,
        audit: InventoryAudit,
        action: str,
        actor: str,
        changes: Mapping[str, object],
    ) -> None:
        session.add(
            AuditEvent(
                organization_id=audit.organization_id,
                facility_id=audit.facility_id,
                entity_type="inventory_audit",
                entity_id=audit.id,
                action=action,
                actor=str(actor),
                changes_json=json.dumps(dict(changes), default=str),
            )
        )


def _normalize_identifier(value: object) -> str:
    return re.sub(r"\s+", "", unquote(str(value or "")).strip()).upper()


def _numeric_value(value: object) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]+", "", str(value).replace(",", ""))
    return float(cleaned or 0.0)


def _identifier_candidates(raw_code: str) -> set[str]:
    """Return exact and embedded identifiers from scanner, QR, URL, or JSON payloads."""

    decoded = unquote(str(raw_code or "").strip())
    candidates = {_normalize_identifier(decoded)}
    if decoded.startswith("]") and len(decoded) > 3:
        candidates.add(_normalize_identifier(decoded[3:]))
    for token in re.findall(r"[A-Za-z0-9_-]{6,}", decoded):
        candidates.add(_normalize_identifier(token))
    try:
        payload = json.loads(decoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, Mapping):
        for value in payload.values():
            if isinstance(value, (str, int, float)):
                candidates.add(_normalize_identifier(value))
    return {candidate for candidate in candidates if candidate}
