"""Runtime readiness checks for the unified DEV Sandbox.

The sandbox is useful only when every workspace receives internally consistent,
synthetic data.  These checks deliberately validate data presence and provenance,
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

REQUIRED_UPLOADS = {
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
        issues.append(
            "Missing sandbox uploads: " + ", ".join(sorted(REQUIRED_UPLOADS - uploads))
        )

    for key in sorted(REQUIRED_FRAMES):
        frame = _frame(payload, key)
        ok = not frame.empty
        checks[f"frame.{key}"] = ok
        if not ok:
            issues.append(f"Sandbox frame is empty or missing: {key}")

    runs = _frame(payload, "extraction_runs")
    if not runs.empty:
        missing = EXTRACTION_REQUIRED_COLUMNS - set(map(str, runs.columns))
        checks["extraction.required_columns"] = not missing
        if missing:
            issues.append(
                "Extraction sandbox is missing required fields: " + ", ".join(sorted(missing))
            )
        if "license_name" in runs.columns:
            facility_match = runs["license_name"].astype(str).eq(SANDBOX_FACILITY_NAME).all()
            checks["extraction.facility_identity"] = bool(facility_match)
            if not facility_match:
                issues.append("Extraction run license_name does not consistently match Sandbox Facility")

    sales = _frame(payload, "sales")
    if not sales.empty and "Store" in sales.columns:
        store_match = sales["Store"].astype(str).eq(SANDBOX_FACILITY_NAME).all()
        checks["retail.store_identity"] = bool(store_match)
        if not store_match:
            issues.append("Retail sales Store values do not consistently match Sandbox Facility")

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
    }
