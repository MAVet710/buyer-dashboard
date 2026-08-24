from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import BomComponent, Facility, Organization, Product, ProductBom
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService
from modules.cultivation.models import CultivationPlantEvent
from modules.cultivation.service import CultivationService
from modules.data_hub_repository import DataHubRepository
from modules.extraction.repository import ExtractionRepository
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.product_master.models import ProductMasterProfile
from modules.retail_planning import RetailPlanningService
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec, objects_frame
from services.extraction_agent import build_extraction_derived_datasets

from ..auth import RequestContext
from ..routers.buyer_parity import _model


ALL = ("ops", "buyer", "purchasing", "inventory", "audit", "compliance", "nomenclature", "repack", "coman", "extraction", "commercial", "commercial_finance", "cultivation", "data_hub")
RETAIL = ("ops", "buyer", "purchasing", "inventory", "audit", "compliance", "nomenclature", "repack", "data_hub")
PRODUCTION = ("ops", "coman", "repack", "extraction", "audit", "data_hub")
COMMERCIAL = ("ops", "commercial", "commercial_finance", "data_hub")
CULTIVATION = ("ops", "cultivation", "data_hub")
PURCHASE_ROLES = ("dev", "admin", "supervisor", "buyer")


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if value is None:
        return pd.DataFrame()
    if isinstance(value, list):
        return objects_frame(value) if value and not isinstance(value[0], dict) else pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return objects_frame([value])


def facility_access(context: RequestContext, engine: Engine, *, operation_type: str) -> tuple[DatasetAccessContext, str, str]:
    with Session(engine) as session:
        facility = session.get(Facility, context.facility_id)
        organization = session.get(Organization, context.organization_id)
    capabilities = set()
    if facility and facility.organization_id == context.organization_id:
        if facility.retail_enabled:
            capabilities.add("retail")
        if facility.production_enabled:
            capabilities.add("production")
        if facility.cultivation_enabled:
            capabilities.add("cultivation")
        if facility.commercial_enabled:
            capabilities.add("commercial")
    return DatasetAccessContext(context.organization_id, context.facility_id, context.user_id, context.role, frozenset(capabilities), operation_type=operation_type, engine=engine), (organization.name if organization else ""), (facility.name if facility and facility.organization_id == context.organization_id else "")


def build_dataset_registry(context: RequestContext, engine: Engine, *, operation_type: str = "retail") -> DatasetRegistry:
    registry = DatasetRegistry()
    buyer_cache: dict[str, Any] = {}
    planning_cache: dict[str, Any] = {}
    commercial_cache: dict[str, Any] = {}
    extraction_cache: dict[str, Any] = {}

    def buyer_data() -> dict[str, Any]:
        if not buyer_cache:
            try:
                detail, product, inventory, sales, inventory_source, sales_source = _model(context, engine, 21, 1.0, 60)
                buyer_cache.update({
                    "buyer_forecast": detail,
                    "buyer_product_forecast": product,
                    "inventory": inventory,
                    "sales": sales,
                    "buyer_sources": pd.DataFrame([
                        {"dataset": "inventory", "filename": inventory_source.filename, "rows": inventory_source.row_count, "freshness": inventory_source.activated_at},
                        {"dataset": "product_sales", "filename": sales_source.filename, "rows": sales_source.row_count, "freshness": sales_source.activated_at},
                    ]),
                })
            except Exception:
                buyer_cache.update({key: pd.DataFrame() for key in ("buyer_forecast", "buyer_product_forecast", "inventory", "sales", "buyer_sources")})
        return buyer_cache

    def planning() -> dict[str, Any]:
        if not planning_cache:
            try:
                planning_cache.update(RetailPlanningService(engine).workspace(context.organization_id, context.facility_id))
            except Exception:
                planning_cache.update({"recommendations": [], "vendors": [], "open_purchase_orders": []})
        return planning_cache

    commercial = CommercialRepository(engine)

    def facility_orders() -> list[Any]:
        if "orders" not in commercial_cache:
            try:
                commercial_cache["orders"] = commercial.list_orders(context.organization_id, context.facility_id)
            except Exception:
                commercial_cache["orders"] = []
        return commercial_cache["orders"]

    def facility_order_lines() -> list[Any]:
        if "lines" not in commercial_cache:
            allowed_ids = {row.id for row in facility_orders()}
            try:
                commercial_cache["lines"] = [row for row in commercial.list_order_lines(context.organization_id) if row.commercial_order_id in allowed_ids]
            except Exception:
                commercial_cache["lines"] = []
        return commercial_cache["lines"]

    def purchase_orders() -> list[Any]:
        return [row for row in facility_orders() if str(getattr(row, "order_type", "")).casefold() == "purchase"]

    def purchase_order_lines() -> pd.DataFrame:
        purchase_ids = {row.id for row in purchase_orders()}
        rows = []
        for line in facility_order_lines():
            if line.commercial_order_id not in purchase_ids:
                continue
            rows.append({
                "id": line.id,
                "commercial_order_id": line.commercial_order_id,
                "product_id": line.product_id,
                "sku_snapshot": line.sku_snapshot,
                "description": line.description,
                "quantity": float(line.quantity or 0),
                "fulfilled_quantity": float(line.fulfilled_quantity or 0),
                "outstanding_quantity": max(0.0, float(line.quantity or 0) - float(line.fulfilled_quantity or 0)),
                "unit": line.unit,
                "unit_price": float(line.unit_price or 0),
            })
        return pd.DataFrame(rows)

    def purchase_receipts() -> pd.DataFrame:
        purchase_ids = {row.id for row in purchase_orders()}
        try:
            transactions = commercial.list_commercial_transactions(context.organization_id, context.facility_id)
        except Exception:
            transactions = []
        return _frame([row for row in transactions if row.commercial_order_id in purchase_ids and str(row.transaction_type).casefold() == "receipt"])

    def reg(**kwargs):
        registry.register(DatasetSpec(**kwargs))

    for key, description in (("inventory", "Current authorized retail inventory"), ("sales", "Authorized historical retail sales"), ("buyer_forecast", "Buyer forecast details"), ("buyer_product_forecast", "Buyer product-level forecast")):
        reg(key=key, domain="retail", description=description, loader=lambda access, k=key: _frame(buyer_data().get(k)), allowed_agents=RETAIL, required_capabilities=("retail",), allow_business_columns=True, freshness="active Data Hub source", max_tool_rows=50)
    reg(key="buyer_sources", domain="data_hub", description="Provenance for active Buyer source files", loader=lambda access: _frame(buyer_data().get("buyer_sources")), allowed_agents=RETAIL, required_capabilities=("retail",), allowed_columns=("dataset", "filename", "rows", "freshness"), freshness="active Data Hub metadata", max_tool_rows=20)

    reg(key="purchase_recommendations", domain="purchasing", description="Deterministic replenishment recommendations using durable retail planning policies", loader=lambda access: pd.DataFrame(planning().get("recommendations") or []), allowed_agents=("ops", "buyer", "purchasing", "inventory"), allowed_roles=PURCHASE_ROLES, required_capabilities=("retail",), allowed_columns=("product_id", "sku", "product_name", "category", "unit", "unit_cost", "on_hand", "inbound", "sold", "daily_velocity", "days_on_hand", "target_doh", "safety_stock", "reorder_point", "minimum_order_quantity", "case_pack", "velocity_window_days", "preferred_vendor_id", "preferred_vendor_name", "suggested_quantity", "suggested_cost", "needs_reorder"), freshness="live retail planning workspace", max_tool_rows=50)
    reg(key="vendors", domain="purchasing", description="Authorized vendor terms and identities", loader=lambda access: pd.DataFrame(planning().get("vendors") or []), allowed_agents=("ops", "buyer", "purchasing"), allowed_roles=PURCHASE_ROLES, required_capabilities=("retail",), allowed_columns=("id", "name", "license_or_registration", "payment_terms"), freshness="live commercial partner ledger", max_tool_rows=50)
    reg(key="purchase_orders", domain="purchasing", description="Facility-scoped purchase orders including due and fulfillment state", loader=lambda access: _frame(purchase_orders()), allowed_agents=("ops", "buyer", "purchasing", "inventory"), allowed_roles=PURCHASE_ROLES, required_capabilities=("retail",), allowed_columns=("id", "partner_id", "order_number", "order_type", "status", "order_date", "due_at", "currency", "payment_status", "created_at"), freshness="live commercial order ledger", max_tool_rows=50)
    reg(key="purchase_order_lines", domain="purchasing", description="Facility-scoped purchase-order lines with ordered, received and outstanding quantity", loader=lambda access: purchase_order_lines(), allowed_agents=("ops", "buyer", "purchasing", "inventory"), allowed_roles=PURCHASE_ROLES, required_capabilities=("retail",), allowed_columns=("id", "commercial_order_id", "product_id", "sku_snapshot", "description", "quantity", "fulfilled_quantity", "outstanding_quantity", "unit", "unit_price"), freshness="live commercial order ledger", max_tool_rows=50)
    reg(key="purchase_receipts", domain="receiving", description="Facility-scoped durable purchase receipts created by receiving/PO fulfillment", loader=lambda access: purchase_receipts(), allowed_agents=("ops", "buyer", "purchasing", "inventory"), allowed_roles=PURCHASE_ROLES, required_capabilities=("retail",), allowed_columns=("id", "lot_id", "transaction_type", "quantity_delta", "unit", "commercial_order_id", "commercial_order_line_id", "reference", "occurred_at"), sensitive_columns=("actor",), freshness="live inventory receipt ledger", max_tool_rows=50)

    def product_master(_access):
        with Session(engine) as session:
            rows = session.execute(select(Product, ProductMasterProfile).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(Product.organization_id == context.organization_id, Product.active.is_(True))).all()
            return pd.DataFrame([{
                "product_id": product.id, "sku": product.sku, "name": product.name, "item_type": product.item_type, "base_unit": product.base_unit,
                "unit_cost": product.unit_cost, "retail_price": product.retail_price, "upc": product.upc,
                "brand": profile.brand if profile else "", "category": profile.category if profile else "", "subcategory": profile.subcategory if profile else "",
                "strain": profile.strain if profile else "", "manufacturer": profile.manufacturer if profile else "", "product_format": profile.product_format if profile else "",
                "retail_enabled": profile.retail_enabled if profile else True, "production_enabled": profile.production_enabled if profile else True,
            } for product, profile in rows])
    reg(key="product_master", domain="catalog", description="Canonical organization-level DoobieLogic product catalog", loader=product_master, allowed_agents=("ops", "buyer", "purchasing", "inventory", "nomenclature", "repack", "coman", "commercial", "cultivation"), allowed_columns=("product_id", "sku", "name", "item_type", "base_unit", "unit_cost", "retail_price", "upc", "brand", "category", "subcategory", "strain", "manufacturer", "product_format", "retail_enabled", "production_enabled"), freshness="live product master", max_tool_rows=50)

    def data_hub(_access):
        rows = DataHubRepository(engine).list_history(context.organization_id, context.facility_id, limit=250)
        payload = []
        for row in rows:
            try:
                mapping = json.loads(row.mapping_json or "{}")
            except Exception:
                mapping = {}
            try:
                missing = json.loads(row.missing_fields_json or "[]")
            except Exception:
                missing = []
            payload.append({"dataset_key": row.dataset_key, "dataset_label": row.dataset_label, "filename": row.filename, "status": row.status, "row_count": row.row_count, "column_count": row.column_count, "quality": row.quality, "mapping_count": len(mapping), "mapping_complete": not bool(missing), "validation_errors": len(missing), "missing_fields": ", ".join(str(value) for value in missing[:20]), "activated_at": row.activated_at, "fingerprint": row.fingerprint})
        return pd.DataFrame(payload)
    reg(key="active_data_sources", domain="data_hub", description="Safe Data Hub source, schema, mapping, validation and provenance metadata", loader=data_hub, allowed_agents=("ops", "data_hub", "buyer", "purchasing", "inventory", "compliance"), allowed_columns=("dataset_key", "dataset_label", "filename", "status", "row_count", "column_count", "quality", "mapping_count", "mapping_complete", "validation_errors", "missing_fields", "activated_at", "fingerprint"), freshness="live Data Hub history", max_tool_rows=50)

    coman = ComanRepository(engine)
    production_specs = {
        "production_orders": (lambda access: _frame(coman.list_production_orders(context.organization_id, context.facility_id)), ("id", "order_number", "work_type", "customer_id", "product_name", "sku", "product_format", "requested_units", "due_at", "priority", "status", "source_lot_reference", "material_owner", "packaging_owner", "created_at")),
        "production_actuals": (lambda access: _frame(coman.list_production_actuals(context.organization_id, context.facility_id)), ("id", "production_order_id", "actual_units", "scrap_units", "rework_units", "actual_machine_hours", "actual_labor_hours", "completed_at")),
        "facility_machines": (lambda access: _frame(coman.list_facility_machines(context.organization_id, context.facility_id)), ("id", "machine_model_id", "asset_code", "display_name", "effective_rate", "rate_unit", "preferred_crew_size", "setup_minutes", "cleanup_minutes", "active")),
        "material_reservations": (lambda access: _frame(coman.list_material_reservations(context.organization_id, context.facility_id)), ("id", "production_order_id", "lot_id", "quantity", "unit", "status", "created_at")),
        "crew_availability": (lambda access: _frame(coman.list_crew_availability(context.organization_id, context.facility_id)), ("id", "work_date", "shift_name", "available_people", "shift_hours", "created_at", "updated_at")),
    }
    for key, (loader, columns) in production_specs.items():
        reg(key=key, domain="production", description=key.replace("_", " ").title(), loader=loader, allowed_agents=PRODUCTION, required_capabilities=("production",), allowed_columns=columns, freshness="live production repository", max_tool_rows=50)

    shared_inventory_agents = tuple(dict.fromkeys((*PRODUCTION, "cultivation")))
    shared_inventory_specs = {
        "products": (lambda access: _frame(coman.list_products(context.organization_id)), ("id", "sku", "name", "item_type", "base_unit", "unit_cost", "retail_price", "upc", "external_product_id", "active")),
        "inventory_lots": (lambda access: _frame(coman.list_inventory_lots(context.organization_id, context.facility_id)), ("id", "product_id", "lot_code", "compliance_package_id", "external_inventory_id", "barcode_value", "location_code", "status", "received_at", "expiration_at")),
        "inventory_transactions": (lambda access: _frame(coman.list_inventory_transactions(context.organization_id, context.facility_id, limit=500)), ("id", "lot_id", "transaction_type", "quantity_delta", "unit", "production_order_id", "commercial_order_id", "commercial_order_line_id", "reason", "reference", "occurred_at")),
    }
    for key, (loader, columns) in shared_inventory_specs.items():
        reg(key=key, domain="production_inventory", description=key.replace("_", " ").title(), loader=loader, allowed_agents=shared_inventory_agents, required_capabilities=("production", "cultivation"), allowed_columns=columns, sensitive_columns=("actor",), freshness="live production inventory repository", max_tool_rows=50)

    def boms(_access):
        with Session(engine) as session:
            boms = list(session.scalars(select(ProductBom).where(ProductBom.organization_id == context.organization_id, ProductBom.active.is_(True))))
            components = list(session.scalars(select(BomComponent).where(BomComponent.organization_id == context.organization_id)))
        return pd.DataFrame([{"bom_id": row.id, "output_product_id": row.output_product_id, "version": row.version, "output_quantity": row.output_quantity, "expected_loss_pct": row.expected_loss_pct, "component_count": sum(1 for item in components if item.bom_id == row.id)} for row in boms])
    reg(key="production_boms", domain="production", description="Bill-of-material and expected-loss metadata", loader=boms, allowed_agents=("ops", "coman", "repack"), required_capabilities=("production",), allowed_columns=("bom_id", "output_product_id", "version", "output_quantity", "expected_loss_pct", "component_count"), freshness="live production BOMs", max_tool_rows=50)
    reg(key="production_bom_components", domain="production", description="Organization BOM material requirements", loader=lambda access: _frame(Session(engine).scalars(select(BomComponent).where(BomComponent.organization_id == context.organization_id)).all()), allowed_agents=("ops", "coman", "repack"), required_capabilities=("production",), allowed_columns=("id", "bom_id", "input_product_id", "quantity", "unit", "scrap_pct"), freshness="live production BOMs", max_tool_rows=50)

    extraction = ExtractionRepository(engine)
    def extraction_raw() -> pd.DataFrame:
        if "raw" not in extraction_cache:
            try:
                extraction_cache["raw"] = _frame(extraction.list_runs(context.organization_id, context.facility_id, include_closed=True, limit=500))
            except Exception:
                extraction_cache["raw"] = pd.DataFrame()
        return extraction_cache["raw"]
    def extraction_derived(name: str) -> pd.DataFrame:
        if "derived" not in extraction_cache:
            extraction_cache["derived"] = build_extraction_derived_datasets({"extraction_runs": extraction_raw()})
        return _frame(extraction_cache["derived"].get(name))
    reg(key="extraction_runs", domain="extraction", description="Extraction runs and run outcomes", loader=lambda access: extraction_raw(), allowed_agents=("ops", "extraction"), required_capabilities=("production",), allow_business_columns=True, sensitive_columns=("actor", "created_by", "updated_by"), freshness="live extraction repository", max_tool_rows=50)
    reg(key="extraction_inventory", domain="extraction", description="Available extraction inventory lots", loader=lambda access: pd.DataFrame(extraction.list_available_lots(context.organization_id, context.facility_id)), allowed_agents=("ops", "extraction"), required_capabilities=("production",), allow_business_columns=True, freshness="live extraction inventory", max_tool_rows=50)
    for key in ("extraction_run_analysis", "extraction_method_summary", "extraction_qa_holds", "extraction_exceptions", "extraction_data_availability"):
        reg(key=key, domain="extraction", description=key.replace("_", " ").title(), loader=lambda access, k=key: extraction_derived(k), allowed_agents=("ops", "extraction"), required_capabilities=("production",), allow_business_columns=True, freshness="deterministic from live extraction runs", max_tool_rows=50)

    commercial_specs = {
        "trade_partners": (lambda access: _frame(commercial.list_trade_partners(context.organization_id)), ("id", "name", "partner_type", "license_or_registration", "payment_terms", "active")),
        "commercial_orders": (lambda access: _frame(facility_orders()), ("id", "partner_id", "order_number", "order_type", "status", "order_date", "due_at", "currency", "payment_status", "created_at")),
        "commercial_order_lines": (lambda access: _frame(facility_order_lines()), ("id", "commercial_order_id", "product_id", "position", "description", "sku_snapshot", "quantity", "fulfilled_quantity", "unit", "unit_price")),
        "order_allocations": (lambda access: _frame(commercial.list_allocations(context.organization_id, context.facility_id)), ("id", "commercial_order_id", "commercial_order_line_id", "lot_id", "quantity", "fulfilled_quantity", "status", "created_at")),
        "commercial_transactions": (lambda access: _frame(commercial.list_commercial_transactions(context.organization_id, context.facility_id)), ("id", "lot_id", "transaction_type", "quantity_delta", "unit", "commercial_order_id", "commercial_order_line_id", "reference", "occurred_at")),
    }
    for key, (loader, columns) in commercial_specs.items():
        reg(key=key, domain="commercial", description=key.replace("_", " ").title(), loader=loader, allowed_agents=COMMERCIAL, required_capabilities=("commercial",), allowed_columns=columns, sensitive_columns=("actor", "created_by", "updated_by", "contact_email", "contact_phone", "contact_name"), freshness="live commercial repository", max_tool_rows=50)

    def finance(_access):
        try:
            summary = CommercialFinanceService(engine).ar_summary(context.organization_id, context.facility_id)
            rows = summary.get("invoices") or []
            for row in rows:
                row["Total AR"] = summary.get("total_ar", 0.0)
            return pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()
    reg(key="commercial_finance", domain="commercial_finance", description="Authorized A/R status and aging without payment credentials", loader=finance, allowed_agents=("ops", "commercial", "commercial_finance"), required_capabilities=("commercial",), allowed_columns=("invoice_id", "Invoice", "Status", "Due", "Balance", "Days Past Due", "Total AR"), freshness="live commercial finance ledger", max_tool_rows=50)

    audits = InventoryAuditRepository(engine)
    audit_cache: dict[str, Any] = {}
    def audit_rows(_access):
        return _frame(audits.list_audits(context.organization_id, context.facility_id, operation_type=operation_type))
    def active_audit():
        if "audits" not in audit_cache:
            rows = audits.list_audits(context.organization_id, context.facility_id, operation_type=operation_type)
            audit_cache["audits"] = rows
            audit_cache["active"] = next((row for row in rows if getattr(row, "status", "") in {"in_progress", "paused", "stopped"}), rows[0] if rows else None)
        return audit_cache.get("active")
    audit_caps = ("retail",) if operation_type == "retail" else ("production", "cultivation")
    reg(key="inventory_audits", domain="audit", description=f"{operation_type.title()} inventory audit sessions", loader=audit_rows, allowed_agents=("ops", "audit", "inventory", "coman", "cultivation"), required_capabilities=audit_caps, allowed_columns=("id", "audit_number", "operation_type", "scope_label", "status", "blind_count", "recount_tolerance", "started_at", "paused_at", "stopped_at", "completed_at", "created_at"), freshness="live audit repository", max_tool_rows=50)
    reg(key="audit_lines", domain="audit", description="Current audit expected/actual count lines", loader=lambda access: _frame(audits.list_lines(context.organization_id, active_audit().id)) if active_audit() else pd.DataFrame(), allowed_agents=("ops", "audit", "inventory", "coman", "cultivation"), required_capabilities=audit_caps, allowed_columns=("id", "audit_id", "lot_id", "expected_quantity", "counted_quantity", "unit", "status", "last_scanned_at", "created_at", "updated_at"), freshness="live active/most-recent audit", max_tool_rows=50)
    reg(key="audit_scans", domain="audit", description="Bounded scan events for the current audit", loader=lambda access: _frame(audits.list_scans(context.organization_id, active_audit().id)) if active_audit() else pd.DataFrame(), allowed_agents=("ops", "audit", "inventory", "coman", "cultivation"), required_capabilities=audit_caps, allowed_columns=("id", "audit_id", "audit_line_id", "scan_value", "quantity", "scanned_at", "match_type"), sensitive_columns=("scanned_by", "actor", "user_id"), freshness="live active/most-recent audit", max_tool_rows=50)

    cultivation = CultivationService(engine)
    reg(key="cultivation_plants", domain="cultivation", description="Authorized cultivation plants and lifecycle state", loader=lambda access: _frame(cultivation.list_plants(context.organization_id, context.facility_id)), allowed_agents=CULTIVATION, required_capabilities=("cultivation",), allowed_columns=("id", "plant_tag", "strain_name", "phase", "room_code", "source_lot_id", "mother_plant_tag", "planted_at", "estimated_harvest_date", "retired_at"), freshness="live cultivation repository", max_tool_rows=50)
    def plant_events(_access):
        with Session(engine) as session:
            rows = list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.organization_id == context.organization_id, CultivationPlantEvent.facility_id == context.facility_id).order_by(CultivationPlantEvent.occurred_at.desc()).limit(500)))
        return _frame(rows)
    reg(key="cultivation_plant_events", domain="cultivation", description="Cultivation lifecycle transitions without employee identity", loader=plant_events, allowed_agents=CULTIVATION, required_capabilities=("cultivation",), allowed_columns=("id", "plant_id", "event_type", "from_value", "to_value", "reason", "notes", "occurred_at"), sensitive_columns=("actor",), freshness="live cultivation event ledger", max_tool_rows=50)

    def business_context(_access):
        with Session(engine) as session:
            org = session.get(Organization, context.organization_id)
            facility = session.get(Facility, context.facility_id)
        if not org or not facility or facility.organization_id != context.organization_id:
            return pd.DataFrame()
        return pd.DataFrame([{"organization": org.name, "facility": facility.name, "facility_code": facility.code, "timezone": facility.timezone_name, "license_number": facility.license_number, "license_type": facility.license_type, "retail_enabled": facility.retail_enabled, "production_enabled": facility.production_enabled, "cultivation_enabled": facility.cultivation_enabled, "commercial_enabled": facility.commercial_enabled}])
    reg(key="business_context", domain="context", description="Non-sensitive authorized organization/facility operating context", loader=business_context, allowed_agents=ALL, allowed_columns=("organization", "facility", "facility_code", "timezone", "license_number", "license_type", "retail_enabled", "production_enabled", "cultivation_enabled", "commercial_enabled"), freshness="live facility configuration", max_tool_rows=5)

    return registry
