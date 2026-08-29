from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import utc_now
from modules.traceability.models import ReceivingPreflight
from services.metrc_receiving import fetch_confirmed_inbound_snapshot
from ..schemas.inventory import InventoryReceiptCreate, InventoryReceiptResult
from .inventory_receiving import InventoryReceiptBatchService


PREFLIGHT_TTL_MINUTES = 10


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_json(snapshot).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Receiving quantities must be valid decimal values.") from exc


def _canonical_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    packages = [
        {
            "package_record_id": str(row.get("package_record_id") or "").strip(),
            "package_id": str(row.get("package_id") or "").strip(),
            "identity": str(row.get("identity") or "").strip(),
            "quantity": str(row.get("quantity") or "0").strip(),
            "unit": str(row.get("unit") or "unit").strip() or "unit",
            "unit_key": str(row.get("unit_key") or row.get("unit") or "unit").strip().casefold(),
            "lab_testing_state": str(row.get("lab_testing_state") or "").strip(),
            "delivery_id": str(row.get("delivery_id") or "").strip(),
        }
        for row in raw.get("packages") or []
    ]
    packages.sort(key=lambda row: (row["identity"].casefold(), row["delivery_id"], row["package_record_id"]))
    return {
        "transfer_id": str(raw.get("transfer_id") or "").strip(),
        "manifest": str(raw.get("manifest") or "").strip(),
        "vendor": str(raw.get("vendor") or "").strip(),
        "vendor_license": str(raw.get("vendor_license") or "").strip(),
        "packages": packages,
    }


def _public(row: ReceivingPreflight) -> dict[str, Any]:
    snapshot = json.loads(row.snapshot_json or "{}")
    return {
        "id": row.id,
        "provider": row.provider,
        "operation": row.operation,
        "transfer_id": row.transfer_id,
        "jurisdiction": row.jurisdiction,
        "environment": row.environment,
        "license_number": row.license_number,
        "status": row.status,
        "snapshot_digest": row.snapshot_digest,
        "snapshot": snapshot,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "consumed_at": row.consumed_at.isoformat() if row.consumed_at else None,
        "reason": row.reason,
    }


class ReceivingPreflightService:
    """Gate Metrc-sourced local receiving behind two matching provider reads.

    This service never accepts or edits a Metrc transfer. It records a strict
    license-scoped read snapshot, requires an identical fresh read before local
    posting, then marks the preflight processing before the atomic local receipt
    starts. A crash in that narrow window remains blocked for reconciliation
    instead of being retried blindly.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def _read_snapshot(self, *, metrc: Any, transfer_id: str) -> dict[str, Any]:
        result = fetch_confirmed_inbound_snapshot(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            license_number=metrc.license_number,
            transfer_id=transfer_id,
            environment=metrc.environment,
        )
        if not result.get("ok"):
            message = str(result.get("message") or "Metrc receiving verification failed.")
            raise RuntimeError(message)
        snapshot = _canonical_snapshot(result)
        if not snapshot["packages"]:
            raise ValueError("The pending Metrc transfer has no remaining packages to receive.")
        return snapshot

    def prepare(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation: str,
        actor: str,
        transfer_id: str,
        metrc: Any,
    ) -> dict[str, Any]:
        transfer_id = str(transfer_id or "").strip()
        if operation not in {"retail", "production"}:
            raise ValueError("Unsupported inventory operation.")
        if not transfer_id:
            raise ValueError("A Metrc transfer id is required.")
        if not getattr(metrc, "configured", False) or getattr(metrc, "status", "") != "connected" or not getattr(metrc, "trusted_mapping", False):
            raise ValueError("A connected and verified Metrc facility mapping is required for controlled receiving.")

        snapshot = self._read_snapshot(metrc=metrc, transfer_id=transfer_id)
        digest = _digest(snapshot)
        now = utc_now()
        expires = now + timedelta(minutes=PREFLIGHT_TTL_MINUTES)
        with Session(self.engine) as session, session.begin():
            active = session.scalars(
                select(ReceivingPreflight).where(
                    ReceivingPreflight.organization_id == organization_id,
                    ReceivingPreflight.facility_id == facility_id,
                    ReceivingPreflight.operation == operation,
                    ReceivingPreflight.transfer_id == transfer_id,
                    ReceivingPreflight.status == "prepared",
                )
            ).all()
            for existing in active:
                existing.status = "cancelled"
                existing.reason = "Superseded by a newer provider-confirmed receiving preflight."
            row = ReceivingPreflight(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                operation=operation,
                transfer_id=transfer_id,
                jurisdiction=str(metrc.state or "").strip().upper(),
                environment=str(metrc.environment or "").strip().casefold(),
                license_number=str(metrc.license_number or "").strip(),
                snapshot_digest=digest,
                snapshot_json=_json(snapshot),
                status="prepared",
                requested_by=actor,
                expires_at=expires,
            )
            session.add(row)
            session.flush()
            return _public(row)

    def _load_for_update(self, session: Session, *, preflight_id: str, organization_id: str, facility_id: str, operation: str) -> ReceivingPreflight:
        row = session.scalar(
            select(ReceivingPreflight)
            .where(
                ReceivingPreflight.id == preflight_id,
                ReceivingPreflight.organization_id == organization_id,
                ReceivingPreflight.facility_id == facility_id,
                ReceivingPreflight.operation == operation,
            )
            .with_for_update()
        )
        if row is None:
            raise ValueError("Receiving preflight was not found for the active facility.")
        return row

    def _authoritative_receipts(self, *, snapshot: dict[str, Any], rows: list[InventoryReceiptCreate]) -> list[InventoryReceiptCreate]:
        provider = {str(item["identity"]).casefold(): item for item in snapshot.get("packages") or []}
        if len(provider) != len(snapshot.get("packages") or []):
            raise ValueError("The provider snapshot contains duplicate package identities and cannot be posted safely.")
        reviewed: dict[str, InventoryReceiptCreate] = {}
        for row in rows:
            identity = str(row.package_id or row.lot_code or "").strip().casefold()
            if not identity:
                raise ValueError("Every reviewed receipt row must identify the provider package.")
            if identity in reviewed:
                raise ValueError("The reviewed receipt contains a duplicate provider package.")
            reviewed[identity] = row
        if set(reviewed) != set(provider):
            raise ValueError("The reviewed package set no longer matches the provider-confirmed transfer snapshot.")

        manifest_reference = str(snapshot.get("manifest") or snapshot.get("transfer_id") or "").strip()
        source_name = str(snapshot.get("vendor") or snapshot.get("vendor_license") or "").strip()
        sanitized: list[InventoryReceiptCreate] = []
        for identity, provider_row in provider.items():
            row = reviewed[identity]
            if _decimal(row.quantity) != _decimal(provider_row["quantity"]):
                raise ValueError(f"Reviewed quantity no longer matches Metrc for {provider_row['identity']}.")
            if str(row.unit or "").strip().casefold() != str(provider_row["unit_key"]):
                raise ValueError(f"Reviewed unit no longer matches Metrc for {provider_row['identity']}.")
            sanitized.append(
                row.model_copy(
                    update={
                        "package_id": str(provider_row.get("package_id") or provider_row["identity"]),
                        "lot_code": str(provider_row.get("package_id") or provider_row["identity"]),
                        "quantity": float(_decimal(provider_row["quantity"])),
                        "unit": str(provider_row["unit"]),
                        "source_name": source_name,
                        "manifest_reference": manifest_reference,
                        "lab_testing_state": str(provider_row.get("lab_testing_state") or ""),
                    }
                )
            )
        return sanitized

    def commit(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation: str,
        actor: str,
        preflight_id: str,
        rows: list[InventoryReceiptCreate],
        metrc: Any,
    ) -> dict[str, Any]:
        now = utc_now()
        stale_error = ""
        stored_snapshot: dict[str, Any] = {}
        transfer_id = ""
        stored_digest = ""
        with Session(self.engine) as session, session.begin():
            row = self._load_for_update(
                session,
                preflight_id=preflight_id,
                organization_id=organization_id,
                facility_id=facility_id,
                operation=operation,
            )
            if row.status == "consumed":
                return {"preflight": _public(row), "receipts": json.loads(row.local_result_json or "[]"), "idempotent": True}
            if row.status == "processing":
                raise ValueError("This receipt has an unknown local outcome and requires reconciliation before any retry.")
            if row.status != "prepared":
                raise ValueError(f"This receiving preflight is {row.status} and cannot be posted.")
            if _aware(row.expires_at) <= _aware(now):
                row.status = "stale"
                row.reason = "The provider confirmation expired before local posting."
                stale_error = "The provider confirmation expired. Refresh the transfer and prepare a new receipt."
            elif (
                row.jurisdiction != str(metrc.state or "").strip().upper()
                or row.environment != str(metrc.environment or "").strip().casefold()
                or row.license_number != str(metrc.license_number or "").strip()
                or not getattr(metrc, "trusted_mapping", False)
                or getattr(metrc, "status", "") != "connected"
            ):
                row.status = "stale"
                row.reason = "The active Metrc facility mapping changed after preflight preparation."
                stale_error = "The active Metrc facility mapping changed. Prepare a new receiving preflight."
            else:
                stored_snapshot = json.loads(row.snapshot_json or "{}")
                transfer_id = row.transfer_id
                stored_digest = row.snapshot_digest
        if stale_error:
            raise ValueError(stale_error)

        fresh_snapshot = self._read_snapshot(metrc=metrc, transfer_id=transfer_id)
        fresh_digest = _digest(fresh_snapshot)
        if fresh_digest != stored_digest:
            with Session(self.engine) as session, session.begin():
                current = self._load_for_update(session, preflight_id=preflight_id, organization_id=organization_id, facility_id=facility_id, operation=operation)
                if current.status == "prepared":
                    current.status = "stale"
                    current.reason = "The Metrc transfer package snapshot changed between preflight and posting."
            raise ValueError("Metrc changed after review. Refresh the inbound transfer before posting inventory.")

        sanitized = self._authoritative_receipts(snapshot=stored_snapshot, rows=rows)
        with Session(self.engine) as session, session.begin():
            current = self._load_for_update(session, preflight_id=preflight_id, organization_id=organization_id, facility_id=facility_id, operation=operation)
            if current.status != "prepared":
                if current.status == "consumed":
                    return {"preflight": _public(current), "receipts": json.loads(current.local_result_json or "[]"), "idempotent": True}
                raise ValueError("The receiving preflight is no longer available for posting.")
            current.status = "processing"
            current.consumed_by = actor
            current.reason = "Provider readback matched; local atomic receipt started."

        try:
            results = InventoryReceiptBatchService(self.engine).post(
                organization_id,
                facility_id,
                operation=operation,
                rows=sanitized,
                actor=actor,
            )
        except ValueError as exc:
            with Session(self.engine) as session, session.begin():
                current = self._load_for_update(session, preflight_id=preflight_id, organization_id=organization_id, facility_id=facility_id, operation=operation)
                if current.status == "processing":
                    current.status = "cancelled"
                    current.reason = f"Local receipt validation failed before commit: {exc}"
            raise

        serialized = [result.model_dump(mode="json") if isinstance(result, InventoryReceiptResult) else dict(result) for result in results]
        with Session(self.engine) as session, session.begin():
            current = self._load_for_update(session, preflight_id=preflight_id, organization_id=organization_id, facility_id=facility_id, operation=operation)
            if current.status != "processing":
                raise RuntimeError("Receiving preflight state changed while local inventory was posting; reconcile before retrying.")
            current.status = "consumed"
            current.consumed_by = actor
            current.consumed_at = utc_now()
            current.local_result_json = _json(serialized)
            current.reason = "Provider readback matched and the atomic local receipt completed."
            session.flush()
            public = _public(current)
        return {"preflight": public, "receipts": serialized, "idempotent": False}
