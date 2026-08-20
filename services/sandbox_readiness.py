"""Runtime readiness checks for the unified DEV Sandbox.

The sandbox is useful only when every workspace receives internally consistent,
synthetic data. These checks validate operational completeness and provenance,
not cannabis regulatory truth.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

SANDBOX_ORGANIZATION_NAME = "DEV Sandbox"
SANDBOX_ORGANIZATION_SLUG = "dev-sandbox"
SANDBOX_FACILITY_NAME = "Sandbox Facility"
SANDBOX_FACILITY_CODE = "SANDBOX"
SANDBOX_TIMEZONE = "America/New_York"
SANDBOX_SALES_WINDOW_DAYS = 120

REQUIRED_UPLOADS = {
    "buyer_catalog",
    "buyer_inventory",
    "buyer_sales",
    "buyer_extra_sales",
    "buyer_quarantine",
    "delivery_manifest",
    "delivery_sales",
    "compliance_sources",
    "extraction_inventory",
    "extraction_runs",
    "extraction_jobs",
    "nomenclature_catalog",
    "nomenclature_manifest",
    "commercial_partners",
    "commercial_orders",
    "commercial_order_lines",
    "commercial_ledger",
    "production_orders",
    "production_machines",
    "production_crew",
    "purchasing_budget",
}

REQUIRED_FRAMES = {
    "catalog",
    "inventory",
    "sales",
    "manifest",
    "quarantine",
    "compliance",
    "detail",
    "detail_product",
    "production_inventory",
    "extraction_inventory",
    "extraction_runs",
    "extraction_jobs",
    "nomenclature_catalog",
    "nomenclature_manifest",
    "commercial_partners",
    "commercial_orders",
    "commercial_order_lines",
    "commercial_ledger",
    "production_orders_export",
    "production_machines_export",
    "production_crew_export",
    "budget",
}

RETAIL_INVENTORY_REQUIRED_COLUMNS = {
    "Product Name", "SKU", "Category", "Inventory Class", "Item Type", "Status",
    "Available", "Reserved", "On Hand Total", "Inventory Unit", "Batch", "Room",
    "Cost", "Med Price", "Brand", "Vendor", "Package Size", "Received Date",
    "Expiration Date", "Strain", "Package ID", "METRC Package ID", "COA ID",
    "Lab Status", "Source Production Order", "Source Extraction Batch",
}

PRODUCTION_INVENTORY_REQUIRED_COLUMNS = {
    "received_date", "material_name", "material_type", "inventory_class", "item_type",
    "inventory_unit", "strain", "source_vendor", "batch_id_internal", "metrc_package_id",
    "current_weight_g", "reserved_weight_g", "available_weight_g", "cost_per_g",
    "total_cost", "status", "lab_status", "storage_location", "source_extraction_batch",
    "facility_name", "license_number",
}

SALES_REQUIRED_COLUMNS = {
    "Product Name", "Master Category", "Quantity Sold", "Gross Sales", "Net Sales",
    "Unit Cost", "COGS", "Gross Profit", "Order ID", "Order Time", "Report Start",
    "Report End", "SKU", "Package ID", "Brand", "Vendor", "Store",
}

EXTRACTION_REQUIRED_COLUMNS = {
    "run_date",
    "batch_id_internal",
    "method",
    "input_material_type",
    "input_weight_g",
    "intermediate_output_g",
    "finished_output_g",
    "yield_pct",
    "operator",
    "machine_line",
    "status",
    "coa_status",
    "qa_hold",
    "est_revenue_usd",
    "cogs_usd",
    "input_terpene_pct",
    "finished_terpene_pct",
    "terpene_retention_pct",
    "turnaround_hours",
    "rework_required",
    "residual_solvent_status",
    "downtime_minutes",
    "settings_verified",
    "sop_reference",
}


def _frame(payload: dict[str, Any], key: str) -> pd.DataFrame:
    value = payload.get(key)
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _check_columns(
    frame: pd.DataFrame,
    required: set[str],
    *,
    check_name: str,
    label: str,
    checks: dict[str, bool],
    issues: list[str],
) -> None:
    missing = required - set(map(str, frame.columns))
    checks[check_name] = not missing
    if missing:
        issues.append(f"{label} is missing required fields: " + ", ".join(sorted(missing)))


def validate_sandbox_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a structured readiness report for a generated sandbox payload."""
    issues: list[str] = []
    checks: dict[str, bool] = {}

    profile = dict(payload.get("company_profile") or {})
    identity_checks = {
        "organization_name": profile.get("company_name") == SANDBOX_ORGANIZATION_NAME,
        "store_name": profile.get("store_name") == SANDBOX_FACILITY_NAME,
        "facility_name": profile.get("facility_name") == SANDBOX_FACILITY_NAME,
        "state": profile.get("state") == "MA",
    }
    checks.update({f"identity.{key}": value for key, value in identity_checks.items()})
    for key, ok in identity_checks.items():
        if not ok:
            issues.append(f"Sandbox identity mismatch: {key}={profile.get(key)!r}")

    uploads = set((payload.get("uploads") or {}).keys())
    uploads_ok = REQUIRED_UPLOADS.issubset(uploads)
    checks["uploads.complete"] = uploads_ok
    if not uploads_ok:
        issues.append("Missing sandbox uploads: " + ", ".join(sorted(REQUIRED_UPLOADS - uploads)))

    for key in sorted(REQUIRED_FRAMES):
        frame = _frame(payload, key)
        ok = not frame.empty
        checks[f"frame.{key}"] = ok
        if not ok:
            issues.append(f"Sandbox frame is empty or missing: {key}")

    inventory = _frame(payload, "inventory")
    if not inventory.empty:
        _check_columns(
            inventory,
            RETAIL_INVENTORY_REQUIRED_COLUMNS,
            check_name="retail_inventory.required_columns",
            label="Retail sandbox inventory",
            checks=checks,
            issues=issues,
        )
        classes = set(inventory.get("Inventory Class", pd.Series(dtype=str)).astype(str))
        finished_ready = "Finished Retail" in classes
        checks["retail_inventory.finished_retail"] = finished_ready
        if not finished_ready:
            issues.append("Retail sandbox inventory does not contain finished retail-ready products")
        package_ids = inventory.get("Package ID", pd.Series(dtype=str)).astype(str).str.strip()
        checks["retail_inventory.package_ids"] = bool(package_ids.ne("").all())
        if not package_ids.ne("").all():
            issues.append("Retail sandbox inventory contains products without package IDs")

    production_inventory = _frame(payload, "production_inventory")
    if not production_inventory.empty:
        _check_columns(
            production_inventory,
            PRODUCTION_INVENTORY_REQUIRED_COLUMNS,
            check_name="production_inventory.required_columns",
            label="Production sandbox inventory",
            checks=checks,
            issues=issues,
        )
        has_bulk = production_inventory.get(
            "inventory_class", pd.Series(dtype=str)
        ).astype(str).str.contains("Bulk", case=False, na=False).any()
        checks["production_inventory.bulk_or_wip"] = bool(has_bulk)
        if not has_bulk:
            issues.append("Production sandbox inventory does not contain bulk/WIP packages")
        balances_ok = (
            pd.to_numeric(production_inventory.get("current_weight_g"), errors="coerce").fillna(-1).ge(0).all()
            and pd.to_numeric(production_inventory.get("reserved_weight_g"), errors="coerce").fillna(-1).ge(0).all()
            and pd.to_numeric(production_inventory.get("available_weight_g"), errors="coerce").fillna(-1).ge(0).all()
        )
        checks["production_inventory.nonnegative_balances"] = bool(balances_ok)
        if not balances_ok:
            issues.append("Production sandbox inventory contains invalid material balances")

    sales = _frame(payload, "sales")
    if not sales.empty:
        _check_columns(
            sales,
            SALES_REQUIRED_COLUMNS,
            check_name="retail_sales.required_columns",
            label="Retail sandbox sales",
            checks=checks,
            issues=issues,
        )
        if "Store" in sales.columns:
            store_match = sales["Store"].astype(str).eq(SANDBOX_FACILITY_NAME).all()
            checks["retail.store_identity"] = bool(store_match)
            if not store_match:
                issues.append("Retail sales Store values do not consistently match Sandbox Facility")
        order_times = pd.to_datetime(sales.get("Order Time"), errors="coerce").dropna()
        span_days = (
            int((order_times.max().normalize() - order_times.min().normalize()).days) + 1
            if not order_times.empty
            else 0
        )
        checks["retail_sales.120_day_window"] = span_days == SANDBOX_SALES_WINDOW_DAYS
        if span_days != SANDBOX_SALES_WINDOW_DAYS:
            issues.append(
                f"Retail sandbox sales must span exactly {SANDBOX_SALES_WINDOW_DAYS} days; found {span_days}"
            )
        report_start = pd.to_datetime(sales.get("Report Start"), errors="coerce").dropna()
        report_end = pd.to_datetime(sales.get("Report End"), errors="coerce").dropna()
        explicit_window_ok = bool(
            not report_start.empty
            and not report_end.empty
            and int((report_end.max().normalize() - report_start.min().normalize()).days) + 1
            == SANDBOX_SALES_WINDOW_DAYS
        )
        checks["retail_sales.explicit_report_window"] = explicit_window_ok
        if not explicit_window_ok:
            issues.append("Retail sandbox sales reporting boundaries are not a 120-day window")

    runs = _frame(payload, "extraction_runs")
    if not runs.empty:
        _check_columns(
            runs,
            EXTRACTION_REQUIRED_COLUMNS,
            check_name="extraction.required_columns",
            label="Extraction sandbox",
            checks=checks,
            issues=issues,
        )
        if "license_name" in runs.columns:
            facility_match = runs["license_name"].astype(str).eq(SANDBOX_FACILITY_NAME).all()
            checks["extraction.facility_identity"] = bool(facility_match)
            if not facility_match:
                issues.append("Extraction run license_name does not consistently match Sandbox Facility")

    compliance = _frame(payload, "compliance")
    if not compliance.empty:
        synthetic_citations = compliance.get(
            "source_citation", pd.Series("", index=compliance.index)
        ).astype(str).str.startswith("SYNTHETIC-DEMO-").all()
        demo_review = compliance.get(
            "review_status", pd.Series("", index=compliance.index)
        ).astype(str).str.casefold().eq("demo-only").all()
        invalid_urls = compliance.get(
            "source_url", pd.Series("", index=compliance.index)
        ).astype(str).str.contains("example.invalid", regex=False).all()
        compliance_ok = bool(synthetic_citations and demo_review and invalid_urls)
        checks["compliance.synthetic_only"] = compliance_ok
        if not compliance_ok:
            issues.append("Sandbox compliance rows are not consistently marked synthetic/demo-only")

    return {
        "ready": not issues,
        "issues": issues,
        "checks": checks,
        "organization": SANDBOX_ORGANIZATION_NAME,
        "organization_slug": SANDBOX_ORGANIZATION_SLUG,
        "facility": SANDBOX_FACILITY_NAME,
        "facility_code": SANDBOX_FACILITY_CODE,
        "timezone": SANDBOX_TIMEZONE,
        "sales_window_days": SANDBOX_SALES_WINDOW_DAYS,
    }
