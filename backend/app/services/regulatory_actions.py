from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, InventoryTransaction, Product
from modules.doobie_actions.service import DoobieActionService
from modules.regulatory import list_metrc_write_contracts, require_metrc_write_contract


class RegulatoryActionProposalService:
    """Build deterministic human-approved regulatory proposals from durable data."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.actions = DoobieActionService(engine)

    @staticmethod
    def catalog(*, jurisdiction_code: str, environment: str) -> list[dict[str, Any]]:
        code = str(jurisdiction_code or "").strip().upper()
        env = str(environment or "").strip().casefold()
        return [
            contract.public(jurisdiction=code, environment=env)
            for contract in list_metrc_write_contracts(jurisdiction=code, environment=env)
        ]

    def package_finish_candidates(self, organization_id: str, facility_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return depleted tracked lots that are eligible for employee review.

        Candidate discovery is local/deterministic and does not call Metrc. The
        provider contract, trusted mapping, and exact package state are checked
        again when the proposal is built and submitted.
        """

        safe_limit = max(1, min(int(limit or 200), 500))
        with Session(self.engine) as session:
            lots = list(
                session.scalars(
                    select(InventoryLot)
                    .where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.compliance_package_id != "",
                    )
                    .order_by(InventoryLot.updated_at.desc())
                    .limit(safe_limit)
                )
            )
            product_ids = {lot.product_id for lot in lots}
            products = {
                row.id: row
                for row in session.scalars(
                    select(Product).where(
                        Product.organization_id == organization_id,
                        Product.id.in_(product_ids),
                    )
                )
            } if product_ids else {}
            balances = {
                lot.id: float(
                    session.scalar(
                        select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                            InventoryTransaction.organization_id == organization_id,
                            InventoryTransaction.facility_id == facility_id,
                            InventoryTransaction.lot_id == lot.id,
                        )
                    )
                    or 0.0
                )
                for lot in lots
            }

        output: list[dict[str, Any]] = []
        for lot in lots:
            balance = balances.get(lot.id, 0.0)
            if abs(balance) > 1e-6:
                continue
            product = products.get(lot.product_id)
            output.append({
                "lot_id": lot.id,
                "package_label": str(lot.compliance_package_id or "").strip(),
                "lot_code": lot.lot_code,
                "product_name": product.name if product else "",
                "product_sku": product.sku if product else "",
                "local_balance": balance,
                "location": lot.location_code,
                "status": lot.status,
                "ready": True,
            })
        return output

    def package_finish_proposal(
        self,
        *,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        actor: str,
        jurisdiction_code: str,
        environment: str,
        license_number: str,
        actual_date: str,
    ):
        environment = str(environment or "").strip().casefold()
        if environment != "sandbox":
            raise ValueError("New Doobie regulatory action workflows remain sandbox-only until authenticated provider validation is complete.")
        contract = require_metrc_write_contract(
            operation_type="package_finish",
            jurisdiction=jurisdiction_code,
            environment=environment,
        )
        try:
            finish_date = date.fromisoformat(str(actual_date or date.today().isoformat())[:10])
        except ValueError as exc:
            raise ValueError("Package finish requires a valid actual date.") from exc

        with Session(self.engine) as session:
            lot = session.get(InventoryLot, lot_id)
            if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Inventory lot was not found in the active facility.")
            package_label = str(lot.compliance_package_id or "").strip()
            if not package_label:
                raise ValueError("This inventory lot does not have a tracked Metrc package label.")
            balance = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.organization_id == organization_id,
                        InventoryTransaction.facility_id == facility_id,
                        InventoryTransaction.lot_id == lot.id,
                    )
                )
                or 0.0
            )

        if abs(balance) > 1e-6:
            raise ValueError(
                f"Package {package_label} still has {balance:g} local units on hand. Reconcile inventory before proposing a finish action."
            )

        payload = {
            "provider": "metrc",
            "operation_type": contract.operation_type,
            "entity_type": contract.entity_type,
            "entity_id": package_label,
            "license_number": str(license_number or "").strip(),
            "jurisdiction_code": str(jurisdiction_code or "").strip().upper(),
            "environment": environment,
            "request_payload": {"actual_date": finish_date.isoformat()},
            "reason": "Finish a depleted tracked package after employee review.",
        }
        preview = {
            "workflow": "Doobie Agent proposal → employee approval → explicit provider submit → reconciliation",
            "operation": "Finish Metrc package",
            "package_label": package_label,
            "local_balance": balance,
            "actual_date": finish_date.isoformat(),
            "jurisdiction_code": payload["jurisdiction_code"],
            "environment": payload["environment"],
            "license_number": payload["license_number"],
            "approval_required": True,
            "provider_submission_happens_on_approval": False,
            "verification_resource": contract.verification_resource,
        }
        return self.actions.propose(
            organization_id=organization_id,
            facility_id=facility_id,
            action_type="prepare_regulatory_action",
            title=f"Finish Metrc package {package_label}",
            rationale="The local package balance is zero. Doobie prepared the provider action for an authorized employee to review.",
            payload=payload,
            preview=preview,
            actor=actor,
            idempotency_key=f"regulatory:package-finish:{facility_id}:{package_label}:{finish_date.isoformat()}",
            risk_level="compliance",
            source_type="doobie_agent",
            source_id=lot_id,
        )


def action_recommendations(*, intelligence: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert deterministic regulatory findings into safe next-action guidance.

    This does not ask an LLM to author provider payloads. Recommendations only
    point to registered workflows and explicitly state when provider execution is
    not enabled.
    """

    catalog_by_operation = {str(row.get("operation_type") or ""): row for row in catalog}
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for finding in intelligence.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        domain = str(finding.get("domain") or "").casefold()
        code = str(finding.get("code") or "")
        entity_id = str(finding.get("entity_id") or "")
        if domain == "traceability":
            operation = "reconcile_traceability"
            message = "Open Queue & Reconciliation and compare the durable attempt to provider state before any repeat write."
        elif domain == "inventory":
            operation = "package_adjust"
            message = "Review the physical count and package evidence. A package adjustment can only be submitted after an employee supplies the exact adjustment reason and quantity."
        elif domain == "wholesale":
            operation = "transfer_template_create"
            message = "Use the governed manifest builder when the sales order, recipient license, allocations, and package labels are ready."
        elif domain == "manufacturing":
            operation = "processing_adjust"
            message = "Review the processing job. The endpoint is known, but automatic execution remains locked until the exact payload contract is verified."
        elif domain == "cultivation":
            operation = "plant_location_update"
            message = "Review the plant/tag/room evidence. Cultivation writes remain locked until their exact deterministic payload contracts are verified."
        else:
            continue
        key = (operation, entity_id or code)
        if key in seen:
            continue
        seen.add(key)
        contract = catalog_by_operation.get(operation, {})
        output.append({
            "operation_type": operation,
            "entity_id": entity_id,
            "finding_code": code,
            "severity": str(finding.get("severity") or "info"),
            "title": str(finding.get("title") or "Regulatory review"),
            "message": message,
            "provider_dispatch_enabled": bool(contract.get("dispatch_enabled")),
            "human_approval_required": True,
        })
    return output[:100]
