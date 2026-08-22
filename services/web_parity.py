"""Independent durable-data versus FastAPI parity checks for web cutover."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from math import isclose
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from backend.app.services.audits import AuditService
from modules.coman.models import (
    Facility,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Product,
    RetailSale,
    utc_now,
)
from modules.commercial.repository import CommercialRepository
from modules.cultivation.service import CultivationService
from modules.data_hub_repository import DataHubRepository
from modules.extraction.repository import ExtractionRepository
from modules.package_studio.service import PackageStudioService
from modules.product_master.models import ProductMasterProfile
from modules.production_erp.service import ProductionERPService

JsonGetter = Callable[[str], Any]


def _ids(rows: list[Any], key: str = "id") -> list[str]:
    return sorted(str(row[key] if isinstance(row, dict) else getattr(row, key)) for row in rows)


def run_web_parity(engine: Engine, organization_id: str, facility_id: str, get_json: JsonGetter) -> dict[str, Any]:
    """Compare API responses with direct, tenant-scoped durable reads."""
    checks: list[dict[str, Any]] = []

    def check(name: str, expected: Any, actual: Any, *, numeric: bool = False) -> None:
        passed = isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-7) if numeric else expected == actual
        checks.append({"name": name, "passed": passed, "expected": expected, "actual": actual})

    with Session(engine) as session:
        facility = session.scalar(select(Facility).where(Facility.id == facility_id, Facility.organization_id == organization_id))
        if not facility:
            raise ValueError("Parity facility was not found in the selected organization.")
        lot_count = int(session.scalar(select(func.count()).select_from(InventoryLot).where(InventoryLot.organization_id == organization_id, InventoryLot.facility_id == facility_id)) or 0)
        balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.organization_id == organization_id, InventoryTransaction.facility_id == facility_id)) or 0)
        reserved = float(session.scalar(select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(MaterialReservation.organization_id == organization_id, MaterialReservation.facility_id == facility_id, MaterialReservation.status == "reserved")) or 0)
        product_rows = list(session.execute(select(Product, ProductMasterProfile).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(Product.organization_id == organization_id, Product.active.is_(True))))
        retail_product_ids = sorted(row.id for row, profile in product_rows if profile is None or profile.retail_enabled)
        production_product_ids = sorted(row.id for row, profile in product_rows if profile is None or profile.production_enabled)
        since = utc_now() - timedelta(days=30)
        sales_units, net_sales = session.execute(select(func.coalesce(func.sum(RetailSale.quantity), 0.0), func.coalesce(func.sum(RetailSale.net_sales), 0.0)).where(RetailSale.organization_id == organization_id, RetailSale.facility_id == facility_id, RetailSale.sold_at >= since, RetailSale.sold_at <= utc_now())).one()

    context = get_json("/api/v1/account/context")
    expected_capabilities = {"retail": bool(facility.retail_enabled), "production": bool(facility.production_enabled), "cultivation": bool(facility.cultivation_enabled), "commercial": bool(facility.commercial_enabled)}
    check("account.facility", facility_id, context["facility_id"])
    check("account.capabilities", expected_capabilities, context["capabilities"])
    check("account.license_number", facility.license_number, context["facility"]["license_number"])

    for operation, enabled in (("retail", facility.retail_enabled), ("production", facility.production_enabled)):
        if not enabled:
            continue
        inventory = get_json(f"/api/v1/inventory/{operation}/packages")
        check(f"{operation}.inventory.package_count", lot_count, inventory["summary"]["package_count"])
        check(f"{operation}.inventory.balance", balance, inventory["summary"]["available_quantity"], numeric=True)
        check(f"{operation}.inventory.reserved", reserved, inventory["summary"]["reserved_quantity"], numeric=True)
        expected_products = retail_product_ids if operation == "retail" else production_product_ids
        catalog = get_json(f"/api/v1/product-master?operation={operation}&status=active")
        check(f"{operation}.product_master.ids", expected_products, _ids(catalog))
        audits = get_json(f"/api/v1/inventory/{operation}/audits")
        check(f"{operation}.audits.ids", _ids(AuditService(engine).list(organization_id, facility_id, operation)), _ids(audits))

    if facility.retail_enabled:
        trends = get_json("/api/v1/retail-insights/trends?days=30")
        check("retail.sales.units_30d", float(sales_units or 0), trends["summary"]["units"], numeric=True)
        check("retail.sales.net_sales_30d", float(net_sales or 0), trends["summary"]["net_sales"], numeric=True)

    if facility.production_enabled:
        production = get_json("/api/v1/production/orders")
        check("production.order.ids", _ids(ProductionERPService(engine).queue_summary(organization_id, facility_id), "order_id"), _ids(production, "order_id"))
        extraction = get_json("/api/v1/extraction/runs")
        check("extraction.run.ids", _ids(ExtractionRepository(engine).list_runs(organization_id, facility_id)), _ids(extraction))
        studio = PackageStudioService(engine)
        studio_api = get_json("/api/v1/package-studio/workspace")
        check("package_studio.lot.ids", _ids(studio.list_available_lots(organization_id, facility_id), "lot_id"), _ids(studio_api["lots"], "lot_id"))
        check("package_studio.product.ids", _ids(studio.list_products(organization_id), "product_id"), _ids(studio_api["products"], "product_id"))
        check("package_studio.run.ids", _ids(studio.recent_runs(organization_id, facility_id)), _ids(studio_api["runs"]))
        if facility.cultivation_enabled:
            plants = get_json("/api/v1/inventory/production/plants")
            check("cultivation.plant.ids", _ids(CultivationService(engine).list_plants(organization_id, facility_id)), _ids(plants))

    if facility.commercial_enabled:
        orders = get_json("/api/v1/commercial/orders?open_only=false")
        check("commercial.order.ids", _ids(CommercialRepository(engine).list_orders(organization_id, facility_id)), _ids(orders))

    data_hub = get_json("/api/v1/data-hub/datasets")
    check("data_hub.import.ids", _ids(DataHubRepository(engine).list_history(organization_id, facility_id)), _ids(data_hub["history"]))
    failed = [row for row in checks if not row["passed"]]
    return {"passed": not failed, "organization_id": organization_id, "facility_id": facility_id, "check_count": len(checks), "failed_count": len(failed), "checks": checks}
