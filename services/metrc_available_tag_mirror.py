from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility
from modules.regulatory.metrc_process_models import MetrcTagInventory


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return value if isinstance(value, dict) else record


def _label(record: dict[str, Any]) -> str:
    source = _source(record)
    return str(
        record.get("label")
        or source.get("Label")
        or source.get("Tag")
        or source.get("TagNumber")
        or ""
    ).strip()


def _provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    return str(record.get("provider_id") or source.get("Id") or source.get("ID") or source.get("id") or "").strip()


class MetrcAvailableTagMirror:
    """Project one complete Metrc available-tag snapshot into durable selectors.

    Provider snapshot state owns only whether an otherwise unused tag is currently
    available. Local reservation/consumption lifecycle is authoritative once a tag
    is reserved, used or voided, so those states are never resurrected by sync.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def replace(
        self,
        *,
        organization_id: str,
        facility_id: str,
        jurisdiction_code: str,
        license_number: str,
        environment: str,
        tag_type: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        env = str(environment or "").strip().casefold()
        jurisdiction = str(jurisdiction_code or "").strip().upper()
        license_value = str(license_number or "").strip()
        kind = str(tag_type or "").strip().casefold()
        if env not in {"sandbox", "production"}:
            raise ValueError("Metrc tag mirror requires sandbox or production environment.")
        if kind not in {"plant", "package"}:
            raise ValueError("Metrc tag mirror supports plant or package tags.")
        if not jurisdiction or not license_value:
            raise ValueError("Metrc tag mirror requires exact jurisdiction and facility license.")

        by_label: dict[str, dict[str, Any]] = {}
        duplicates = 0
        for source_record in records:
            if not isinstance(source_record, dict):
                continue
            record = dict(source_record)
            label = _label(record)
            if not label:
                continue
            if label in by_label:
                duplicates += 1
                continue
            by_label[label] = record

        now = datetime.now(timezone.utc)
        created = 0
        restored_available = 0
        marked_unavailable = 0
        protected_local_lifecycle = 0
        with self.sessions.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id or not facility.active:
                raise ValueError("The active facility was not found in this organization.")

            existing = list(
                session.scalars(
                    select(MetrcTagInventory).where(
                        MetrcTagInventory.organization_id == organization_id,
                        MetrcTagInventory.facility_id == facility_id,
                        MetrcTagInventory.environment == env,
                        MetrcTagInventory.tag_type == kind,
                    )
                )
            )
            existing_by_label = {row.label: row for row in existing}

            for row in existing:
                if row.status in {"reserved", "used", "voided"}:
                    protected_local_lifecycle += 1
                    continue
                if row.label not in by_label and row.status == "available":
                    row.status = "unavailable"
                    row.synced_at = now
                    marked_unavailable += 1

            for label, record in by_label.items():
                row = existing_by_label.get(label)
                if row is None:
                    session.add(
                        MetrcTagInventory(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            jurisdiction_code=jurisdiction,
                            license_number=license_value,
                            environment=env,
                            tag_type=kind,
                            label=label,
                            provider_id=_provider_id(record),
                            status="available",
                            synced_at=now,
                        )
                    )
                    created += 1
                    continue

                # Fail closed across regulatory identity. A tag row may not be
                # silently rebound from one license/jurisdiction to another.
                if row.license_number and row.license_number != license_value:
                    raise ValueError(f"Existing {kind} tag {label} belongs to a different Metrc license.")
                if row.jurisdiction_code and row.jurisdiction_code != jurisdiction:
                    raise ValueError(f"Existing {kind} tag {label} belongs to a different Metrc jurisdiction.")
                row.provider_id = _provider_id(record) or row.provider_id
                row.synced_at = now
                if row.status == "unavailable":
                    row.status = "available"
                    restored_available += 1

        return {
            "tag_type": kind,
            "available_count": len(by_label),
            "created_count": created,
            "restored_available_count": restored_available,
            "marked_unavailable_count": marked_unavailable,
            "protected_local_lifecycle_count": protected_local_lifecycle,
            "duplicate_provider_label_count": duplicates,
            "synced_at": now.isoformat(),
            "environment": env,
            "license_number": license_value,
        }
