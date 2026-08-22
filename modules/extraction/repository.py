"""Transactional repository for durable extraction operations.

The extraction module never owns a parallel inventory balance. Inputs reserve and
consume ``coman_inventory_lots`` and outputs are created back into the same shared
append-only inventory ledger.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import (
    AuditEvent,
    Customer,
    Facility,
    FacilityMachine,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    OrderLotAllocation,
    Product,
    ProductionOrder,
    utc_now,
)
from modules.traceability.models import TraceabilityTransaction

from .models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionStageEvent,
    ExtractionTollJob,
)
from .workflows import get_extraction_workflow


OPEN_RUN_STATUSES = {"planned", "queued", "active", "hold", "qa"}
INPUT_OPEN_STATUSES = {"reserved", "partial"}
OUTPUT_ACTIVE_STATUSES = {"wip", "quarantine", "released"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


class ExtractionRepository:
    """Tenant-safe source of truth for Extraction ERP records."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------
    def create_run(
        self,
        *,
        organization_id: str,
        facility_id: str,
        batch_number: str,
        method: str,
        workflow_key: str,
        actor: str,
        product_family: str = "",
        strain: str = "",
        operator: str = "",
        compliance_provider: str = "metrc",
        license_number: str = "",
        production_order_id: str | None = None,
        customer_id: str | None = None,
        machine_id: str | None = None,
        toll_processing: bool = False,
        notes: str = "",
        run_date: date | None = None,
        jurisdiction: str = "",
        facility_license_name: str = "",
        client_name_snapshot: str = "",
        manual_batch_id_internal: str | None = None,
        input_material_type: str = "",
        manual_input_weight_g: float = 0.0,
        intermediate_output_g: float = 0.0,
        manual_finished_output_g: float = 0.0,
        residual_loss_g: float = 0.0,
        machine_line: str = "",
        metrc_package_id_input: str = "",
        metrc_package_id_output: str = "",
        metrc_manifest_or_transfer_id: str = "",
        manual_coa_status: str = "pending",
        manual_qa_hold: bool = False,
        processing_fee_usd: float = 0.0,
        estimated_revenue_usd: float = 0.0,
        manual_cogs_usd: float = 0.0,
        initial_status: str = "queued",
        initial_release_status: str = "blocked",
    ) -> ExtractionRun:
        workflow = get_extraction_workflow(workflow_key)
        clean_batch = _clean(batch_number)
        clean_actor = _clean(actor)
        if not clean_batch or not clean_actor:
            raise ValueError("Batch number and actor are required.")
        if _clean(method).casefold() != workflow.method.casefold():
            raise ValueError("Run method must match the selected workflow template.")
        clean_status = _clean(initial_status).casefold()
        clean_release_status = _clean(initial_release_status).casefold()
        if clean_status not in {"planned", "queued", "active", "hold", "qa", "complete", "cancelled", "failed"}:
            raise ValueError("Unsupported initial run status.")
        if clean_release_status not in {"blocked", "pending", "approved", "rejected"}:
            raise ValueError("Unsupported initial release status.")

        run = ExtractionRun(
            organization_id=organization_id,
            facility_id=facility_id,
            production_order_id=production_order_id,
            customer_id=customer_id,
            machine_id=machine_id,
            batch_number=clean_batch,
            method=workflow.method,
            workflow_key=workflow.key,
            current_stage_key=workflow.first_stage,
            status=clean_status,
            release_status=clean_release_status,
            product_family=_clean(product_family),
            strain=_clean(strain),
            toll_processing=bool(toll_processing),
            compliance_provider=_clean(compliance_provider).casefold() or "metrc",
            license_number=_clean(license_number),
            operator=_clean(operator),
            notes=_clean(notes),
            run_date=run_date,
            jurisdiction=_clean(jurisdiction),
            facility_license_name=_clean(facility_license_name),
            client_name_snapshot=_clean(client_name_snapshot),
            manual_batch_id_internal=None if manual_batch_id_internal is None else _clean(manual_batch_id_internal),
            input_material_type=_clean(input_material_type),
            manual_input_weight_g=max(0.0, float(manual_input_weight_g)),
            intermediate_output_g=max(0.0, float(intermediate_output_g)),
            manual_finished_output_g=max(0.0, float(manual_finished_output_g)),
            residual_loss_g=max(0.0, float(residual_loss_g)),
            machine_line=_clean(machine_line),
            metrc_package_id_input=_clean(metrc_package_id_input),
            metrc_package_id_output=_clean(metrc_package_id_output),
            metrc_manifest_or_transfer_id=_clean(metrc_manifest_or_transfer_id),
            manual_coa_status=_clean(manual_coa_status).casefold() or "pending",
            manual_qa_hold=bool(manual_qa_hold),
            processing_fee_usd=max(0.0, float(processing_fee_usd)),
            estimated_revenue_usd=max(0.0, float(estimated_revenue_usd)),
            manual_cogs_usd=max(0.0, float(manual_cogs_usd)),
            created_by=clean_actor,
            updated_by=clean_actor,
        )
        with self._session_factory.begin() as session:
            self._require_scope(session, organization_id, facility_id)
            if production_order_id:
                order = session.get(ProductionOrder, production_order_id)
                if not order or order.organization_id != organization_id or order.facility_id != facility_id:
                    raise ValueError("Production order was not found in the active facility.")
            if customer_id:
                customer = session.get(Customer, customer_id)
                if not customer or customer.organization_id != organization_id:
                    raise ValueError("Customer was not found in the active organization.")
            if machine_id:
                machine = session.get(FacilityMachine, machine_id)
                if not machine or machine.organization_id != organization_id or machine.facility_id != facility_id:
                    raise ValueError("Machine was not found in the active facility.")
            session.add(run)
            session.flush()
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_run",
                run.id,
                "created",
                clean_actor,
                {"batch_number": clean_batch, "workflow_key": workflow.key, "method": workflow.method},
            )
        return run

    def get_run(self, organization_id: str, facility_id: str, run_id: str) -> ExtractionRun:
        with self._session_factory() as session:
            return self._require_run(session, organization_id, facility_id, run_id)

    def find_run_by_batch(
        self,
        organization_id: str,
        facility_id: str,
        batch_number: str,
    ) -> ExtractionRun | None:
        with self._session_factory() as session:
            return session.scalar(
                select(ExtractionRun).where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                    func.lower(ExtractionRun.batch_number) == _clean(batch_number).casefold(),
                )
            )

    def list_runs(
        self,
        organization_id: str,
        facility_id: str,
        *,
        include_closed: bool = True,
        limit: int = 500,
    ) -> list[ExtractionRun]:
        with self._session_factory() as session:
            statement = select(ExtractionRun).where(
                ExtractionRun.organization_id == organization_id,
                ExtractionRun.facility_id == facility_id,
            )
            if not include_closed:
                statement = statement.where(ExtractionRun.status.in_(tuple(OPEN_RUN_STATUSES)))
            statement = statement.order_by(ExtractionRun.updated_at.desc()).limit(max(1, min(int(limit), 2000)))
            return list(session.scalars(statement))

    def update_run_notes(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        notes: str,
        actor: str,
    ) -> ExtractionRun:
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            run.notes = _clean(notes)
            run.updated_by = _clean(actor)
            self._audit(session, organization_id, facility_id, "extraction_run", run.id, "notes_updated", actor, {})
            session.flush()
            return run

    # ------------------------------------------------------------------
    # Shared inventory reservation / consumption
    # ------------------------------------------------------------------
    def lot_balance(self, organization_id: str, facility_id: str, lot_id: str) -> float:
        with self._session_factory() as session:
            self._require_lot(session, organization_id, facility_id, lot_id)
            return self._lot_balance(session, lot_id)

    def lot_reserved_quantity(
        self,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        *,
        exclude_extraction_input_id: str | None = None,
    ) -> float:
        with self._session_factory() as session:
            self._require_lot(session, organization_id, facility_id, lot_id)
            return self._lot_reserved_quantity(
                session,
                lot_id,
                exclude_extraction_input_id=exclude_extraction_input_id,
            )

    def lot_available_quantity(self, organization_id: str, facility_id: str, lot_id: str) -> float:
        with self._session_factory() as session:
            self._require_lot(session, organization_id, facility_id, lot_id)
            return max(
                0.0,
                self._lot_balance(session, lot_id) - self._lot_reserved_quantity(session, lot_id),
            )

    def list_available_lots(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            lots = list(
                session.scalars(
                    select(InventoryLot)
                    .where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.status.in_(("available", "reserved")),
                    )
                    .order_by(InventoryLot.received_at, InventoryLot.lot_code)
                )
            )
            rows: list[dict[str, Any]] = []
            for lot in lots:
                product = session.get(Product, lot.product_id)
                balance = self._lot_balance(session, lot.id)
                reserved = self._lot_reserved_quantity(session, lot.id)
                available = max(0.0, balance - reserved)
                if available <= 1e-9:
                    continue
                rows.append(
                    {
                        "lot_id": lot.id,
                        "lot_code": lot.lot_code,
                        "compliance_package_id": lot.compliance_package_id,
                        "product_id": lot.product_id,
                        "product_name": product.name if product else "",
                        "sku": product.sku if product else "",
                        "unit": product.base_unit if product else "unit",
                        "unit_cost": float(product.unit_cost if product else 0.0),
                        "balance": balance,
                        "reserved": reserved,
                        "available": available,
                        "location": lot.location_code,
                        "status": lot.status,
                    }
                )
            return rows

    def reserve_input(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        lot_id: str,
        quantity: float,
        actor: str,
        role: str = "primary_input",
        unit: str | None = None,
        source_reference: str = "",
    ) -> ExtractionRunInput:
        reserve_qty = float(quantity)
        if reserve_qty <= 0:
            raise ValueError("Reserved extraction input quantity must be positive.")
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            self._require_open_run(run)
            lot = self._require_lot(session, organization_id, facility_id, lot_id)
            if lot.status not in {"available", "reserved"}:
                raise ValueError("Only released/available inventory can be reserved for extraction.")
            product = session.get(Product, lot.product_id)
            if not product or product.organization_id != organization_id:
                raise ValueError("Inventory product was not found in the active organization.")
            input_unit = _clean(unit) or product.base_unit
            if input_unit.casefold() != product.base_unit.casefold():
                raise ValueError("Extraction reservations must use the inventory lot base unit.")

            existing = session.scalar(
                select(ExtractionRunInput).where(
                    ExtractionRunInput.run_id == run_id,
                    ExtractionRunInput.lot_id == lot_id,
                    ExtractionRunInput.role == _clean(role),
                )
            )
            current_reserved = float(existing.reserved_quantity if existing else 0.0)
            available = max(
                0.0,
                self._lot_balance(session, lot_id)
                - self._lot_reserved_quantity(
                    session,
                    lot_id,
                    exclude_extraction_input_id=existing.id if existing else None,
                ),
            )
            if reserve_qty > available + 1e-9:
                raise ValueError(
                    f"Extraction reservation exceeds available lot inventory ({available:,.3f} {input_unit})."
                )

            if existing:
                if existing.status == "consumed":
                    raise ValueError("A fully consumed input line cannot be re-reserved.")
                existing.planned_quantity = max(float(existing.planned_quantity), reserve_qty)
                existing.reserved_quantity = reserve_qty
                existing.status = "partial" if existing.consumed_quantity > 0 else "reserved"
                existing.source_reference = _clean(source_reference) or existing.source_reference
                record = existing
            else:
                record = ExtractionRunInput(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    lot_id=lot.id,
                    role=_clean(role) or "primary_input",
                    planned_quantity=reserve_qty,
                    reserved_quantity=reserve_qty,
                    consumed_quantity=0.0,
                    unit=input_unit,
                    unit_cost_snapshot=max(0.0, float(product.unit_cost or 0.0)),
                    input_cost_usd=0.0,
                    source_reference=_clean(source_reference),
                    status="reserved",
                    reserved_by=_clean(actor),
                )
                session.add(record)
                session.flush()
            if lot.status == "available":
                lot.status = "reserved"
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_run_input",
                record.id,
                "reserved",
                actor,
                {"run_id": run.id, "lot_id": lot.id, "quantity": reserve_qty, "unit": input_unit},
            )
            session.flush()
            return record

    def consume_input(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_input_id: str,
        quantity: float,
        actor: str,
        reason: str = "Extraction consumption",
    ) -> ExtractionRunInput:
        consume_qty = float(quantity)
        if consume_qty <= 0:
            raise ValueError("Consumed extraction input quantity must be positive.")
        with self._session_factory.begin() as session:
            record = self._require_input(session, organization_id, facility_id, run_input_id)
            run = self._require_run(session, organization_id, facility_id, record.run_id)
            self._require_open_run(run)
            remaining_reserved = float(record.reserved_quantity) - float(record.consumed_quantity)
            if consume_qty > remaining_reserved + 1e-9:
                raise ValueError("Consumed quantity exceeds the remaining reserved extraction input.")
            balance = self._lot_balance(session, record.lot_id)
            if consume_qty > balance + 1e-9:
                raise ValueError("Inventory changed and no longer contains enough material to consume this reservation.")

            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=record.lot_id,
                    transaction_type="production_consume",
                    quantity_delta=-consume_qty,
                    unit=record.unit,
                    production_order_id=run.production_order_id,
                    reason=_clean(reason),
                    reference=f"extraction:{run.id}:{record.id}",
                    actor=_clean(actor),
                )
            )
            amount = consume_qty * max(0.0, float(record.unit_cost_snapshot or 0.0))
            record.consumed_quantity = float(record.consumed_quantity) + consume_qty
            record.input_cost_usd = float(record.input_cost_usd) + amount
            record.status = (
                "consumed"
                if record.consumed_quantity >= record.reserved_quantity - 1e-9
                else "partial"
            )
            session.add(
                ExtractionCostEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    category="material",
                    amount_usd=amount,
                    quantity=consume_qty,
                    unit=record.unit,
                    unit_rate_usd=record.unit_cost_snapshot,
                    source_type="inventory_lot",
                    source_id=record.lot_id,
                    notes=f"Consumed source lot via extraction input {record.id}",
                    actor=_clean(actor),
                )
            )
            if run.started_at is None:
                run.started_at = utc_now()
            if run.status in {"planned", "queued"}:
                run.status = "active"
            run.updated_by = _clean(actor)
            self._refresh_lot_status(session, record.lot_id)
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_run_input",
                record.id,
                "consumed",
                actor,
                {"quantity": consume_qty, "amount_usd": amount},
            )
            session.flush()
            return record

    def release_input_reservation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_input_id: str,
        actor: str,
    ) -> ExtractionRunInput:
        with self._session_factory.begin() as session:
            record = self._require_input(session, organization_id, facility_id, run_input_id)
            if record.status == "consumed":
                return record
            record.reserved_quantity = float(record.consumed_quantity)
            record.status = "consumed" if record.consumed_quantity > 0 else "released"
            self._refresh_lot_status(session, record.lot_id)
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_run_input",
                record.id,
                "reservation_released",
                actor,
                {},
            )
            session.flush()
            return record

    def list_run_inputs(self, organization_id: str, facility_id: str, run_id: str) -> list[ExtractionRunInput]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionRunInput)
                    .where(ExtractionRunInput.run_id == run_id)
                    .order_by(ExtractionRunInput.created_at)
                )
            )

    # ------------------------------------------------------------------
    # Process events / mass balance
    # ------------------------------------------------------------------
    def record_stage_event(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        stage_key: str,
        event_type: str,
        actor: str,
        input_weight_g: float | None = None,
        output_weight_g: float | None = None,
        loss_weight_g: float | None = None,
        loss_reason: str = "",
        operator: str = "",
        machine_id: str | None = None,
        notes: str = "",
    ) -> ExtractionStageEvent:
        event_type = _clean(event_type).casefold()
        if event_type not in {"started", "completed", "measurement", "note", "deviation", "hold", "released"}:
            raise ValueError("Unsupported extraction stage event type.")
        workflow_stage = _clean(stage_key).casefold()
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            self._require_open_run(run)
            workflow = get_extraction_workflow(run.workflow_key)
            if not workflow.has_stage(workflow_stage):
                raise ValueError("Stage is not part of this extraction workflow template.")
            if machine_id:
                machine = session.get(FacilityMachine, machine_id)
                if not machine or machine.organization_id != organization_id or machine.facility_id != facility_id:
                    raise ValueError("Machine was not found in the active facility.")

            in_weight = None if input_weight_g is None else float(input_weight_g)
            out_weight = None if output_weight_g is None else float(output_weight_g)
            if in_weight is not None and in_weight < 0:
                raise ValueError("Stage input weight cannot be negative.")
            if out_weight is not None and out_weight < 0:
                raise ValueError("Stage output weight cannot be negative.")
            if loss_weight_g is None and in_weight is not None and out_weight is not None:
                loss = max(0.0, in_weight - out_weight)
            else:
                loss = None if loss_weight_g is None else float(loss_weight_g)
            if loss is not None and loss < 0:
                raise ValueError("Stage loss cannot be negative.")

            event = ExtractionStageEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                stage_key=workflow_stage,
                event_type=event_type,
                input_weight_g=in_weight,
                output_weight_g=out_weight,
                loss_weight_g=loss,
                loss_reason=_clean(loss_reason),
                operator=_clean(operator) or run.operator,
                machine_id=machine_id or run.machine_id,
                notes=_clean(notes),
                occurred_at=utc_now(),
            )
            session.add(event)
            if event_type == "hold":
                run.status = "hold"
                run.release_status = "blocked"
            elif event_type == "released" and run.status == "hold":
                run.status = "active"
            elif event_type in {"started", "measurement", "completed"}:
                run.status = "active" if run.status in {"planned", "queued"} else run.status
                run.current_stage_key = workflow_stage
                if run.started_at is None:
                    run.started_at = utc_now()
                if event_type == "completed":
                    next_stage = workflow.next_stage(workflow_stage)
                    if next_stage:
                        run.current_stage_key = next_stage
                        if next_stage == "qa":
                            run.status = "qa"
                            run.release_status = "pending"
            run.updated_by = _clean(actor)
            session.flush()
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_stage_event",
                event.id,
                event_type,
                actor,
                {"run_id": run.id, "stage_key": workflow_stage, "output_weight_g": out_weight, "loss_weight_g": loss},
            )
            session.flush()
            return event

    def list_stage_events(self, organization_id: str, facility_id: str, run_id: str) -> list[ExtractionStageEvent]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionStageEvent)
                    .where(ExtractionStageEvent.run_id == run_id)
                    .order_by(ExtractionStageEvent.occurred_at, ExtractionStageEvent.id)
                )
            )

    def mass_balance(self, organization_id: str, facility_id: str, run_id: str) -> dict[str, float]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            consumed = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionRunInput.consumed_quantity), 0.0)).where(
                        ExtractionRunInput.run_id == run_id
                    )
                )
                or 0.0
            )
            output = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionRunOutput.quantity), 0.0)).where(
                        ExtractionRunOutput.run_id == run_id,
                        ExtractionRunOutput.status != "destroyed",
                    )
                )
                or 0.0
            )
            measured_loss = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionStageEvent.loss_weight_g), 0.0)).where(
                        ExtractionStageEvent.run_id == run_id,
                        ExtractionStageEvent.loss_weight_g.is_not(None),
                    )
                )
                or 0.0
            )
            residual = max(0.0, consumed - output)
            yield_pct = (output / consumed * 100.0) if consumed > 0 else 0.0
            return {
                "consumed_input": consumed,
                "recorded_output": output,
                "measured_stage_loss": measured_loss,
                "unaccounted_balance": residual,
                "yield_pct": yield_pct,
            }

    # ------------------------------------------------------------------
    # Outputs / unified inventory
    # ------------------------------------------------------------------
    def create_output(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        product_id: str,
        lot_code: str,
        quantity: float,
        actor: str,
        output_label: str = "",
        unit: str | None = None,
        compliance_package_id: str = "",
        location_code: str = "WIP-EXTRACTION",
        notes: str = "",
    ) -> ExtractionRunOutput:
        qty = float(quantity)
        if qty <= 0:
            raise ValueError("Extraction output quantity must be positive.")
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            self._require_open_run(run)
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id:
                raise ValueError("Output product was not found in the active organization.")
            output_unit = _clean(unit) or product.base_unit
            if output_unit.casefold() != product.base_unit.casefold():
                raise ValueError("Extraction output must use the product base unit.")

            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product.id,
                lot_code=_clean(lot_code),
                compliance_package_id=_clean(compliance_package_id),
                location_code=_clean(location_code).upper() or "WIP-EXTRACTION",
                status="quarantine",
                received_at=utc_now(),
                notes=f"Extraction output from {run.batch_number}",
            )
            session.add(lot)
            session.flush()
            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=lot.id,
                    transaction_type="production_output",
                    quantity_delta=qty,
                    unit=output_unit,
                    production_order_id=run.production_order_id,
                    reason="Extraction run output",
                    reference=f"extraction:{run.id}",
                    actor=_clean(actor),
                )
            )
            position = int(
                session.scalar(
                    select(func.coalesce(func.max(ExtractionRunOutput.position), 0)).where(
                        ExtractionRunOutput.run_id == run.id
                    )
                )
                or 0
            ) + 1
            output = ExtractionRunOutput(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                product_id=product.id,
                lot_id=lot.id,
                position=position,
                output_label=_clean(output_label) or product.name,
                quantity=qty,
                unit=output_unit,
                status="quarantine",
                coa_status="not_submitted",
                compliance_package_id=_clean(compliance_package_id),
                output_cost_usd=0.0,
                notes=_clean(notes),
                created_by=_clean(actor),
            )
            session.add(output)
            if run.current_stage_key != "qa":
                run.current_stage_key = "qa"
            run.status = "qa"
            run.release_status = "pending"
            run.updated_by = _clean(actor)
            session.flush()
            self._allocate_output_cogs(session, run.id)
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_run_output",
                output.id,
                "created",
                actor,
                {"run_id": run.id, "lot_id": lot.id, "quantity": qty, "unit": output_unit},
            )
            session.flush()
            return output

    def list_outputs(self, organization_id: str, facility_id: str, run_id: str) -> list[ExtractionRunOutput]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionRunOutput)
                    .where(ExtractionRunOutput.run_id == run_id)
                    .order_by(ExtractionRunOutput.position)
                )
            )

    # ------------------------------------------------------------------
    # Cost / COGS
    # ------------------------------------------------------------------
    def add_cost_event(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        category: str,
        amount_usd: float,
        actor: str,
        quantity: float | None = None,
        unit: str = "",
        unit_rate_usd: float | None = None,
        source_type: str = "manual",
        source_id: str = "",
        notes: str = "",
    ) -> ExtractionCostEvent:
        category = _clean(category).casefold()
        if category not in {"material", "labor", "packaging", "processing", "overhead", "waste", "other"}:
            raise ValueError("Unsupported extraction cost category.")
        amount = float(amount_usd)
        if amount < 0:
            raise ValueError("Extraction cost cannot be negative.")
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            record = ExtractionCostEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                category=category,
                amount_usd=amount,
                quantity=None if quantity is None else float(quantity),
                unit=_clean(unit),
                unit_rate_usd=None if unit_rate_usd is None else float(unit_rate_usd),
                source_type=_clean(source_type) or "manual",
                source_id=_clean(source_id),
                notes=_clean(notes),
                actor=_clean(actor),
                occurred_at=utc_now(),
            )
            session.add(record)
            session.flush()
            self._allocate_output_cogs(session, run.id)
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_cost_event",
                record.id,
                "created",
                actor,
                {"run_id": run.id, "category": category, "amount_usd": amount},
            )
            return record

    def list_cost_events(self, organization_id: str, facility_id: str, run_id: str) -> list[ExtractionCostEvent]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionCostEvent)
                    .where(ExtractionCostEvent.run_id == run_id)
                    .order_by(ExtractionCostEvent.occurred_at, ExtractionCostEvent.id)
                )
            )

    def cogs_summary(self, organization_id: str, facility_id: str, run_id: str) -> dict[str, float]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            rows = session.execute(
                select(
                    ExtractionCostEvent.category,
                    func.coalesce(func.sum(ExtractionCostEvent.amount_usd), 0.0),
                )
                .where(ExtractionCostEvent.run_id == run_id)
                .group_by(ExtractionCostEvent.category)
            ).all()
            summary = {category: 0.0 for category in ("material", "labor", "packaging", "processing", "overhead", "waste", "other")}
            for category, amount in rows:
                summary[str(category)] = float(amount or 0.0)
            summary["total"] = float(sum(summary.values()))
            output_qty = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionRunOutput.quantity), 0.0)).where(
                        ExtractionRunOutput.run_id == run_id,
                        ExtractionRunOutput.status.in_(tuple(OUTPUT_ACTIVE_STATUSES)),
                    )
                )
                or 0.0
            )
            summary["cost_per_output_unit"] = summary["total"] / output_qty if output_qty > 0 else 0.0
            return summary

    # ------------------------------------------------------------------
    # QA / release gate
    # ------------------------------------------------------------------
    def record_qa_event(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        event_type: str,
        result: str,
        actor: str,
        output_id: str | None = None,
        coa_reference: str = "",
        deviation_code: str = "",
        notes: str = "",
    ) -> ExtractionQAEvent:
        event_type = _clean(event_type).casefold()
        result = _clean(result).casefold()
        valid_events = {"sample_submitted", "coa_attached", "hold", "release", "failure", "retest", "remediation", "deviation"}
        if event_type not in valid_events:
            raise ValueError("Unsupported extraction QA event type.")
        if result not in {"pending", "passed", "failed", "not_applicable"}:
            raise ValueError("Unsupported extraction QA result.")
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            output = None
            if output_id:
                output = session.get(ExtractionRunOutput, output_id)
                if not output or output.run_id != run.id or output.organization_id != organization_id:
                    raise ValueError("Extraction output was not found on this run.")

            if event_type == "release":
                if result != "passed":
                    raise ValueError("A QA release must carry a passed result.")
                outputs = list(
                    session.scalars(
                        select(ExtractionRunOutput).where(
                            ExtractionRunOutput.run_id == run.id,
                            ExtractionRunOutput.status.in_(("wip", "quarantine")),
                        )
                    )
                )
                if not outputs:
                    raise ValueError("A run cannot be released before an output exists.")
                not_passed = [item for item in outputs if item.coa_status != "passed"]
                if not_passed:
                    raise ValueError("Every releasable output must have a passed COA before run release.")

            event = ExtractionQAEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                output_id=output.id if output else None,
                event_type=event_type,
                result=result,
                coa_reference=_clean(coa_reference),
                deviation_code=_clean(deviation_code),
                notes=_clean(notes),
                actor=_clean(actor),
                occurred_at=utc_now(),
            )
            session.add(event)

            if output and event_type in {"sample_submitted", "coa_attached", "failure", "retest"}:
                if result == "passed":
                    output.coa_status = "passed"
                elif result == "failed":
                    output.coa_status = "failed"
                else:
                    output.coa_status = "pending"
            if event_type in {"hold", "failure"} or result == "failed":
                run.status = "hold"
                run.release_status = "rejected" if result == "failed" else "blocked"
            elif event_type in {"sample_submitted", "coa_attached", "retest", "remediation"}:
                run.status = "qa"
                run.release_status = "pending"
            elif event_type == "release":
                outputs = list(session.scalars(select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == run.id)))
                for item in outputs:
                    if item.status in {"wip", "quarantine"}:
                        item.status = "released"
                    if item.lot_id:
                        lot = session.get(InventoryLot, item.lot_id)
                        if lot:
                            lot.status = "available"
                run.status = "complete"
                run.release_status = "approved"
                run.current_stage_key = "release"
                run.completed_at = utc_now()
            run.updated_by = _clean(actor)
            session.flush()
            self._audit(
                session,
                organization_id,
                facility_id,
                "extraction_qa_event",
                event.id,
                event_type,
                actor,
                {"run_id": run.id, "result": result, "output_id": output.id if output else ""},
            )
            return event

    def list_qa_events(self, organization_id: str, facility_id: str, run_id: str) -> list[ExtractionQAEvent]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionQAEvent)
                    .where(ExtractionQAEvent.run_id == run_id)
                    .order_by(ExtractionQAEvent.occurred_at, ExtractionQAEvent.id)
                )
            )

    # ------------------------------------------------------------------
    # Toll processing
    # ------------------------------------------------------------------
    def upsert_toll_job(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        customer_id: str,
        actor: str,
        promised_completion_at: datetime | None = None,
        processing_fee_usd: float = 0.0,
        invoice_status: str = "draft",
        payment_status: str = "pending",
        external_reference: str = "",
        notes: str = "",
        jurisdiction: str = "",
        client_license_snapshot: str = "",
        material_received_at: datetime | None = None,
        input_weight_g: float = 0.0,
        expected_output_g: float = 0.0,
        actual_output_g: float = 0.0,
        coa_status: str = "pending",
        job_status: str = "queued",
    ) -> ExtractionTollJob:
        if float(processing_fee_usd) < 0:
            raise ValueError("Processing fee cannot be negative.")
        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            customer = session.get(Customer, customer_id)
            if not customer or customer.organization_id != organization_id:
                raise ValueError("Customer was not found in the active organization.")
            record = session.scalar(select(ExtractionTollJob).where(ExtractionTollJob.run_id == run.id))
            if record is None:
                record = ExtractionTollJob(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    customer_id=customer.id,
                    promised_completion_at=promised_completion_at,
                    processing_fee_usd=float(processing_fee_usd),
                    invoice_status=_clean(invoice_status).casefold(),
                    payment_status=_clean(payment_status).casefold(),
                    external_reference=_clean(external_reference),
                    notes=_clean(notes),
                    jurisdiction=_clean(jurisdiction),
                    client_license_snapshot=_clean(client_license_snapshot),
                    material_received_at=material_received_at,
                    input_weight_g=max(0.0, float(input_weight_g)),
                    expected_output_g=max(0.0, float(expected_output_g)),
                    actual_output_g=max(0.0, float(actual_output_g)),
                    coa_status=_clean(coa_status).casefold() or "pending",
                    job_status=_clean(job_status).casefold() or "queued",
                    created_by=_clean(actor),
                )
                session.add(record)
            else:
                record.customer_id = customer.id
                record.promised_completion_at = promised_completion_at
                record.processing_fee_usd = float(processing_fee_usd)
                record.invoice_status = _clean(invoice_status).casefold()
                record.payment_status = _clean(payment_status).casefold()
                record.external_reference = _clean(external_reference)
                record.notes = _clean(notes)
                record.jurisdiction = _clean(jurisdiction)
                record.client_license_snapshot = _clean(client_license_snapshot)
                record.material_received_at = material_received_at
                record.input_weight_g = max(0.0, float(input_weight_g))
                record.expected_output_g = max(0.0, float(expected_output_g))
                record.actual_output_g = max(0.0, float(actual_output_g))
                record.coa_status = _clean(coa_status).casefold() or "pending"
                record.job_status = _clean(job_status).casefold() or "queued"
            run.customer_id = customer.id
            run.toll_processing = True
            run.updated_by = _clean(actor)
            session.flush()
            self._audit(session, organization_id, facility_id, "extraction_toll_job", record.id, "upserted", actor, {"run_id": run.id})
            return record

    def get_toll_job(self, organization_id: str, facility_id: str, run_id: str) -> ExtractionTollJob | None:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return session.scalar(
                select(ExtractionTollJob).where(
                    ExtractionTollJob.organization_id == organization_id,
                    ExtractionTollJob.facility_id == facility_id,
                    ExtractionTollJob.run_id == run_id,
                )
            )

    # ------------------------------------------------------------------
    # Traceability visibility
    # ------------------------------------------------------------------
    def list_traceability_transactions(
        self,
        organization_id: str,
        facility_id: str,
        run_id: str,
    ) -> list[TraceabilityTransaction]:
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            output_ids = list(
                session.scalars(
                    select(ExtractionRunOutput.id).where(ExtractionRunOutput.run_id == run_id)
                )
            )
            conditions = [
                (TraceabilityTransaction.entity_type == "extraction_run")
                & (TraceabilityTransaction.entity_id == run_id)
            ]
            if output_ids:
                conditions.append(
                    (TraceabilityTransaction.entity_type == "extraction_output")
                    & TraceabilityTransaction.entity_id.in_(output_ids)
                )
            from sqlalchemy import or_

            return list(
                session.scalars(
                    select(TraceabilityTransaction)
                    .where(
                        TraceabilityTransaction.organization_id == organization_id,
                        TraceabilityTransaction.facility_id == facility_id,
                        or_(*conditions),
                    )
                    .order_by(TraceabilityTransaction.requested_at.desc())
                )
            )

    # ------------------------------------------------------------------
    # Run 360 snapshot
    # ------------------------------------------------------------------
    def run_360(self, organization_id: str, facility_id: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(organization_id, facility_id, run_id)
        inputs = self.list_run_inputs(organization_id, facility_id, run_id)
        stages = self.list_stage_events(organization_id, facility_id, run_id)
        outputs = self.list_outputs(organization_id, facility_id, run_id)
        qa = self.list_qa_events(organization_id, facility_id, run_id)
        costs = self.list_cost_events(organization_id, facility_id, run_id)
        traceability = self.list_traceability_transactions(organization_id, facility_id, run_id)
        mass = self.mass_balance(organization_id, facility_id, run_id)
        cogs = self.cogs_summary(organization_id, facility_id, run_id)
        return {
            "run": run,
            "inputs": inputs,
            "stages": stages,
            "outputs": outputs,
            "qa_events": qa,
            "cost_events": costs,
            "traceability": traceability,
            "mass_balance": mass,
            "cogs": cogs,
            "workflow": get_extraction_workflow(run.workflow_key),
            "toll_job": self.get_toll_job(organization_id, facility_id, run_id),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _require_scope(session, organization_id: str, facility_id: str) -> Facility:
        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != organization_id:
            raise ValueError("Facility does not belong to the active organization.")
        return facility

    @classmethod
    def _require_run(cls, session, organization_id: str, facility_id: str, run_id: str) -> ExtractionRun:
        cls._require_scope(session, organization_id, facility_id)
        run = session.get(ExtractionRun, run_id)
        if not run or run.organization_id != organization_id or run.facility_id != facility_id:
            raise ValueError("Extraction run was not found in the active facility.")
        return run

    @staticmethod
    def _require_open_run(run: ExtractionRun) -> None:
        if run.status not in OPEN_RUN_STATUSES:
            raise ValueError("This extraction run is closed and cannot be modified.")

    @classmethod
    def _require_lot(cls, session, organization_id: str, facility_id: str, lot_id: str) -> InventoryLot:
        cls._require_scope(session, organization_id, facility_id)
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
            raise ValueError("Inventory lot was not found in the active facility.")
        return lot

    @classmethod
    def _require_input(cls, session, organization_id: str, facility_id: str, input_id: str) -> ExtractionRunInput:
        cls._require_scope(session, organization_id, facility_id)
        record = session.get(ExtractionRunInput, input_id)
        if not record or record.organization_id != organization_id or record.facility_id != facility_id:
            raise ValueError("Extraction run input was not found in the active facility.")
        return record

    @staticmethod
    def _lot_balance(session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _lot_reserved_quantity(
        session,
        lot_id: str,
        *,
        exclude_extraction_input_id: str | None = None,
    ) -> float:
        production_reserved = float(
            session.scalar(
                select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(
                    MaterialReservation.lot_id == lot_id,
                    MaterialReservation.status == "reserved",
                )
            )
            or 0.0
        )
        commercial_reserved = float(
            session.scalar(
                select(
                    func.coalesce(
                        func.sum(OrderLotAllocation.quantity - OrderLotAllocation.fulfilled_quantity),
                        0.0,
                    )
                ).where(
                    OrderLotAllocation.lot_id == lot_id,
                    OrderLotAllocation.status.in_(("reserved", "partial")),
                )
            )
            or 0.0
        )
        extraction_statement = select(
            func.coalesce(
                func.sum(ExtractionRunInput.reserved_quantity - ExtractionRunInput.consumed_quantity),
                0.0,
            )
        ).where(
            ExtractionRunInput.lot_id == lot_id,
            ExtractionRunInput.status.in_(tuple(INPUT_OPEN_STATUSES)),
        )
        if exclude_extraction_input_id:
            extraction_statement = extraction_statement.where(ExtractionRunInput.id != exclude_extraction_input_id)
        extraction_reserved = float(session.scalar(extraction_statement) or 0.0)
        return max(0.0, production_reserved + commercial_reserved + extraction_reserved)

    def _refresh_lot_status(self, session, lot_id: str) -> None:
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.status not in {"available", "reserved"}:
            return
        balance = self._lot_balance(session, lot_id)
        reserved = self._lot_reserved_quantity(session, lot_id)
        if balance <= 1e-9:
            lot.status = "depleted"
        elif reserved > 1e-9:
            lot.status = "reserved"
        else:
            lot.status = "available"

    @staticmethod
    def _audit(
        session,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str,
        changes: dict[str, Any],
    ) -> None:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor=_clean(actor),
                changes_json=json.dumps(changes, sort_keys=True, default=str),
            )
        )

    @staticmethod
    def _allocate_output_cogs(session, run_id: str) -> None:
        outputs = list(
            session.scalars(
                select(ExtractionRunOutput)
                .where(
                    ExtractionRunOutput.run_id == run_id,
                    ExtractionRunOutput.status.in_(tuple(OUTPUT_ACTIVE_STATUSES)),
                )
                .order_by(ExtractionRunOutput.position)
            )
        )
        if not outputs:
            return
        total_cost = float(
            session.scalar(
                select(func.coalesce(func.sum(ExtractionCostEvent.amount_usd), 0.0)).where(
                    ExtractionCostEvent.run_id == run_id
                )
            )
            or 0.0
        )
        units = {output.unit.casefold() for output in outputs}
        if len(units) != 1:
            # Mixed units need an explicit allocation basis; do not invent one.
            for output in outputs:
                output.output_cost_usd = 0.0
            return
        total_quantity = sum(max(0.0, float(output.quantity)) for output in outputs)
        if total_quantity <= 0:
            return
        for output in outputs:
            output.output_cost_usd = total_cost * (float(output.quantity) / total_quantity)
