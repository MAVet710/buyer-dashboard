"""Translate Co-Man optimizer recommendations into editable production orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def build_recommended_order_prefill(
    recommendation: dict[str, Any],
    work_type_label: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build safe form defaults without committing an advisory recommendation."""
    created = created_at or datetime.now()
    is_external = str(work_type_label or "").strip().lower().startswith("external")
    units = max(1, int(recommendation.get("units") or 1))
    product_name = str(recommendation.get("product") or "Recommended production run").strip()
    product_format = str(recommendation.get("format") or "Other").strip()
    allocated_g = max(0.0, float(recommendation.get("allocated_g") or 0.0))
    cases = max(0, int(recommendation.get("cases") or 0))
    profit = float(recommendation.get("profit") or 0.0)
    margin_pct = float(recommendation.get("margin_pct") or 0.0)
    machine_hours = max(0.0, float(recommendation.get("machine_hours") or 0.0))
    hand_labor_hours = max(0.0, float(recommendation.get("hand_labor_hours") or 0.0))

    notes = (
        "Created from the weight-based production optimizer. "
        f"Planned bulk allocation: {allocated_g:,.1f} g; "
        f"recommended cases: {cases:,}; "
        f"estimated machine time: {machine_hours:,.1f} hr; "
        f"estimated hand labor: {hand_labor_hours:,.1f} hr; "
        f"estimated contribution profit: ${profit:,.2f} ({margin_pct:,.1f}% margin). "
        "Review assumptions, customer requirements, and available inventory before scheduling."
    )

    return {
        "order_number": f"COM-{created:%Y%m%d-%H%M%S}",
        "work_type": "External" if is_external else "Internal",
        "requested_units": units,
        "product_name": product_name,
        "product_format": product_format,
        "sku": "",
        "due_date": date(created.year, created.month, created.day) + timedelta(days=7),
        "priority": "Normal",
        "source_lot": "",
        "material_owner": "Customer" if is_external else "Internal",
        "packaging_owner": "Internal",
        "notes": notes,
    }

