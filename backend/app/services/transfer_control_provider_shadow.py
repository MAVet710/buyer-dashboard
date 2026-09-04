from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationSyncRecord
from backend.app.services.transfer_control import TransferControlService


TERMINAL_PROVIDER_STATUSES = {
    "accepted",
    "cancelled",
    "canceled",
    "completed",
    "delivered",
    "rejected",
    "voided",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _raw(row: IntegrationSyncRecord) -> dict[str, Any]:
    try:
        parsed = json.loads(row.raw_payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    nested = parsed.get("source")
    return nested if isinstance(nested, dict) else parsed


def _provider_status(source: dict[str, Any]) -> str:
    return _text(_first(source, "Status", "TransferStatus", "DeliveryStatus", "status") or "provider_synced")


def _direction(resource: str, source: dict[str, Any]) -> str:
    if resource == "incoming_transfers":
        return "incoming"
    if resource == "outgoing_transfers":
        return "outgoing"
    value = _text(_first(source, "Direction", "TransferDirection", "direction")).casefold()
    return "incoming" if value.startswith("in") else "outgoing" if value.startswith("out") else "unknown"


def _manifest(source: dict[str, Any]) -> str:
    return _text(_first(source, "ManifestNumber", "Manifest", "ManifestId", "manifest_number", "manifest"))


def _package_count(source: dict[str, Any]) -> int:
    for key in ("Packages", "packages", "PackageIds", "package_ids"):
        value = source.get(key)
        if isinstance(value, list):
            return len(value)
    try:
        return max(0, int(_first(source, "PackageCount", "package_count") or 0))
    except (TypeError, ValueError):
        return 0


def _is_open(status: str) -> bool:
    return status.strip().casefold().replace(" ", "_") not in TERMINAL_PROVIDER_STATUSES


class ProviderAwareTransferControlService(TransferControlService):
    """Blend last-synced provider transfer state into the durable transfer read model.

    This remains a read-only surface. Provider rows are virtual view rows backed by
    IntegrationSyncRecord; no ActionProposal, receiving preflight, manifest, order,
    or traceability mutation is fabricated merely because Metrc already has history.
    """

    def snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        snapshot = super().snapshot(organization_id, facility_id)
        provider_rows = self._provider_rows(organization_id, facility_id)
        provider_outgoing = [row for row in provider_rows if row["direction"] != "incoming"]
        provider_inbound = [row for row in provider_rows if row["direction"] == "incoming"]

        snapshot["outgoing"] = [self._as_outgoing(row) for row in provider_outgoing] + snapshot["outgoing"]
        snapshot["inbound"] = [self._as_inbound(row) for row in provider_inbound] + snapshot["inbound"]

        open_outgoing = sum(_is_open(row["status"]) for row in provider_outgoing)
        open_inbound = sum(_is_open(row["status"]) for row in provider_inbound)
        snapshot["metrics"]["outgoing_open"] += open_outgoing
        snapshot["metrics"]["inbound_open"] += open_inbound
        snapshot["metrics"]["provider_in_flight"] += open_outgoing + open_inbound
        snapshot["provider_synced"] = {
            "count": len(provider_rows),
            "open": open_outgoing + open_inbound,
            "source": "integration_sync_records",
            "network_request_made": False,
        }
        snapshot["policy"]["message"] = (
            "Durable DoobieLogic transfer state and the last successfully synced provider transfer state load without contacting Metrc. "
            "Provider-synced rows are read-only shadows; DoobieLogic never fabricates a manifest proposal or receiving event from an existing provider record."
        )
        return snapshot

    def _provider_rows(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        resources = ("transfers", "incoming_transfers", "outgoing_transfers", "rejected_transfers")
        with Session(self.engine) as session:
            records = list(
                session.scalars(
                    select(IntegrationSyncRecord)
                    .where(
                        IntegrationSyncRecord.organization_id == organization_id,
                        IntegrationSyncRecord.facility_id == facility_id,
                        IntegrationSyncRecord.provider.in_(("metrc", "metrc_sandbox")),
                        IntegrationSyncRecord.resource.in_(resources),
                        IntegrationSyncRecord.status == "accepted",
                    )
                    .order_by(IntegrationSyncRecord.received_at.desc())
                    .limit(1000)
                )
            )

        latest: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for record in records:
            source = _raw(record)
            external_id = _text(record.external_id or _first(source, "Id", "ID", "id"))
            if not external_id:
                continue
            key = (record.provider, record.resource, external_id.casefold())
            if key in seen:
                continue
            seen.add(key)
            status = _provider_status(source)
            latest.append(
                {
                    "provider": record.provider,
                    "resource": record.resource,
                    "external_id": external_id,
                    "direction": _direction(record.resource, source),
                    "status": status,
                    "manifest": _manifest(source),
                    "vendor": _text(_first(source, "ShipperFacilityName", "SenderFacilityName", "VendorName", "vendor")),
                    "vendor_license": _text(_first(source, "ShipperFacilityLicenseNumber", "SenderFacilityLicenseNumber", "VendorLicenseNumber", "vendor_license")),
                    "recipient": _text(_first(source, "RecipientFacilityName", "DestinationFacilityName", "recipient")),
                    "recipient_license": _text(_first(source, "RecipientFacilityLicenseNumber", "DestinationFacilityLicenseNumber", "recipient_license")),
                    "package_count": _package_count(source),
                    "departure": _text(_first(source, "EstimatedDepartureDateTime", "DepartureDateTime", "departure")),
                    "arrival": _text(_first(source, "EstimatedArrivalDateTime", "ArrivalDateTime", "arrival")),
                    "last_seen_at": record.received_at.isoformat() if record.received_at is not None else None,
                }
            )
        return latest

    @staticmethod
    def _as_outgoing(row: dict[str, Any]) -> dict[str, Any]:
        reference = row["manifest"] or row["external_id"]
        return {
            "proposal_id": f"provider-shadow:{row['provider']}:{row['external_id']}",
            "title": f"Metrc · {reference}",
            "stage": row["status"].strip().casefold().replace(" ", "_") or "provider_synced",
            "proposal_status": "provider_synced",
            "traceability_status": "provider_synced",
            "transaction_id": "",
            "external_reference": row["manifest"],
            "commercial_order_id": "",
            "order_number": row["manifest"],
            "customer": row["recipient"],
            "customer_license": row["recipient_license"],
            "package_count": row["package_count"],
            "departure": row["departure"],
            "arrival": row["arrival"],
            "route": "",
            "financial_impact_usd": 0.0,
            "created_at": row["last_seen_at"],
            "approved_at": None,
            "error_message": "",
            "mismatch_reason": "",
            "provider_synced": True,
            "provider": row["provider"],
        }

    @staticmethod
    def _as_inbound(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "preflight_id": f"provider-shadow:{row['provider']}:{row['external_id']}",
            "transfer_id": row["external_id"],
            "operation": "provider_sync",
            "status": row["status"].strip().casefold().replace(" ", "_") or "provider_synced",
            "provider": row["provider"],
            "jurisdiction": "",
            "environment": "sandbox" if row["provider"] == "metrc_sandbox" else "production",
            "manifest": row["manifest"],
            "vendor": row["vendor"],
            "vendor_license": row["vendor_license"],
            "package_count": row["package_count"],
            "expires_at": None,
            "consumed_at": None,
            "received_count": 0,
            "reason": "Provider-synced transfer. Prepare a controlled receiving preflight before posting local inventory.",
            "provider_synced": True,
        }
