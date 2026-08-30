from __future__ import annotations

import hashlib
import json
import math

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from modules.coman.models import InventoryAuditLine, InventoryAuditScan, utc_now
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.offline.models import OfflineMutationReceipt


ENDPOINT_KEY = "inventory_audit_scan_count"


class OfflineMutationConflict(ValueError):
    """The queued mutation can no longer be applied without operator review."""


def _fingerprint(
    *,
    audit_id: str,
    raw_code: str,
    quantity: float,
    recount: bool,
    reason: str,
    notes: str,
) -> str:
    payload = {
        "audit_id": str(audit_id),
        "raw_code": str(raw_code or "").strip(),
        "quantity": float(quantity),
        "recount": bool(recount),
        "reason": str(reason or "").strip(),
        "notes": str(notes or "").strip(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IdempotentAuditCountService:
    """Apply one offline-safe physical count and its replay receipt atomically."""

    def __init__(self, engine: Engine):
        self.repository = InventoryAuditRepository(engine)

    @staticmethod
    def _clean_key(idempotency_key: str) -> str:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ValueError("An idempotency key is required for offline audit replay.")
        if len(key) > 160:
            raise ValueError("The idempotency key cannot exceed 160 characters.")
        return key

    @staticmethod
    def _receipt_statement(organization_id: str, facility_id: str, key: str):
        return select(OfflineMutationReceipt).where(
            OfflineMutationReceipt.organization_id == organization_id,
            OfflineMutationReceipt.facility_id == facility_id,
            OfflineMutationReceipt.endpoint_key == ENDPOINT_KEY,
            OfflineMutationReceipt.idempotency_key == key,
        )

    def _result_from_receipt(
        self,
        session,
        receipt: OfflineMutationReceipt,
        *,
        fingerprint: str,
        organization_id: str,
        facility_id: str,
        audit_id: str,
    ) -> InventoryAuditLine:
        if receipt.request_fingerprint != fingerprint:
            raise OfflineMutationConflict("That offline idempotency key was already used for a different physical count.")
        if receipt.parent_entity_id != audit_id or receipt.entity_type != "inventory_audit_line":
            raise OfflineMutationConflict("The saved offline replay receipt does not match this audit.")
        line = session.get(InventoryAuditLine, receipt.entity_id)
        if (
            line is None
            or line.organization_id != organization_id
            or line.facility_id != facility_id
            or line.audit_id != audit_id
        ):
            raise OfflineMutationConflict("The counted audit line is no longer available in this facility.")
        return line

    def record(
        self,
        organization_id: str,
        facility_id: str,
        audit_id: str,
        *,
        raw_code: str,
        quantity: float,
        actor: str,
        idempotency_key: str,
        recount: bool = False,
        reason: str = "",
        notes: str = "",
    ) -> InventoryAuditLine:
        key = self._clean_key(idempotency_key)
        raw = str(raw_code or "").strip()
        if not raw:
            raise ValueError("Scan or enter a product code first.")
        count = float(quantity)
        if not math.isfinite(count) or count < 0:
            raise ValueError("Physical counts cannot be negative.")
        fingerprint = _fingerprint(
            audit_id=audit_id,
            raw_code=raw,
            quantity=count,
            recount=recount,
            reason=reason,
            notes=notes,
        )

        try:
            with self.repository._session_factory.begin() as session:
                receipt = session.scalar(self._receipt_statement(organization_id, facility_id, key))
                if receipt is not None:
                    return self._result_from_receipt(
                        session,
                        receipt,
                        fingerprint=fingerprint,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        audit_id=audit_id,
                    )

                audit = self.repository._require_audit(session, organization_id, audit_id, facility_id)
                if audit.status not in {"draft", "in_progress"}:
                    raise OfflineMutationConflict(
                        f"Audit status changed to {audit.status}. Review this queued count before applying it."
                    )

                candidates, matches = self.repository._matching_scan_lines(session, audit.id, raw)
                if not matches:
                    raise OfflineMutationConflict(
                        "The queued code no longer matches an item in this audit. Review the count before applying it."
                    )
                if len(matches) > 1:
                    raise OfflineMutationConflict(
                        "The queued code now matches multiple lots. Review the count and choose the exact lot."
                    )

                line = matches[0]
                if recount:
                    if not line.recount_required:
                        raise OfflineMutationConflict(
                            "This item is no longer waiting for a recount. Review the queued count before applying it."
                        )
                    line.recount_quantity = count
                    line.counted_quantity = count
                    line.variance_quantity = count - float(line.expected_quantity)
                    line.recount_required = False
                else:
                    if line.first_count_quantity is not None:
                        raise OfflineMutationConflict(
                            "This item received a first-pass count before the offline capture replayed. Review both counts."
                        )
                    line.first_count_quantity = count
                    line.counted_quantity = count
                    line.variance_quantity = count - float(line.expected_quantity)
                    line.recount_required = abs(line.variance_quantity) > float(audit.recount_tolerance)

                line.reason = str(reason or "").strip()
                line.notes = str(notes or "").strip()
                line.counted_by = str(actor)
                line.counted_at = utc_now()
                audit.status = "in_progress"

                session.add(
                    InventoryAuditScan(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        audit_id=audit.id,
                        audit_line_id=line.id,
                        raw_code=raw,
                        normalized_code=next(iter(candidates), raw)[:512],
                        match_status="matched",
                        scan_stage="recount" if recount else "first_count",
                        scanned_by=str(actor),
                    )
                )
                self.repository._audit_event(
                    session,
                    audit,
                    "recount_recorded" if recount else "count_recorded",
                    actor,
                    {
                        "line_id": line.id,
                        "quantity": count,
                        "recount_required": line.recount_required,
                        "offline_replay": True,
                        "idempotency_key": key,
                    },
                )
                session.add(
                    OfflineMutationReceipt(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        endpoint_key=ENDPOINT_KEY,
                        idempotency_key=key,
                        request_fingerprint=fingerprint,
                        entity_type="inventory_audit_line",
                        entity_id=line.id,
                        parent_entity_id=audit.id,
                        actor=str(actor),
                    )
                )
                session.flush()
                return line
        except IntegrityError:
            # A concurrent retry may win the unique receipt race. The losing
            # transaction is rolled back in full, then returns the committed
            # winner only when its fingerprint matches this exact request.
            with self.repository._session_factory() as session:
                receipt = session.scalar(self._receipt_statement(organization_id, facility_id, key))
                if receipt is None:
                    raise
                return self._result_from_receipt(
                    session,
                    receipt,
                    fingerprint=fingerprint,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    audit_id=audit_id,
                )
