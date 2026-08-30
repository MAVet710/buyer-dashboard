from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import utc_now
from modules.traceability.models import ReceivingDiscrepancy, ReceivingPreflight
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


def _decimal_text(value: Any) -> str:
    value = _decimal(value)
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


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


def _public_discrepancy(row: ReceivingDiscrepancy) -> dict[str, Any]:
    return {
        "id": row.id,
        "preflight_id": row.preflight_id,
        "transfer_id": row.transfer_id,
        "package_identity": row.package_identity,
        "provider_quantity": row.provider_quantity,
        "observed_quantity": row.observed_quantity,
        "unit": row.unit,
        "discrepancy_type": row.discrepancy_type,
        "status": row.status,
        "note": row.note,
        "recorded_by": row.recorded_by,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolution_note": row.resolution_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class ReceivingPreflightService:
    """Gate Metrc-sourced local receiving behind matching provider and physical reads.

    This service never accepts or edits a Metrc transfer. It records a strict
    license-scoped provider snapshot, allows the operator to record durable
    physical-vs-provider discrepancies, requires all open discrepancies to be
    resolved, requires an exact physical count at commit, then requires an
    identical fresh provider read before local posting. A crash after the
    processing boundary remains blocked for reconciliation instead of being
    retried blindly.
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
                open_discrepancies = session.scalars(
                    select(ReceivingDiscrepancy).where(
                        ReceivingDiscrepancy.preflight_id == existing.id,
                        ReceivingDiscrepancy.status == "open",
                    )
                ).all()
                for discrepancy in open_discrepancies:
                    discrepancy.status = "cancelled"
                    discrepancy.resolved_by = actor
                    discrepancy.resolved_at = now
                    discrepancy.resolution_note = "Preflight superseded by a newer provider snapshot."
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

    def list_discrepancies(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation: str,
        preflight_id: str,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            preflight = session.scalar(
                select(ReceivingPreflight).where(
                    ReceivingPreflight.id == preflight_id,
                    ReceivingPreflight.organization_id == organization_id,
                    ReceivingPreflight.facility_id == facility_id,
                    ReceivingPreflight.operation == operation,
                )
            )
            if preflight is None:
                raise ValueError("Receiving preflight was not found for the active facility.")
            rows = session.scalars(
                select(ReceivingDiscrepancy)
                .where(
                    ReceivingDiscrepancy.organization_id == organization_id,
                    ReceivingDiscrepancy.facility_id == facility_id,
                    ReceivingDiscrepancy.preflight_id == preflight_id,
                )
                .order_by(ReceivingDiscrepancy.created_at.asc())
            ).all()
            return [_public_discrepancy(row) for row in rows]

    def record_observations(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation: str,
        actor: str,
        preflight_id: str,
        transfer_id: str,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Record physical exceptions without changing provider or inventory state."""

        if not observations:
            raise ValueError("Record at least one physical package observation.")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            preflight = self._load_for_update(
                session,
                preflight_id=preflight_id,
                organization_id=organization_id,
                facility_id=facility_id,
                operation=operation,
            )
            if preflight.transfer_id != str(transfer_id or "").strip():
                raise ValueError("The receiving preflight does not belong to this inbound transfer.")
            if preflight.status != "prepared":
                raise ValueError(f"This receiving preflight is {preflight.status} and cannot accept physical observations.")
            if _aware(preflight.expires_at) <= _aware(now):
                preflight.status = "stale"
                preflight.reason = "The provider confirmation expired before the physical discrepancy was recorded."
                raise ValueError("The provider confirmation expired. Prepare a new receiving preflight.")

            existing_open = session.scalars(
                select(ReceivingDiscrepancy).where(
                    ReceivingDiscrepancy.organization_id == organization_id,
                    ReceivingDiscrepancy.facility_id == facility_id,
                    ReceivingDiscrepancy.preflight_id == preflight_id,
                    ReceivingDiscrepancy.status == "open",
                )
            ).all()
            if existing_open:
                return {
                    "preflight": _public(preflight),
                    "can_post": False,
                    "message": "This preflight already has an open physical discrepancy. Resolve it before recording another observation set.",
                    "discrepancies": [_public_discrepancy(row) for row in existing_open],
                }

            snapshot = json.loads(preflight.snapshot_json or "{}")
            provider_rows = snapshot.get("packages") or []
            provider = {str(item.get("identity") or "").strip().casefold(): item for item in provider_rows}
            if len(provider) != len(provider_rows) or not provider:
                raise ValueError("The provider snapshot contains invalid or duplicate package identities.")

            observed: dict[str, dict[str, Any]] = {}
            for raw in observations:
                identity = str(raw.get("package_id") or raw.get("package_identity") or "").strip()
                if not identity:
                    raise ValueError("Every physical observation must identify a package.")
                key = identity.casefold()
                if key in observed:
                    raise ValueError("The physical observation set contains a duplicate package.")
                quantity = _decimal(raw.get("observed_quantity"))
                if quantity < 0:
                    raise ValueError("Physical receiving quantities cannot be negative.")
                unit = str(raw.get("unit") or "unit").strip() or "unit"
                condition = str(raw.get("condition") or "ok").strip().casefold()
                if condition not in {"ok", "damaged", "other"}:
                    raise ValueError("Physical package condition must be ok, damaged, or other.")
                observed[key] = {
                    "identity": identity,
                    "quantity": quantity,
                    "unit": unit,
                    "condition": condition,
                    "note": str(raw.get("note") or "").strip()[:2000],
                }

            discrepancies: list[ReceivingDiscrepancy] = []
            for key, provider_row in provider.items():
                observation = observed.get(key)
                provider_quantity = _decimal(provider_row.get("quantity"))
                provider_unit = str(provider_row.get("unit") or "unit").strip() or "unit"
                if observation is None:
                    discrepancy_type = "missing"
                    observed_quantity = Decimal("0")
                    note = "Provider package was not present in the physical observation set."
                else:
                    observed_quantity = observation["quantity"]
                    if observation["unit"].casefold() != provider_unit.casefold():
                        discrepancy_type = "other"
                        note = f"Physical unit {observation['unit']} does not match provider unit {provider_unit}. {observation['note']}".strip()
                    elif observation["condition"] == "damaged":
                        discrepancy_type = "damaged"
                        note = observation["note"] or "Package was observed as damaged."
                    elif observation["condition"] == "other":
                        discrepancy_type = "other"
                        note = observation["note"] or "Package requires receiving review."
                    elif observed_quantity == 0 and provider_quantity > 0:
                        discrepancy_type = "missing"
                        note = observation["note"] or "Provider package was not physically present."
                    elif observed_quantity < provider_quantity:
                        discrepancy_type = "short"
                        note = observation["note"]
                    elif observed_quantity > provider_quantity:
                        discrepancy_type = "over"
                        note = observation["note"]
                    else:
                        continue
                discrepancies.append(ReceivingDiscrepancy(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    preflight_id=preflight.id,
                    transfer_id=preflight.transfer_id,
                    package_identity=str(provider_row.get("identity") or observation["identity"] if observation else "").strip(),
                    provider_quantity=_decimal_text(provider_quantity),
                    observed_quantity=_decimal_text(observed_quantity),
                    unit=provider_unit,
                    discrepancy_type=discrepancy_type,
                    note=note,
                    status="open",
                    recorded_by=actor,
                ))

            for key, observation in observed.items():
                if key in provider:
                    continue
                discrepancies.append(ReceivingDiscrepancy(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    preflight_id=preflight.id,
                    transfer_id=preflight.transfer_id,
                    package_identity=observation["identity"],
                    provider_quantity="0",
                    observed_quantity=_decimal_text(observation["quantity"]),
                    unit=observation["unit"],
                    discrepancy_type="unexpected",
                    note=observation["note"] or "Physical package is not present in the provider-confirmed transfer snapshot.",
                    status="open",
                    recorded_by=actor,
                ))

            if not discrepancies:
                return {
                    "preflight": _public(preflight),
                    "can_post": True,
                    "message": "Physical package count matches the provider-confirmed transfer snapshot.",
                    "discrepancies": [],
                }
            session.add_all(discrepancies)
            preflight.reason = f"Physical receiving discrepancy recorded ({len(discrepancies)} open). Resolve before posting local inventory."
            session.flush()
            return {
                "preflight": _public(preflight),
                "can_post": False,
                "message": "Physical receipt differs from the provider-confirmed transfer. Local inventory is blocked until the discrepancy is resolved.",
                "discrepancies": [_public_discrepancy(row) for row in discrepancies],
            }

    def resolve_discrepancy(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation: str,
        actor: str,
        preflight_id: str,
        discrepancy_id: str,
        resolution_note: str,
    ) -> dict[str, Any]:
        note = str(resolution_note or "").strip()
        if len(note) < 3:
            raise ValueError("A resolution note is required.")
        with Session(self.engine) as session, session.begin():
            preflight = self._load_for_update(
                session,
                preflight_id=preflight_id,
                organization_id=organization_id,
                facility_id=facility_id,
                operation=operation,
            )
            row = session.scalar(
                select(ReceivingDiscrepancy)
                .where(
                    ReceivingDiscrepancy.id == discrepancy_id,
                    ReceivingDiscrepancy.organization_id == organization_id,
                    ReceivingDiscrepancy.facility_id == facility_id,
                    ReceivingDiscrepancy.preflight_id == preflight_id,
                )
                .with_for_update()
            )
            if row is None:
                raise ValueError("Receiving discrepancy was not found for the active facility.")
            if row.status == "resolved":
                return _public_discrepancy(row)
            if row.status != "open":
                raise ValueError(f"This receiving discrepancy is {row.status} and cannot be resolved.")
            row.status = "resolved"
            row.resolved_by = actor
            row.resolved_at = utc_now()
            row.resolution_note = note[:2000]
            session.flush()
            remaining = session.scalars(
                select(ReceivingDiscrepancy).where(
                    ReceivingDiscrepancy.preflight_id == preflight.id,
                    ReceivingDiscrepancy.status == "open",
                )
            ).all()
            if not remaining:
                preflight.reason = "All recorded physical discrepancies are resolved; an exact physical count and fresh provider read are still required before posting."
            return _public_discrepancy(row)

    def _open_discrepancies(self, session: Session, *, organization_id: str, facility_id: str, preflight_id: str) -> list[ReceivingDiscrepancy]:
        return list(session.scalars(
            select(ReceivingDiscrepancy).where(
                ReceivingDiscrepancy.organization_id == organization_id,
                ReceivingDiscrepancy.facility_id == facility_id,
                ReceivingDiscrepancy.preflight_id == preflight_id,
                ReceivingDiscrepancy.status == "open",
            )
        ).all())

    def _validate_physical_observations(self, *, snapshot: dict[str, Any], observations: list[dict[str, Any]]) -> None:
        if not observations:
            raise ValueError("A complete physical count is required before posting inventory.")
        provider_rows = snapshot.get("packages") or []
        provider = {str(item.get("identity") or "").strip().casefold(): item for item in provider_rows}
        observed: dict[str, dict[str, Any]] = {}
        for raw in observations:
            identity = str(raw.get("package_id") or raw.get("package_identity") or "").strip()
            if not identity:
                raise ValueError("Every physical observation must identify a package.")
            key = identity.casefold()
            if key in observed:
                raise ValueError("The physical observation set contains a duplicate package.")
            observed[key] = raw
        if set(observed) != set(provider):
            raise ValueError("The physical package set does not exactly match the provider-confirmed transfer. Record a discrepancy instead of posting inventory.")
        for key, provider_row in provider.items():
            raw = observed[key]
            observed_quantity = _decimal(raw.get("observed_quantity"))
            provider_quantity = _decimal(provider_row.get("quantity"))
            observed_unit = str(raw.get("unit") or "unit").strip().casefold()
            provider_unit = str(provider_row.get("unit_key") or provider_row.get("unit") or "unit").strip().casefold()
            condition = str(raw.get("condition") or "ok").strip().casefold()
            if observed_quantity != provider_quantity or observed_unit != provider_unit or condition != "ok":
                raise ValueError("The physical receipt does not exactly match the provider-confirmed transfer. Record and resolve the discrepancy before posting inventory.")

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
        transfer_id: str,
        rows: list[InventoryReceiptCreate],
        observations: list[dict[str, Any]],
        metrc: Any,
    ) -> dict[str, Any]:
        now = utc_now()
        expected_transfer_id = str(transfer_id or "").strip()
        stale_error = ""
        stored_snapshot: dict[str, Any] = {}
        stored_transfer_id = ""
        stored_digest = ""
        with Session(self.engine) as session, session.begin():
            row = self._load_for_update(
                session,
                preflight_id=preflight_id,
                organization_id=organization_id,
                facility_id=facility_id,
                operation=operation,
            )
            if row.transfer_id != expected_transfer_id:
                raise ValueError("The receiving preflight does not belong to this inbound transfer.")
            if row.status == "consumed":
                return {"preflight": _public(row), "receipts": json.loads(row.local_result_json or "[]"), "idempotent": True}
            if row.status == "processing":
                raise ValueError("This receipt has an unknown local outcome and requires reconciliation before any retry.")
            if row.status != "prepared":
                raise ValueError(f"This receiving preflight is {row.status} and cannot be posted.")
            open_discrepancies = self._open_discrepancies(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                preflight_id=preflight_id,
            )
            if open_discrepancies:
                raise ValueError("This receipt has an open physical discrepancy. Resolve it before posting local inventory.")
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
                stored_transfer_id = row.transfer_id
                stored_digest = row.snapshot_digest
        if stale_error:
            raise ValueError(stale_error)

        self._validate_physical_observations(snapshot=stored_snapshot, observations=observations)
        fresh_snapshot = self._read_snapshot(metrc=metrc, transfer_id=stored_transfer_id)
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
            if self._open_discrepancies(session, organization_id=organization_id, facility_id=facility_id, preflight_id=preflight_id):
                raise ValueError("A physical receiving discrepancy was opened during review. Resolve it before posting inventory.")
            current.status = "processing"
            current.consumed_by = actor
            current.reason = "Physical count and provider readback matched; local atomic receipt started."

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
            current.reason = "Physical count and provider readback matched and the atomic local receipt completed."
            session.flush()
            public = _public(current)
        return {"preflight": public, "receipts": serialized, "idempotent": False}
