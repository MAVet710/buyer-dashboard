from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility
from modules.regulatory.metrc_process_models import MetrcTagInventory


def _label(record: dict[str, Any]) -> str:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return str(record.get("label") or source.get("Label") or source.get("Tag") or "").strip()


def _provider_id(record: dict[str, Any]) -> str:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()


class MetrcCultivationTagMirror:
    """Reconcile the facility's plant-tag availability to one fresh Metrc snapshot.

    Only `available`/`unavailable` rows are provider-mirror state. Reserved, used,
    and voided tags are never resurrected automatically even if a provider
    response is stale or inconsistent with a completed local workflow.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def replace_available_plant_snapshot(
        self,
        *,
        organization_id: str,
        facility_id: str,
        jurisdiction_code: str,
        license_number: str,
        environment: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        env = str(environment or "").strip().casefold()
        jurisdiction = str(jurisdiction_code or "").strip().upper()
        license_value = str(license_number or "").strip()
        if env not in {"sandbox", "production"} or not jurisdiction or not license_value:
            raise ValueError("Fresh Metrc plant-tag reconciliation requires exact jurisdiction, environment, and facility license.")

        by_label = {label: dict(record) for record in records if isinstance(record, dict) and (label := _label(record))}
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id or not facility.active:
                raise ValueError("The active cultivation facility was not found in this organization.")

            existing = list(
                session.scalars(
                    select(MetrcTagInventory).where(
                        MetrcTagInventory.organization_id == organization_id,
                        MetrcTagInventory.facility_id == facility_id,
                        MetrcTagInventory.environment == env,
                        MetrcTagInventory.tag_type == "plant",
                    )
                )
            )
            existing_by_label = {row.label: row for row in existing}

            for row in existing:
                if row.status == "available" and row.label not in by_label:
                    row.status = "unavailable"
                    row.synced_at = now

            for label, record in by_label.items():
                row = existing_by_label.get(label)
                if row is None:
                    row = MetrcTagInventory(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        jurisdiction_code=jurisdiction,
                        license_number=license_value,
                        environment=env,
                        tag_type="plant",
                        label=label,
                        provider_id=_provider_id(record),
                        status="available",
                        synced_at=now,
                    )
                    session.add(row)
                    continue
                row.jurisdiction_code = jurisdiction
                row.license_number = license_value
                row.provider_id = _provider_id(record) or row.provider_id
                row.synced_at = now
                if row.status in {"available", "unavailable"}:
                    row.status = "available"

            session.flush()

        return {
            "available_count": len(by_label),
            "labels": sorted(by_label),
            "synced_at": now.isoformat(),
            "environment": env,
            "license_number": license_value,
        }
