from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot
from modules.commercial.repository import CommercialRepository
from modules.doobie_actions.service import DoobieActionService


READY_ORDER_STATUSES = {"confirmed", "allocated", "partially_fulfilled"}


class ManifestDraftService:
    """Build a manifest-ready Metrc transfer-template draft from trusted commercial data.

    The service only creates an internal Doobie action proposal. It never submits
    to Metrc. Customer/license/package identity comes from the durable commercial
    and inventory records rather than model-provided free text.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.commercial = CommercialRepository(engine)
        self.actions = DoobieActionService(engine)

    def candidates(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        partners = {row.id: row for row in self.commercial.list_trade_partners(organization_id)}
        output: list[dict[str, Any]] = []
        for order in self.commercial.list_orders(organization_id, facility_id):
            if str(order.order_type or "").casefold() != "sales" or str(order.status or "").casefold() not in READY_ORDER_STATUSES:
                continue
            partner = partners.get(order.partner_id)
            allocations = self.commercial.list_allocations(organization_id, facility_id, order_id=order.id)
            lot_ids = {row.lot_id for row in allocations if str(row.status or "").casefold() in {"reserved", "partial"}}
            lots = self._lots(organization_id, facility_id, lot_ids)
            package_labels = sorted({str(row.compliance_package_id or "").strip() for row in lots.values() if str(row.compliance_package_id or "").strip()})
            output.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "customer": str(getattr(partner, "name", "") or ""),
                "customer_license": str(getattr(partner, "license_or_registration", "") or ""),
                "package_count": len(package_labels),
                "package_labels": package_labels,
                "ready": bool(partner and getattr(partner, "license_or_registration", "") and package_labels),
            })
        return output

    def build_proposal(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        actor: str,
        license_number: str,
        jurisdiction_code: str,
        environment: str,
        estimated_departure: str,
        estimated_arrival: str,
        planned_route: str,
        transfer_type_name: str,
        transporter_facility_license_number: str = "",
        driver_name: str = "",
        driver_license_number: str = "",
        driver_occupational_license_number: str = "",
        phone_number_for_questions: str = "",
        vehicle_license_plate_number: str = "",
        vehicle_make: str = "",
        vehicle_model: str = "",
    ):
        jurisdiction = str(jurisdiction_code or "").strip().upper()
        env = str(environment or "").strip().casefold()
        if jurisdiction != "MA" or env != "sandbox":
            raise ValueError("The first manifest write phase is restricted to the Massachusetts Metrc sandbox.")
        departure = _iso_datetime(estimated_departure, "estimated_departure")
        arrival = _iso_datetime(estimated_arrival, "estimated_arrival")
        if arrival <= departure:
            raise ValueError("Estimated arrival must be after estimated departure.")
        route = str(planned_route or "").strip()
        transfer_type = str(transfer_type_name or "").strip()
        if not route:
            raise ValueError("A planned route is required before Doobie can build the manifest draft.")
        if not transfer_type:
            raise ValueError("A Metrc transfer type is required before Doobie can build the manifest draft.")

        order = next((row for row in self.commercial.list_orders(organization_id, facility_id) if row.id == order_id), None)
        if order is None or str(order.order_type or "").casefold() != "sales":
            raise ValueError("The selected sales order was not found in the active facility.")
        if str(order.status or "").casefold() not in READY_ORDER_STATUSES:
            raise ValueError("Confirm and allocate the sales order before building a manifest draft.")
        partner = next((row for row in self.commercial.list_trade_partners(organization_id) if row.id == order.partner_id), None)
        recipient_license = str(getattr(partner, "license_or_registration", "") or "").strip()
        if not partner or not recipient_license:
            raise ValueError("The wholesale customer must have a license/registration before a manifest draft can be built.")

        lines = {row.id: row for row in self.commercial.list_order_lines(organization_id, order_id=order.id)}
        allocations = [
            row for row in self.commercial.list_allocations(organization_id, facility_id, order_id=order.id)
            if str(row.status or "").casefold() in {"reserved", "partial"}
        ]
        if not allocations:
            raise ValueError("Allocate package-backed inventory to the sales order before building a manifest draft.")
        lots = self._lots(organization_id, facility_id, {row.lot_id for row in allocations})

        packages: list[dict[str, Any]] = []
        package_preview: list[dict[str, Any]] = []
        seen: set[str] = set()
        for allocation in allocations:
            lot = lots.get(allocation.lot_id)
            line = lines.get(allocation.commercial_order_line_id)
            label = str(getattr(lot, "compliance_package_id", "") or "").strip()
            if not lot or not label:
                raise ValueError("Every allocated lot must have a Metrc package label before a manifest draft can be built.")
            if label in seen:
                continue
            seen.add(label)
            package: dict[str, Any] = {"PackageLabel": label}
            if line is not None:
                remaining = max(0.0, float(allocation.quantity or 0) - float(allocation.fulfilled_quantity or 0))
                wholesale_price = max(0.0, remaining * float(line.unit_price or 0))
                if wholesale_price:
                    package["WholesalePrice"] = round(wholesale_price, 2)
                package_preview.append({
                    "package_label": label,
                    "product": str(line.description or ""),
                    "allocated_quantity": remaining,
                    "unit": str(line.unit or ""),
                    "wholesale_value_usd": round(wholesale_price, 2),
                })
            packages.append(package)
        if not packages:
            raise ValueError("At least one Metrc package is required for a manifest draft.")

        destination = {
            "RecipientLicenseNumber": recipient_license,
            "TransferTypeName": transfer_type,
            "PlannedRoute": route,
            "EstimatedDepartureDateTime": departure.isoformat(),
            "EstimatedArrivalDateTime": arrival.isoformat(),
            "InvoiceNumber": str(order.external_reference or order.order_number or ""),
            "Packages": packages,
        }
        template: dict[str, Any] = {
            "Name": f"DL-{str(order.order_number or order.id).strip()}-{departure:%Y%m%d%H%M}",
            "Destinations": [destination],
        }
        optional = {
            "TransporterFacilityLicenseNumber": transporter_facility_license_number,
            "DriverName": driver_name,
            "DriverLicenseNumber": driver_license_number,
            "DriverOccupationalLicenseNumber": driver_occupational_license_number,
            "PhoneNumberForQuestions": phone_number_for_questions,
            "VehicleLicensePlateNumber": vehicle_license_plate_number,
            "VehicleMake": vehicle_make,
            "VehicleModel": vehicle_model,
        }
        for key, value in optional.items():
            text = str(value or "").strip()
            if text:
                template[key] = text

        preview = {
            "workflow": "Doobie Agent draft → employee approval → employee Metrc submission",
            "provider_object": "outgoing transfer template",
            "jurisdiction_code": jurisdiction,
            "environment": env,
            "facility_license": str(license_number or "").strip(),
            "sales_order": {"id": order.id, "order_number": order.order_number, "status": order.status},
            "customer": {"name": str(partner.name or ""), "license": recipient_license},
            "route": route,
            "estimated_departure": departure.isoformat(),
            "estimated_arrival": arrival.isoformat(),
            "packages": package_preview,
            "submission_note": "Approval does not submit to Metrc. An authorized employee must explicitly submit the approved draft.",
        }
        payload = {
            "provider": "metrc",
            "operation_type": "transfer_template_create",
            "entity_type": "outgoing_transfer_template",
            "entity_id": str(order.order_number or order.id),
            "license_number": str(license_number or "").strip(),
            "request_payload": {
                "commercial_order_id": order.id,
                "template": template,
            },
            "reason": f"Approved MA sandbox outgoing transfer-template draft for sales order {order.order_number}.",
        }
        return self.actions.propose(
            organization_id=organization_id,
            facility_id=facility_id,
            action_type="prepare_transfer_manifest",
            title=f"Manifest draft · {order.order_number}",
            rationale="Doobie assembled the recipient license and allocated Metrc package labels from the facility's trusted commercial records. Review logistics before approval and submission.",
            payload=payload,
            preview=preview,
            actor=actor,
            idempotency_key=f"manifest-draft:{organization_id}:{facility_id}:{order.id}:{departure.isoformat()}:{arrival.isoformat()}",
            financial_impact_usd=round(sum(float(row.get("wholesale_value_usd") or 0) for row in package_preview), 2),
            risk_level="compliance",
            source_type="doobie_agent",
            source_id=order.id,
        )

    def _lots(self, organization_id: str, facility_id: str, lot_ids: set[str]) -> dict[str, InventoryLot]:
        if not lot_ids:
            return {}
        with Session(self.engine) as session:
            rows = [session.get(InventoryLot, lot_id) for lot_id in lot_ids]
            return {
                row.id: row
                for row in rows
                if row is not None and row.organization_id == organization_id and row.facility_id == facility_id
            }


def _iso_datetime(value: str, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field.replace('_', ' ').title()} is required.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field.replace('_', ' ').title()} must be an ISO date/time.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field.replace('_', ' ').title()} must include a timezone offset.")
    return parsed
