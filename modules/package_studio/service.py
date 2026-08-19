"""Transactional Package Studio service.

Package Studio records package transformation lineage while continuing to use the
existing append-only Co-Man inventory ledger as the balance source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
from .models import (
    PACKAGE_STUDIO_ACTIONS,
    PACKAGE_STUDIO_PURPOSES,
    PackageStudioInput,
    PackageStudioOutput,
    PackageStudioRun,
)


@dataclass(frozen=True)
class PackageStudioInputPlan:
    lot_id: str
    quantity: float
    unit: str
    purpose: str = "source"


@dataclass(frozen=True)
class PackageStudioOutputPlan:
    product_id: str
    lot_code: str
    inventory_quantity: float
    inventory_unit: str
    source_equivalent_quantity: float
    source_equivalent_unit: str
    compliance_package_id: str = ""
    purpose: str = "standard"
    location_code: str = "FINISHED-GOODS"
    notes: str = ""


@dataclass(frozen=True)
class PackageStudioPlan:
    action_type: str
    inputs: tuple[PackageStudioInputPlan, ...]
    outputs: tuple[PackageStudioOutputPlan, ...]
    loss_quantity: float = 0.0
    source_unit: str = ""
    reason: str = ""
    notes: str = ""
    run_number: str = ""
    production_order_id: str | None = None
    commercial_order_id: str | None = None


@dataclass(frozen=True)
class PackageStudioPreview:
    action_type: str
    total_input: float
    total_output_source_equivalent: float
    loss_quantity: float
    source_unit: str
    balanced: bool
    difference: float
    output_count: int


@dataclass(frozen=True)
class PackageStudioCommitResult:
    run_id: str
    run_number: str
    output_lot_ids: tuple[str, ...]
    input_transactions: int
    output_transactions: int


@dataclass(frozen=True)
class AvailableLot:
    lot_id: str
    lot_code: str
    compliance_package_id: str
    product_id: str
    product_name: str
    sku: str
    balance: float
    unit: str
    location_code: str


@dataclass(frozen=True)
class StudioProduct:
    product_id: str
    name: str
    sku: str
    item_type: str
    base_unit: str


class PackageStudioService:
    """Create atomic package transformations and query their Source Trail."""

    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _normalize_action(value: str) -> str:
        action = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
        if action not in PACKAGE_STUDIO_ACTIONS:
            raise ValueError(f"Unsupported Package Studio action: {value}")
        return action

    @staticmethod
    def _normalize_unit(value: str) -> str:
        unit = str(value or "").strip().casefold()
        if not unit:
            raise ValueError("A source unit is required.")
        return unit

    @staticmethod
    def _balance(session: Session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _unit_for_lot(session: Session, lot: InventoryLot) -> str:
        unit = session.scalar(
            select(InventoryTransaction.unit)
            .where(InventoryTransaction.lot_id == lot.id)
            .order_by(InventoryTransaction.occurred_at.desc())
            .limit(1)
        )
        if unit:
            return str(unit)
        product = session.get(Product, lot.product_id)
        return str(product.base_unit if product else "unit")

    @staticmethod
    def _run_number(session: Session, organization_id: str, requested: str = "") -> str:
        requested = str(requested or "").strip()
        if requested:
            existing = session.scalar(
                select(PackageStudioRun.id).where(
                    PackageStudioRun.organization_id == organization_id,
                    PackageStudioRun.run_number == requested,
                )
            )
            if existing:
                raise ValueError("That Package Studio run number already exists.")
            return requested
        prefix = utc_now().strftime("PS-%Y%m%d")
        count = int(
            session.scalar(
                select(func.count(PackageStudioRun.id)).where(
                    PackageStudioRun.organization_id == organization_id,
                    PackageStudioRun.run_number.like(f"{prefix}-%"),
                )
            )
            or 0
        )
        return f"{prefix}-{count + 1:03d}"

    def preview(self, plan: PackageStudioPlan) -> PackageStudioPreview:
        action = self._normalize_action(plan.action_type)
        if not plan.inputs:
            raise ValueError("At least one source package is required.")
        if not plan.outputs:
            raise ValueError("At least one output is required.")
        if action == "multi_build" and len(plan.outputs) < 2:
            raise ValueError("Multi-Build requires at least two outputs.")
        if action in {"breakdown", "sample_pull"} and len(plan.inputs) != 1:
            raise ValueError("Breakdown and Sample Pull use exactly one source package.")

        input_units = {self._normalize_unit(item.unit) for item in plan.inputs}
        if len(input_units) != 1:
            raise ValueError("Phase 1 requires source inputs to share one unit of measure.")
        source_unit = self._normalize_unit(plan.source_unit or next(iter(input_units)))
        if input_units != {source_unit}:
            raise ValueError("Input units must match the run source unit.")

        total_input = 0.0
        for item in plan.inputs:
            quantity = float(item.quantity)
            if quantity <= 0:
                raise ValueError("Source quantities must be greater than zero.")
            total_input += quantity

        total_output = 0.0
        seen_lot_codes: set[str] = set()
        for item in plan.outputs:
            if float(item.inventory_quantity) <= 0:
                raise ValueError("Output inventory quantities must be greater than zero.")
            source_equivalent = float(item.source_equivalent_quantity)
            if source_equivalent <= 0:
                raise ValueError("Every output needs a positive source-material equivalent.")
            if self._normalize_unit(item.source_equivalent_unit) != source_unit:
                raise ValueError("Output source-equivalent units must match the run source unit.")
            purpose = str(item.purpose or "standard").strip().casefold()
            if purpose not in PACKAGE_STUDIO_PURPOSES:
                raise ValueError(f"Unsupported output purpose: {item.purpose}")
            lot_code = str(item.lot_code or "").strip()
            if not lot_code:
                raise ValueError("Every output requires a lot/package code.")
            if lot_code.casefold() in seen_lot_codes:
                raise ValueError("Output lot/package codes must be unique within the run.")
            seen_lot_codes.add(lot_code.casefold())
            total_output += source_equivalent

        loss = float(plan.loss_quantity or 0.0)
        if loss < 0:
            raise ValueError("Loss cannot be negative.")
        difference = total_input - total_output - loss
        balanced = abs(difference) <= 1e-6
        if not balanced:
            raise ValueError(
                "Source material must balance exactly: input = output source-equivalent + recorded loss. "
                f"Current difference is {difference:,.4f} {source_unit}."
            )
        return PackageStudioPreview(
            action_type=action,
            total_input=total_input,
            total_output_source_equivalent=total_output,
            loss_quantity=loss,
            source_unit=source_unit,
            balanced=True,
            difference=difference,
            output_count=len(plan.outputs),
        )

    def list_available_lots(self, organization_id: str, facility_id: str) -> list[AvailableLot]:
        with self._sessions() as session:
            rows = session.execute(
                select(InventoryLot, Product)
                .join(Product, Product.id == InventoryLot.product_id)
                .where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                    InventoryLot.status == "available",
                )
                .order_by(Product.name, InventoryLot.lot_code)
            ).all()
            results: list[AvailableLot] = []
            for lot, product in rows:
                balance = self._balance(session, lot.id)
                if balance <= 1e-9:
                    continue
                results.append(
                    AvailableLot(
                        lot_id=lot.id,
                        lot_code=lot.lot_code,
                        compliance_package_id=lot.compliance_package_id,
                        product_id=product.id,
                        product_name=product.name,
                        sku=product.sku,
                        balance=balance,
                        unit=self._unit_for_lot(session, lot),
                        location_code=lot.location_code,
                    )
                )
            return results

    def list_products(self, organization_id: str) -> list[StudioProduct]:
        with self._sessions() as session:
            products = list(
                session.scalars(
                    select(Product)
                    .where(Product.organization_id == organization_id, Product.active.is_(True))
                    .order_by(Product.name)
                )
            )
            return [
                StudioProduct(
                    product_id=item.id,
                    name=item.name,
                    sku=item.sku,
                    item_type=item.item_type,
                    base_unit=item.base_unit,
                )
                for item in products
            ]

    def commit(
        self,
        plan: PackageStudioPlan,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
    ) -> PackageStudioCommitResult:
        preview = self.preview(plan)
        actor = str(actor or "").strip() or "system"

        with self._sessions.begin() as session:
            input_lots: list[InventoryLot] = []
            for item in plan.inputs:
                lot = session.scalar(
                    select(InventoryLot)
                    .where(
                        InventoryLot.id == item.lot_id,
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                    )
                    .with_for_update()
                )
                if not lot:
                    raise ValueError("A source package was not found in the active facility.")
                if lot.status != "available":
                    raise ValueError(f"Source package {lot.lot_code} is not available.")
                balance = self._balance(session, lot.id)
                if balance + 1e-9 < float(item.quantity):
                    raise ValueError(
                        f"Source package {lot.lot_code} has {balance:,.4f} {item.unit}, "
                        f"less than the requested {float(item.quantity):,.4f}."
                    )
                input_lots.append(lot)

            output_products: list[Product] = []
            for output in plan.outputs:
                product = session.get(Product, output.product_id)
                if not product or product.organization_id != organization_id or not product.active:
                    raise ValueError("An output product is not available in this organization.")
                duplicate = session.scalar(
                    select(InventoryLot.id).where(
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.lot_code == str(output.lot_code).strip(),
                    )
                )
                if duplicate:
                    raise ValueError(f"Output lot/package code {output.lot_code} already exists.")
                output_products.append(product)

            if preview.action_type in {"breakdown", "sample_pull"}:
                source_product_id = input_lots[0].product_id
                if any(product.id != source_product_id for product in output_products):
                    raise ValueError("Breakdown and Sample Pull outputs must keep the source product identity.")

            run_number = self._run_number(session, organization_id, plan.run_number)
            run = PackageStudioRun(
                organization_id=organization_id,
                facility_id=facility_id,
                run_number=run_number,
                action_type=preview.action_type,
                status="committed",
                source_quantity=preview.total_input,
                source_unit=preview.source_unit,
                loss_quantity=preview.loss_quantity,
                reason=str(plan.reason or "").strip(),
                notes=str(plan.notes or "").strip(),
                production_order_id=plan.production_order_id,
                commercial_order_id=plan.commercial_order_id,
                external_sync_status="not_requested",
                created_by=actor,
                completed_by=actor,
                committed_at=utc_now(),
            )
            session.add(run)
            session.flush()

            for position, (item, lot) in enumerate(zip(plan.inputs, input_lots), start=1):
                session.add(
                    PackageStudioInput(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        lot_id=lot.id,
                        position=position,
                        quantity=float(item.quantity),
                        unit=self._normalize_unit(item.unit),
                        purpose=str(item.purpose or "source").strip(),
                    )
                )
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="package_studio_consume",
                        quantity_delta=-float(item.quantity),
                        unit=self._normalize_unit(item.unit),
                        production_order_id=plan.production_order_id,
                        commercial_order_id=plan.commercial_order_id,
                        reason=str(plan.reason or preview.action_type),
                        reference=run_number,
                        actor=actor,
                    )
                )

            output_lot_ids: list[str] = []
            for position, (output, product) in enumerate(zip(plan.outputs, output_products), start=1):
                lot = InventoryLot(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    product_id=product.id,
                    lot_code=str(output.lot_code).strip(),
                    compliance_package_id=str(output.compliance_package_id or "").strip(),
                    location_code=str(output.location_code or "FINISHED-GOODS").strip(),
                    status="available",
                    notes=(
                        f"Created by Package Studio {run_number}. "
                        + str(output.notes or "").strip()
                    ).strip(),
                )
                session.add(lot)
                session.flush()
                output_lot_ids.append(lot.id)
                session.add(
                    PackageStudioOutput(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        product_id=product.id,
                        lot_id=lot.id,
                        position=position,
                        lot_code=lot.lot_code,
                        compliance_package_id=lot.compliance_package_id,
                        inventory_quantity=float(output.inventory_quantity),
                        inventory_unit=self._normalize_unit(output.inventory_unit),
                        source_equivalent_quantity=float(output.source_equivalent_quantity),
                        source_equivalent_unit=self._normalize_unit(output.source_equivalent_unit),
                        purpose=str(output.purpose or "standard").strip().casefold(),
                        location_code=lot.location_code,
                        notes=str(output.notes or "").strip(),
                    )
                )
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="package_studio_output",
                        quantity_delta=float(output.inventory_quantity),
                        unit=self._normalize_unit(output.inventory_unit),
                        production_order_id=plan.production_order_id,
                        commercial_order_id=plan.commercial_order_id,
                        reason=str(plan.reason or preview.action_type),
                        reference=run_number,
                        actor=actor,
                    )
                )

            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="package_studio_run",
                    entity_id=run.id,
                    action="committed",
                    actor=actor,
                    changes_json=json.dumps(
                        {
                            "run_number": run_number,
                            "action_type": preview.action_type,
                            "source_quantity": preview.total_input,
                            "source_unit": preview.source_unit,
                            "loss_quantity": preview.loss_quantity,
                            "input_lot_ids": [lot.id for lot in input_lots],
                            "output_lot_ids": output_lot_ids,
                            "external_sync_status": "not_requested",
                        },
                        sort_keys=True,
                    ),
                )
            )
            return PackageStudioCommitResult(
                run_id=run.id,
                run_number=run_number,
                output_lot_ids=tuple(output_lot_ids),
                input_transactions=len(plan.inputs),
                output_transactions=len(plan.outputs),
            )

    def recent_runs(self, organization_id: str, facility_id: str, *, limit: int = 25) -> list[dict]:
        with self._sessions() as session:
            runs = list(
                session.scalars(
                    select(PackageStudioRun)
                    .where(
                        PackageStudioRun.organization_id == organization_id,
                        PackageStudioRun.facility_id == facility_id,
                    )
                    .order_by(PackageStudioRun.created_at.desc())
                    .limit(max(1, int(limit)))
                )
            )
            return [
                {
                    "id": run.id,
                    "run_number": run.run_number,
                    "action_type": run.action_type,
                    "status": run.status,
                    "source_quantity": run.source_quantity,
                    "source_unit": run.source_unit,
                    "loss_quantity": run.loss_quantity,
                    "external_sync_status": run.external_sync_status,
                    "created_by": run.created_by,
                    "committed_at": run.committed_at,
                }
                for run in runs
            ]

    def source_trail(self, lot_id: str, *, organization_id: str, facility_id: str) -> dict:
        """Return immediate parent/child lineage for one durable inventory lot."""
        with self._sessions() as session:
            lot = session.scalar(
                select(InventoryLot).where(
                    InventoryLot.id == lot_id,
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
            )
            if not lot:
                raise ValueError("Package was not found in the active facility.")
            product = session.get(Product, lot.product_id)

            created_output = session.scalar(
                select(PackageStudioOutput).where(PackageStudioOutput.lot_id == lot_id)
            )
            parent_inputs: list[PackageStudioInput] = []
            parent_run = None
            if created_output:
                parent_run = session.get(PackageStudioRun, created_output.run_id)
                parent_inputs = list(
                    session.scalars(
                        select(PackageStudioInput)
                        .where(PackageStudioInput.run_id == created_output.run_id)
                        .order_by(PackageStudioInput.position)
                    )
                )

            child_inputs = list(
                session.scalars(
                    select(PackageStudioInput).where(PackageStudioInput.lot_id == lot_id)
                )
            )
            child_runs: list[dict] = []
            for input_row in child_inputs:
                run = session.get(PackageStudioRun, input_row.run_id)
                outputs = list(
                    session.scalars(
                        select(PackageStudioOutput)
                        .where(PackageStudioOutput.run_id == input_row.run_id)
                        .order_by(PackageStudioOutput.position)
                    )
                )
                child_runs.append(
                    {
                        "run_number": run.run_number if run else "",
                        "action_type": run.action_type if run else "",
                        "quantity_consumed": input_row.quantity,
                        "unit": input_row.unit,
                        "outputs": [
                            {
                                "lot_id": output.lot_id,
                                "lot_code": output.lot_code,
                                "product_id": output.product_id,
                                "inventory_quantity": output.inventory_quantity,
                                "inventory_unit": output.inventory_unit,
                                "purpose": output.purpose,
                            }
                            for output in outputs
                        ],
                    }
                )

            def parent_payload(item: PackageStudioInput) -> dict:
                parent_lot = session.get(InventoryLot, item.lot_id)
                parent_product = session.get(Product, parent_lot.product_id) if parent_lot else None
                return {
                    "lot_id": item.lot_id,
                    "lot_code": parent_lot.lot_code if parent_lot else "",
                    "product_name": parent_product.name if parent_product else "",
                    "quantity": item.quantity,
                    "unit": item.unit,
                }

            return {
                "lot": {
                    "lot_id": lot.id,
                    "lot_code": lot.lot_code,
                    "compliance_package_id": lot.compliance_package_id,
                    "product_name": product.name if product else "",
                    "balance": self._balance(session, lot.id),
                    "unit": self._unit_for_lot(session, lot),
                },
                "created_by": (
                    {
                        "run_number": parent_run.run_number,
                        "action_type": parent_run.action_type,
                        "parents": [parent_payload(item) for item in parent_inputs],
                    }
                    if parent_run
                    else None
                ),
                "used_by": child_runs,
            }
