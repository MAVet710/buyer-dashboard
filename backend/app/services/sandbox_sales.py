from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, delete, func, inspect, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization, Product, RetailSale
from modules.data_hub_repository import DataHubRepository

SANDBOX_ORGANIZATION_SLUG = "dev-sandbox"
SANDBOX_FACILITY_CODE = "SANDBOX"
SANDBOX_SALES_DATASET_KEY = "sandbox_buyer_sales"
SANDBOX_SALES_SOURCE_SYSTEM = "sandbox"
SANDBOX_SALES_WINDOW_DAYS = 120

_REQUIRED_SALES_COLUMNS = {
    "Product Name",
    "Quantity Sold",
    "Net Sales",
    "Order ID",
    "Order Time",
    "SKU",
}
_REQUIRED_TABLES = {
    "coman_organizations",
    "coman_facilities",
    "coman_products",
    "data_hub_imports",
    "retail_sales",
}


def _number(value: object, *, field: str, row_number: int) -> float:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Sandbox sales row {row_number} has an invalid {field}: {value!r}") from exc


def _sold_at(value: object, *, timezone_name: str, row_number: int) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Sandbox sales row {row_number} is missing Order Time.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Sandbox sales row {row_number} has an invalid Order Time: {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name or "America/New_York"))
    return parsed.astimezone(timezone.utc)


def sync_sandbox_retail_sales(engine: Engine) -> dict[str, object]:
    """Normalize the persisted DEV Sandbox buyer-sales CSV into ``retail_sales``.

    The public sandbox source remains the canonical synthetic dataset.  This sync
    makes the durable inventory/analytics APIs consume the same unit-sales history
    as Buyer parity instead of showing zero velocity.  It is intentionally scoped
    to the canonical DEV Sandbox tenant and is idempotent by source fingerprint.
    """

    tables = set(inspect(engine).get_table_names())
    missing_tables = sorted(_REQUIRED_TABLES - tables)
    if missing_tables:
        return {"synced": False, "reason": "schema_unavailable", "missing_tables": missing_tables}

    with Session(engine) as session:
        organization = session.scalar(
            select(Organization).where(Organization.slug == SANDBOX_ORGANIZATION_SLUG)
        )
        if organization is None:
            return {"synced": False, "reason": "sandbox_organization_missing"}
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == SANDBOX_FACILITY_CODE,
            )
        )
        if facility is None:
            return {"synced": False, "reason": "sandbox_facility_missing"}
        products = list(
            session.scalars(
                select(Product).where(
                    Product.organization_id == organization.id,
                    Product.active.is_(True),
                )
            )
        )
        by_sku = {str(product.sku or "").strip().casefold(): product for product in products if str(product.sku or "").strip()}
        organization_id = organization.id
        facility_id = facility.id
        timezone_name = facility.timezone_name or "America/New_York"

    source = next(
        (
            record
            for record in DataHubRepository(engine).list_active_sources(organization_id, facility_id)
            if record.dataset_key == SANDBOX_SALES_DATASET_KEY
        ),
        None,
    )
    if source is None:
        return {"synced": False, "reason": "sandbox_sales_source_missing"}
    if source.row_count <= 0:
        raise ValueError("Persisted DEV Sandbox buyer sales source is empty.")

    import_batch_id = f"sandbox-{source.fingerprint[:24]}"
    with Session(engine) as session:
        current_batch_count = int(
            session.scalar(
                select(func.count(RetailSale.id)).where(
                    RetailSale.organization_id == organization_id,
                    RetailSale.facility_id == facility_id,
                    RetailSale.source_system == SANDBOX_SALES_SOURCE_SYSTEM,
                    RetailSale.import_batch_id == import_batch_id,
                )
            )
            or 0
        )
        sandbox_sales_count = int(
            session.scalar(
                select(func.count(RetailSale.id)).where(
                    RetailSale.organization_id == organization_id,
                    RetailSale.facility_id == facility_id,
                    RetailSale.source_system == SANDBOX_SALES_SOURCE_SYSTEM,
                )
            )
            or 0
        )
    if current_batch_count == source.row_count and sandbox_sales_count == current_batch_count:
        return {
            "synced": False,
            "reason": "already_current",
            "rows": current_batch_count,
            "import_batch_id": import_batch_id,
        }

    try:
        text = source.payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Persisted DEV Sandbox buyer sales source is not UTF-8 CSV.") from exc
    reader = csv.DictReader(StringIO(text))
    columns = set(reader.fieldnames or [])
    missing_columns = sorted(_REQUIRED_SALES_COLUMNS - columns)
    if missing_columns:
        raise ValueError(
            "Persisted DEV Sandbox buyer sales is missing required columns: "
            + ", ".join(missing_columns)
        )

    rows: list[RetailSale] = []
    local_dates = []
    unmapped_skus: set[str] = set()
    for index, row in enumerate(reader, start=1):
        sku = str(row.get("SKU") or "").strip()
        product = by_sku.get(sku.casefold())
        if product is None:
            unmapped_skus.add(sku or "<blank>")
            continue
        quantity = _number(row.get("Quantity Sold"), field="Quantity Sold", row_number=index)
        if quantity <= 0:
            raise ValueError(f"Sandbox sales row {index} must have positive Quantity Sold.")
        net_sales = _number(row.get("Net Sales"), field="Net Sales", row_number=index)
        if net_sales < 0:
            raise ValueError(f"Sandbox sales row {index} cannot have negative Net Sales.")
        sold_at = _sold_at(row.get("Order Time"), timezone_name=timezone_name, row_number=index)
        local_dates.append(sold_at.astimezone(ZoneInfo(timezone_name)).date())
        order_id = str(row.get("Order ID") or "").strip() or f"ORDER-{index:07d}"
        source_record_id = f"{order_id}:{sku}:{index:06d}"
        rows.append(
            RetailSale(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product.id,
                source_system=SANDBOX_SALES_SOURCE_SYSTEM,
                source_record_id=source_record_id,
                import_batch_id=import_batch_id,
                sku=sku,
                product_name=str(row.get("Product Name") or product.name).strip() or product.name,
                quantity=quantity,
                net_sales=net_sales,
                sold_at=sold_at,
                imported_by="DEV Sandbox",
            )
        )

    if unmapped_skus:
        sample = ", ".join(sorted(unmapped_skus)[:8])
        raise ValueError(
            f"DEV Sandbox sales cannot be normalized because {len(unmapped_skus)} SKU(s) are missing from the product master: {sample}"
        )
    if len(rows) != source.row_count:
        raise ValueError(
            f"DEV Sandbox sales row-count mismatch: source declares {source.row_count}, parsed {len(rows)}."
        )
    if not local_dates:
        raise ValueError("DEV Sandbox sales source parsed with no dated sales rows.")
    span_days = (max(local_dates) - min(local_dates)).days + 1
    if span_days != SANDBOX_SALES_WINDOW_DAYS:
        raise ValueError(
            f"DEV Sandbox sales must span exactly {SANDBOX_SALES_WINDOW_DAYS} days; found {span_days}."
        )

    with Session(engine) as session, session.begin():
        session.execute(
            delete(RetailSale).where(
                RetailSale.organization_id == organization_id,
                RetailSale.facility_id == facility_id,
                RetailSale.source_system == SANDBOX_SALES_SOURCE_SYSTEM,
            )
        )
        session.add_all(rows)

    return {
        "synced": True,
        "reason": "refreshed",
        "rows": len(rows),
        "units": round(sum(float(row.quantity) for row in rows), 2),
        "net_sales": round(sum(float(row.net_sales) for row in rows), 2),
        "products": len({row.product_id for row in rows}),
        "sales_window_days": span_days,
        "import_batch_id": import_batch_id,
    }
