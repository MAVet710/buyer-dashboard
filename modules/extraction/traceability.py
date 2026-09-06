"""Extraction-specific orchestration for the shared traceability transaction layer."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import InventoryLot
from modules.product_master.models import ProductExternalMapping
from modules.regulatory import require_metrc_write_contract
from modules.traceability.backoffice import TraceabilityBackofficeRepository

from .models import ExtractionRun, ExtractionRunInput, ExtractionRunOutput


class ExtractionTraceabilityService:
    """Queue extraction compliance work only after the write contract is promoted."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.traceability = TraceabilityBackofficeRepository(engine)

    def queue_output_package_creation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        output_id: str,
        new_tag: str,
        metrc_item_name: str,
        actor: str,
        location: str = "",
        note: str = "",
        is_finished_good: bool | None = None,
        expiration_date: date | None = None,
    ):
        new_tag = str(new_tag or "").strip()
        requested_item_name = str(metrc_item_name or "").strip()
        if not new_tag:
            raise ValueError("A new Metrc tag is required.")

        with self._session_factory() as session:
            run = session.get(ExtractionRun, run_id)
            output = session.get(ExtractionRunOutput, output_id)
            if (
                not run
                or run.organization_id != organization_id
                or run.facility_id != facility_id
                or not output
                or output.run_id != run.id
                or output.organization_id != organization_id
                or output.facility_id != facility_id
            ):
                raise ValueError("Extraction run/output was not found in the active facility.")
            if output.compliance_package_id and output.compliance_package_id != new_tag:
                raise ValueError("This extraction output is already linked to a different compliance package.")

            resolved_item_name = requested_item_name
            if not resolved_item_name and str(run.compliance_provider or "metrc").strip().casefold() == "metrc":
                mapping = session.scalar(
                    select(ProductExternalMapping)
                    .where(
                        ProductExternalMapping.organization_id == organization_id,
                        ProductExternalMapping.product_id == output.product_id,
                        ProductExternalMapping.system_name == "metrc",
                        ProductExternalMapping.active.is_(True),
                    )
                    .order_by(ProductExternalMapping.updated_at.desc())
                    .limit(1)
                )
                if mapping:
                    resolved_item_name = str(mapping.external_name or "").strip()
            if not resolved_item_name:
                raise ValueError(
                    "A Metrc Item name is required. Map the canonical output product to Metrc in Product Master, "
                    "or enter the exact Item name for this package creation."
                )

            inputs = list(
                session.scalars(
                    select(ExtractionRunInput)
                    .where(
                        ExtractionRunInput.run_id == run.id,
                        ExtractionRunInput.consumed_quantity > 0,
                    )
                    .order_by(ExtractionRunInput.created_at)
                )
            )
            ingredients: list[dict[str, Any]] = []
            for run_input in inputs:
                lot = session.get(InventoryLot, run_input.lot_id)
                package_label = str(lot.compliance_package_id if lot else "").strip()
                if not package_label:
                    raise ValueError(
                        "Every consumed source lot must have a compliance package ID before creating the output package."
                    )
                ingredients.append(
                    {
                        "package_label": package_label,
                        "quantity": float(run_input.consumed_quantity),
                        "unit": run_input.unit,
                    }
                )
            if not ingredients:
                raise ValueError("Consume at least one source inventory lot before creating a compliance output package.")

            payload = {
                "tag": new_tag,
                "item": resolved_item_name,
                "quantity": float(output.quantity),
                "unit": output.unit,
                "ingredients": ingredients,
                "location": str(location or "").strip(),
                "note": str(note or "").strip() or f"Buyer Dash extraction run {run.batch_number}",
                "production_batch_number": run.batch_number,
                "is_finished_good": is_finished_good,
                "actual_date": date.today().isoformat(),
                "expiration_date": expiration_date.isoformat() if expiration_date else "",
                "run_id": run.id,
                "output_id": output.id,
                "item_resolution": "manual" if requested_item_name else "product_master",
            }
            provider = str(run.compliance_provider or "metrc").strip().casefold()
            license_number = str(run.license_number or "").strip()
            jurisdiction = str(run.jurisdiction or "").strip().upper()

            if provider == "metrc":
                if not jurisdiction:
                    raise ValueError(
                        "Set the extraction run jurisdiction before preparing a Metrc output package."
                    )
                try:
                    require_metrc_write_contract(
                        operation_type="package_create",
                        jurisdiction=jurisdiction,
                        environment="sandbox",
                    )
                except ValueError as exc:
                    raise ValueError(
                        "Metrc output package creation is not enabled for this jurisdiction/environment yet. "
                        "No provider transaction was queued. Complete the sandbox write contract and readback proof first."
                    ) from exc

        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider=provider,
            operation_type="package_create",
            entity_type="extraction_output",
            entity_id=output_id,
            idempotency_key=f"extraction-output:{output_id}:package-create:{new_tag}",
            actor=actor,
            license_number=license_number,
            request_payload=payload,
            reason=f"Create state-system output package for extraction run {run_id}.",
        )
        if transaction.status == "requested":
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="validated",
                actor=actor,
                reason="Extraction output package request validated against durable run and source lots.",
                source="system",
            )
        if transaction.status == "validated":
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="queued",
                actor=actor,
                reason="Extraction output package request queued for provider worker.",
                source="system",
            )
        return transaction

    def process_output_package_creation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        credentials: Any,
        actor: str,
    ):
        """Deprecated legacy execution entry point; never submits provider work."""

        del organization_id, facility_id, transaction_id, credentials, actor
        raise RuntimeError(
            "Legacy extraction package-create execution is disabled. Use the canonical traceability dispatcher after the operation is promoted and sandbox-verified."
        )
