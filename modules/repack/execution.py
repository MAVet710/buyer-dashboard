"""Durable repack plans with an atomic, inventory-neutral production handoff."""
import json
import math

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from modules.coman.audit import record_audit_event
from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product, ProductionOrder
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.inventory_quality.service import LotQualityService
from modules.package_studio.models import PackageStudioRun
from .logic import grams_from_unit
from .models import WhiteLabelPlan


def economics(scenario):
    form, allocations = scenario["form"], scenario["plan"]
    def number(key):
        value = float(form.get(key, 0))
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and nonnegative.")
        if key.endswith("_pct") and value > 100:
            raise ValueError(f"{key} cannot exceed 100%.")
        return value
    for key, value in form.items():
        if isinstance(value, (int, float)):
            number(key)
    if form.get("bulk_weight_unit") not in {"g", "oz", "lb"}:
        raise ValueError("Choose grams, ounces, or pounds.")
    grams = grams_from_unit(number("bulk_weight_value"), form["bulk_weight_unit"])
    if grams <= 0:
        raise ValueError("Source weight must be positive.")
    enabled = [row for row in allocations if row["enabled"]]
    if not enabled or sum(row["allocation_pct"] for row in enabled) > 100 + 1e-9:
        raise ValueError("Enable package allocations totaling at most 100%.")
    loss = min(100, sum(number(key) for key in ("shrink_loss_pct", "trim_loss_pct", "qa_hold_loss_pct", "moisture_loss_pct")))
    usable = grams * (1 - loss / 100)
    landed = number("bulk_total_cost_usd") * (1 - number("discount_pct") / 100) + number("freight_or_delivery_cost_usd") + number("sample_or_testing_cost_usd")
    overhead = sum(number(key) for key in ("labor_cost_total_usd", "other_costs_usd", "compliance_admin_cost_usd")) / len(enabled)
    outputs = []
    for row in enabled:
        if row["package_size_g"] <= 0:
            raise ValueError("Enabled package sizes must be positive.")
        allocated = usable * row["allocation_pct"] / 100
        units = math.floor(allocated / row["package_size_g"])
        packaging = sum(value for key, value in row.items() if key.endswith("cost_per_unit"))
        cost = units * row["package_size_g"] * (landed / usable if usable else 0) + units * packaging + overhead
        revenue = units * row["target_retail_price_per_unit"]
        outputs.append(dict(package_size_g=row["package_size_g"], units=units, allocated_g=allocated,
                            packaged_g=units * row["package_size_g"], cost_usd=cost, revenue_usd=revenue))
    return dict(source_g=grams, usable_g=usable, landed_cost_usd=landed, outputs=outputs,
                total_units=sum(row["units"] for row in outputs),
                projected_profit_usd=sum(row["revenue_usd"] - row["cost_usd"] for row in outputs))


class WhiteLabelService:
    def __init__(self, engine):
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    @staticmethod
    def _get(session, org, facility, plan_id, lock=False):
        query = select(WhiteLabelPlan).where(WhiteLabelPlan.id == plan_id,
            WhiteLabelPlan.organization_id == org, WhiteLabelPlan.facility_id == facility)
        row = session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise LookupError("Plan was not found in this facility.")
        return row

    @staticmethod
    def _source(session, org, facility, lot_id, grams):
        lot = session.scalar(select(InventoryLot).where(InventoryLot.id == lot_id,
            InventoryLot.organization_id == org, InventoryLot.facility_id == facility))
        if lot is None:
            raise ValueError("Source lot was not found in this facility.")
        product = session.get(Product, lot.product_id)
        if not product or not product.active or product.organization_id != org or product.base_unit not in {"g", "oz", "lb", "kg"}:
            raise ValueError("Source must be an existing weight-based inventory product.")
        units = set(session.scalars(select(InventoryTransaction.unit).where(
            InventoryTransaction.organization_id == org, InventoryTransaction.facility_id == facility,
            InventoryTransaction.lot_id == lot.id).distinct()))
        if units != {product.base_unit}:
            raise ValueError("Source ledger units must match the inventory product unit before planning.")
        quality = LotQualityService.read(session, lot.id)
        if lot.status not in {"available", "released"} or not quality or not LotQualityService.is_passed(quality.lab_testing_state, quality.coa_reference):
            raise ValueError("Source requires available/released inventory and passed QA with COA evidence.")
        if quality.organization_id != org or quality.facility_id != facility:
            raise ValueError("Source QA evidence is outside this facility.")
        available = InventoryAvailabilityService.build(session, org, facility)["by_lot"][lot.id]["available"]
        factor = 1000 if product.base_unit == "kg" else grams_from_unit(1, product.base_unit)
        if grams > available * factor + 1e-9:
            raise ValueError("Source weight exceeds available inventory after existing commitments.")
        return dict(lot_id=lot.id, lot_code=lot.lot_code, package_id=lot.compliance_package_id,
                    product_id=product.id, product_name=product.name, unit=product.base_unit,
                    quantity=grams / factor, coa_reference=quality.coa_reference,
                    coa_document_id=quality.coa_document_id, lab_testing_state=quality.lab_testing_state)

    @staticmethod
    def _payload(row, order=None, detail=True, package_started=False):
        # Execution state is projected from the durable canonical order, never a second ledger.
        status = row.status
        if order:
            status = {"in_progress": "executing", "on_hold": "executing", "complete": "completed",
                      "cancelled": "cancelled"}.get(order.status, "approved")
            if status == "approved" and package_started:
                status = "executing"
        result = dict(id=row.id, name=row.name, status=status, revision=row.revision,
                      source_lot_id=row.source_lot_id, production_order_id=row.production_order_id,
                      execution_status=order.status if order else None)
        if detail:
            result.update(scenario=json.loads(row.scenario_json), source=json.loads(row.source_json),
                          economics=json.loads(row.economics_json))
        return result

    @staticmethod
    def _order(session, row):
        if not row.production_order_id:
            return None
        order = session.get(ProductionOrder, row.production_order_id)
        if not order or (order.organization_id, order.facility_id) != (row.organization_id, row.facility_id):
            raise ValueError("Execution link is outside this facility.")
        return order

    def list(self, org, facility, offset=0):
        with self.sessions() as session:
            package_started = select(PackageStudioRun.id).where(
                PackageStudioRun.production_order_id == WhiteLabelPlan.production_order_id,
                PackageStudioRun.organization_id == org, PackageStudioRun.facility_id == facility,
                PackageStudioRun.status == "committed").exists()
            rows = session.execute(select(WhiteLabelPlan.id, WhiteLabelPlan.name, WhiteLabelPlan.status,
                WhiteLabelPlan.revision, WhiteLabelPlan.source_lot_id, WhiteLabelPlan.production_order_id,
                ProductionOrder.status.label("execution_status"), package_started.label("package_started")).outerjoin(ProductionOrder,
                (ProductionOrder.id == WhiteLabelPlan.production_order_id) &
                (ProductionOrder.organization_id == org) & (ProductionOrder.facility_id == facility)).where(
                WhiteLabelPlan.organization_id == org, WhiteLabelPlan.facility_id == facility
            ).order_by(WhiteLabelPlan.updated_at.desc(), WhiteLabelPlan.id).offset(offset).limit(100)).all()
            result = []
            for row in rows:
                item = dict(row._mapping)
                if item["execution_status"]:
                    item["status"] = {"in_progress": "executing", "on_hold": "executing", "complete": "completed",
                                      "cancelled": "cancelled"}.get(item["execution_status"], "approved")
                    if item["status"] == "approved" and item["package_started"]:
                        item["status"] = "executing"
                result.append(item)
            return result

    def get(self, org, facility, plan_id):
        with self.sessions() as session:
            row = self._get(session, org, facility, plan_id)
            package_started = bool(row.production_order_id and session.scalar(select(PackageStudioRun.id).where(
                PackageStudioRun.production_order_id == row.production_order_id,
                PackageStudioRun.organization_id == org, PackageStudioRun.facility_id == facility,
                PackageStudioRun.status == "committed").limit(1)))
            return self._payload(row, self._order(session, row), package_started=package_started)

    def save(self, org, facility, actor, payload, plan_id=None):
        calculated = economics(payload["scenario"])
        with self.sessions.begin() as session:
            scoped = session.get(Facility, facility)
            if not scoped or scoped.organization_id != org:
                raise ValueError("Facility was not found in this organization.")
            row = self._get(session, org, facility, plan_id, True) if plan_id else None
            if row and (row.status != "draft" or row.revision != payload.get("revision")):
                raise ValueError("Plan changed or is no longer draft. Reload before editing.")
            before = self._payload(row) if row else None
            source = self._source(session, org, facility, payload["source_lot_id"], calculated["source_g"])
            if row is None:
                row = WhiteLabelPlan(organization_id=org, facility_id=facility, created_by=actor)
                session.add(row)
            else:
                row.revision += 1
            row.name = payload["name"].strip()
            if not row.name:
                raise ValueError("Plan name is required.")
            row.source_lot_id = payload["source_lot_id"]
            row.scenario_json = json.dumps(payload["scenario"], allow_nan=False)
            row.economics_json = json.dumps(calculated, allow_nan=False)
            row.source_json = json.dumps(source)
            row.updated_by = actor
            session.flush()
            self._audit(session, row, actor, "saved", before=before)
            return self._payload(row)

    @staticmethod
    def _audit(session, row, actor, action, before=None):
        record_audit_event(session, organization_id=row.organization_id, facility_id=row.facility_id,
            entity_type="white_label_plan", entity_id=row.id, action=action, actor=actor,
            source="user", correlation_id=row.id, before=before, after=WhiteLabelService._payload(row),
            changes={"revision": row.revision, "source_lot_id": row.source_lot_id,
                     "production_order_id": row.production_order_id, "status": row.status})

    def approve(self, org, facility, actor, plan_id, revision):
        with self.sessions.begin() as session:
            row = self._get(session, org, facility, plan_id, True)
            if row.production_order_id:
                return self._payload(row, self._order(session, row))
            if row.status != "draft" or row.revision != revision:
                raise ValueError("Only the current saved draft can be approved.")
            calculated = economics(json.loads(row.scenario_json))
            if calculated["total_units"] <= 0:
                raise ValueError("Approval requires at least one expected output unit.")
            source = self._source(session, org, facility, row.source_lot_id, calculated["source_g"])
            order = ProductionOrder(organization_id=org, facility_id=facility,
                order_number=f"WL-{row.id}", work_type="internal", product_name=row.name,
                product_format="White Label / Repack", requested_units=calculated["total_units"],
                source_lot_reference=source["lot_code"], status="draft", created_by=actor, updated_by=actor,
                notes=json.dumps({"white_label_plan_id": row.id, "source": source, "expected_outputs": calculated["outputs"],
                    "instructions": "Review output SKU mapping, material allocation and actuals in the canonical execution workflow. Planning does not reserve or consume inventory."}))
            session.add(order)
            session.flush()
            row.production_order_id = order.id
            row.status = "approved"
            row.revision += 1
            row.updated_by = actor
            row.source_json = json.dumps(source)
            self._audit(session, row, actor, "approved")
            record_audit_event(session, organization_id=org, facility_id=facility,
                entity_type="production_order", entity_id=order.id, action="created", actor=actor,
                correlation_id=row.id, changes={"white_label_plan_id": row.id, "status": "draft"})
            return self._payload(row, order)

    def cancel(self, org, facility, actor, plan_id, revision):
        with self.sessions.begin() as session:
            row = self._get(session, org, facility, plan_id, True)
            if row.status != "draft" or row.revision != revision:
                raise ValueError("Only a current draft may be cancelled here. Cancel approved execution in Production Run 360.")
            row.status = "cancelled"
            row.revision += 1
            row.updated_by = actor
            self._audit(session, row, actor, "cancelled")
            return self._payload(row)


def validate_package_handoff(session, package_plan, org, facility):
    """Revalidate a White Label link inside Package Studio's locked commit transaction.

    Other Package Studio workflows retain their existing execution contracts.
    """
    if not package_plan.production_order_id:
        return
    order = session.scalar(select(ProductionOrder).where(ProductionOrder.id == package_plan.production_order_id).with_for_update())
    if not order or (order.organization_id, order.facility_id) != (org, facility):
        raise ValueError("Production order was not found in this facility.")
    row = session.scalar(select(WhiteLabelPlan).where(
        WhiteLabelPlan.production_order_id == order.id).with_for_update())
    if row is None:
        return
    if (row.organization_id, row.facility_id) != (org, facility):
        raise ValueError("White Label handoff is outside this facility.")
    if row.production_order_id != order.id or row.status != "approved" or order.status in {"cancelled", "complete", "on_hold"}:
        raise ValueError("White Label execution is not open for package transformation.")
    if len(package_plan.inputs) != 1 or package_plan.inputs[0].lot_id != row.source_lot_id:
        raise ValueError("Package execution must use the approved White Label source lot.")
    item = package_plan.inputs[0]
    source = json.loads(row.source_json)
    if item.unit != source["unit"]:
        raise ValueError("Package source unit differs from the approved source.")
    grams = item.quantity * (1000 if item.unit == "kg" else grams_from_unit(1, item.unit))
    WhiteLabelService._source(session, org, facility, row.source_lot_id, grams)
