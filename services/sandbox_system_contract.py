"""App-wide data contract for the canonical DEV Sandbox.

Every operational surface must resolve to either the living synthetic session
payload or durable rows scoped to ``dev-sandbox`` / ``SANDBOX``. Platform
controls (user admin, credentials, location settings) are intentionally not fake
business datasets. The contract is DEV-only and also forces tenant-operational
data sources away from live Dutchie mode while the sandbox is active.
"""
from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Mapping, MutableMapping

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.demo_data import (
    DEMO_DATA_VERSION as COMAN_DEMO_DATA_VERSION,
    DEMO_FACILITY_CODE,
    DEMO_ORGANIZATION_SLUG,
    ensure_coman_demo_dataset,
)
from modules.coman.models import (
    AuditEvent,
    BomComponent,
    CommercialOrder,
    CommercialOrderLine,
    CrewAvailability,
    Facility,
    FacilityMachine,
    HandLaborArea,
    InventoryAudit,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Organization,
    Product,
    ProductBom,
    ProductionActual,
    ProductionOrder,
    TradePartner,
)
from services.sandbox_readiness import REQUIRED_UPLOADS
from services.sandbox_market_seed import (
    market_sandbox_readiness,
    reset_market_sandbox_dataset,
    seed_market_sandbox,
)

SANDBOX_DATA_MODE = "📁 Uploads"

# These are the user-facing operational systems that rely on the living session
# payload. Durable/core systems are checked separately below.
SESSION_SYSTEM_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "Operations Home": ("demo_company_profile", "inv_raw_df", "sales_raw_df"),
    "Inventory": ("inv_raw_df", "active_inventory_df"),
    "Slow Movers": ("detail_product_cached_df",),
    "MA Flower Equivalency": ("inv_raw_df",),
    "Buying Recommendations": ("detail_product_cached_df", "sales_raw_df"),
    "Delivery Performance": ("delivery_manifest_df", "delivery_sales_df"),
    "Purchase Orders": ("inv_raw_df", "sales_raw_df"),
    "Buying Budget": ("demo_budget_df",),
    "Sales & Category Trends": ("sales_raw_df",),
    "Compliance Q&A": ("compliance_sources_df",),
    "Product Name Mapper": (
        "demo_nomenclature_catalog_df",
        "demo_nomenclature_manifest_df",
    ),
    "White Label / Repack": ("white_label_package_plan",),
    "Data Hub": ("demo_upload_catalog",),
    "Extraction compatibility data": (
        "ecc_inventory_log",
        "ecc_run_log",
        "ecc_client_jobs",
    ),
    "Commercial compatibility data": (
        "demo_commercial_partners_df",
        "demo_commercial_orders_df",
        "demo_commercial_order_lines_df",
    ),
    "Production compatibility data": (
        "demo_production_orders_df",
        "demo_production_machines_df",
        "demo_production_crew_df",
    ),
}

CORE_SYSTEM_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "Inventory Ledger": ("products", "inventory_lots", "inventory_transactions"),
    "Inventory Audits": ("inventory_audits",),
    "Co-Man Production": (
        "production_orders",
        "product_boms",
        "bom_components",
        "material_reservations",
        "production_actuals",
        "facility_machines",
        "crew_availability",
        "hand_labor_areas",
    ),
    "Orders & Fulfillment": (
        "commercial_orders",
        "commercial_order_lines",
        "trade_partners",
    ),
}

MARKET_SYSTEM_REQUIREMENTS: dict[str, str] = {
    "Products / Product Master": "products",
    "Switch to Buyer Dash": "switch_center",
    "Production Control": "production",
    "Wholesale + Finance": "wholesale_finance",
    "Doobie Actions": "doobie_actions",
    "Benchmarks": "benchmarks",
    "Design Partner": "design_partner",
    "Extraction / Run 360": "extraction",
    "Traceability": "traceability",
}

# These are real platform configuration surfaces, not tenant operational
# datasets. They remain available to DEV, but are excluded from fake-data
# requirements by design.
PLATFORM_CONTROL_SURFACES = (
    "Admin Tools",
    "AI & METRC Integrations",
    "METRC Integrations",
    "Location Settings",
)


def is_dev_role(role: str | None) -> bool:
    return str(role or "").strip().casefold() == "dev"


def is_dev_sandbox_scope(organization: Any, facility: Any) -> bool:
    return (
        str(getattr(organization, "slug", "") or "").strip().casefold()
        == DEMO_ORGANIZATION_SLUG.casefold()
        and str(getattr(facility, "code", "") or "").strip().casefold()
        == DEMO_FACILITY_CODE.casefold()
    )


def install_dev_sandbox_role_guard() -> None:
    """Make the living full-app sandbox runtime DEV-only.

    ``services.demo_data`` historically also enabled itself for admin/demo flags.
    The canonical durable sandbox is a developer environment, so the app runtime
    narrows that behavior before demo bootstrap executes.
    """
    from services import demo_data

    current = demo_data.demo_enabled_for_state
    if getattr(current, "_dev_sandbox_only", False):
        return

    def dev_only(state: MutableMapping[str, Any]) -> bool:
        return is_dev_role(str(state.get("auth_user_role") or ""))

    dev_only._dev_sandbox_only = True
    demo_data.demo_enabled_for_state = dev_only


def force_sandbox_operational_sources(state: MutableMapping[str, Any]) -> None:
    """Keep DEV Sandbox tenant operations on synthetic sources, never live retail data."""
    state["demo_mode_enabled"] = True
    state["data_mode"] = SANDBOX_DATA_MODE
    state["flat_nav_data_mode"] = SANDBOX_DATA_MODE
    state["mobile_flat_nav_data_mode"] = SANDBOX_DATA_MODE
    state["_sandbox_live_operational_sources_blocked"] = True


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, pd.Series):
        return not value.empty
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return True


def session_sandbox_system_readiness(state: Mapping[str, Any]) -> dict[str, Any]:
    systems: dict[str, bool] = {}
    missing_detail: dict[str, list[str]] = {}
    for system, keys in SESSION_SYSTEM_REQUIREMENTS.items():
        missing = [key for key in keys if not _nonempty(state.get(key))]
        systems[system] = not missing
        if missing:
            missing_detail[system] = missing

    uploads = state.get("demo_upload_catalog")
    upload_keys = set(uploads) if isinstance(uploads, Mapping) else set()
    upload_missing = sorted(REQUIRED_UPLOADS - upload_keys)
    systems["Data Hub"] = systems.get("Data Hub", False) and not upload_missing
    if upload_missing:
        missing_detail.setdefault("Data Hub", []).extend(
            f"upload:{item}" for item in upload_missing
        )

    source_mode_ok = str(state.get("data_mode") or "") == SANDBOX_DATA_MODE
    systems["Sandbox data-source isolation"] = source_mode_ok
    if not source_mode_ok:
        missing_detail["Sandbox data-source isolation"] = [
            f"data_mode={state.get('data_mode')!r}"
        ]

    return {
        "ready": all(systems.values()),
        "systems": systems,
        "missing": [name for name, ok in systems.items() if not ok],
        "detail": missing_detail,
    }


def _count(session: Any, model: Any, *conditions: Any) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(session.scalar(statement) or 0)


def _seed_version(session: Any, organization_id: str) -> str:
    event = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.entity_type == "demo_dataset",
            AuditEvent.action == "seeded",
        )
        .order_by(AuditEvent.occurred_at.desc())
        .limit(1)
    )
    if event is None:
        return ""
    try:
        return str(json.loads(event.changes_json or "{}").get("version") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""


def core_sandbox_readiness(
    engine: Engine,
    organization_id: str,
    facility_id: str,
) -> dict[str, Any]:
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions() as session:
        organization = session.get(Organization, organization_id)
        facility = session.get(Facility, facility_id)
        if (
            organization is None
            or facility is None
            or facility.organization_id != organization.id
            or organization.slug != DEMO_ORGANIZATION_SLUG
            or facility.code != DEMO_FACILITY_CODE
        ):
            raise ValueError("Core sandbox readiness refused a non-DEV Sandbox tenant.")

        counts = {
            "products": _count(session, Product, Product.organization_id == organization_id),
            "inventory_lots": _count(
                session,
                InventoryLot,
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            ),
            "inventory_transactions": _count(
                session,
                InventoryTransaction,
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
            ),
            "inventory_audits": _count(
                session,
                InventoryAudit,
                InventoryAudit.organization_id == organization_id,
                InventoryAudit.facility_id == facility_id,
            ),
            "production_orders": _count(
                session,
                ProductionOrder,
                ProductionOrder.organization_id == organization_id,
                ProductionOrder.facility_id == facility_id,
            ),
            "product_boms": _count(
                session,
                ProductBom,
                ProductBom.organization_id == organization_id,
            ),
            "bom_components": _count(
                session,
                BomComponent,
                BomComponent.organization_id == organization_id,
            ),
            "material_reservations": _count(
                session,
                MaterialReservation,
                MaterialReservation.organization_id == organization_id,
                MaterialReservation.facility_id == facility_id,
            ),
            "production_actuals": _count(
                session,
                ProductionActual,
                ProductionActual.organization_id == organization_id,
                ProductionActual.facility_id == facility_id,
            ),
            "facility_machines": _count(
                session,
                FacilityMachine,
                FacilityMachine.organization_id == organization_id,
                FacilityMachine.facility_id == facility_id,
            ),
            "crew_availability": _count(
                session,
                CrewAvailability,
                CrewAvailability.organization_id == organization_id,
                CrewAvailability.facility_id == facility_id,
            ),
            "hand_labor_areas": _count(
                session,
                HandLaborArea,
                HandLaborArea.organization_id == organization_id,
                HandLaborArea.facility_id == facility_id,
            ),
            "commercial_orders": _count(
                session,
                CommercialOrder,
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
            ),
            "commercial_order_lines": _count(
                session,
                CommercialOrderLine,
                CommercialOrderLine.organization_id == organization_id,
            ),
            "trade_partners": _count(
                session,
                TradePartner,
                TradePartner.organization_id == organization_id,
            ),
        }
        version = _seed_version(session, organization_id)

    systems: dict[str, bool] = {}
    for system, required_counts in CORE_SYSTEM_REQUIREMENTS.items():
        systems[system] = all(counts.get(name, 0) > 0 for name in required_counts)
    version_ok = version == COMAN_DEMO_DATA_VERSION
    systems["Current core sandbox version"] = version_ok
    return {
        "ready": all(systems.values()),
        "version": version,
        "expected_version": COMAN_DEMO_DATA_VERSION,
        "counts": counts,
        "systems": systems,
        "missing": [name for name, ok in systems.items() if not ok],
    }


def _demo_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.date() if pd.notna(parsed) else date.today()


def rebuild_core_sandbox(
    engine: Engine,
    state: MutableMapping[str, Any],
    *,
    actor: str,
) -> dict[str, Any]:
    """One-time self-upgrade for stale synthetic core data, preserving org/facility IDs."""
    from services.demo_data import build_demo_payload

    payload = build_demo_payload(
        today=_demo_date(state.get("demo_as_of_date")),
        scale=str(state.get("demo_dataset_scale") or "medium"),
        company_seed=int(state.get("demo_company_seed") or 710),
        catalog_seed=int(state.get("demo_catalog_seed") or 811),
        history_seed=int(state.get("demo_history_seed") or 912),
        problems=set(state.get("demo_problem_set") or []),
    )

    # Extension rows may reference products/orders that the full core refresh
    # replaces. Clear only the synthetic extension rows first, then force the
    # canonical Co-Man sandbox seed inside the same org/facility identity.
    reset_market_sandbox_dataset(engine=engine)
    result = ensure_coman_demo_dataset(
        state=state,
        actor=actor,
        payload=payload,
        force=True,
        engine=engine,
    )
    state["_coman_demo_seeded"] = True
    state["_coman_demo_error"] = ""
    return result


def full_sandbox_system_readiness(
    engine: Engine,
    state: Mapping[str, Any],
    organization_id: str,
    facility_id: str,
    *,
    core: Mapping[str, Any] | None = None,
    market: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    session_report = session_sandbox_system_readiness(state)
    core_report = dict(core or core_sandbox_readiness(engine, organization_id, facility_id))
    market_report = dict(market or market_sandbox_readiness(engine, organization_id, facility_id))

    systems = dict(session_report.get("systems") or {})
    systems.update(dict(core_report.get("systems") or {}))
    market_counts = dict(market_report.get("counts") or {})
    for system, count_key in MARKET_SYSTEM_REQUIREMENTS.items():
        systems[system] = int(market_counts.get(count_key) or 0) > 0

    missing = [name for name, ok in systems.items() if not ok]
    return {
        "ready": not missing,
        "systems": systems,
        "missing": missing,
        "system_count": len(systems),
        "ready_count": sum(1 for ok in systems.values() if ok),
        "session": session_report,
        "core": core_report,
        "market": market_report,
        "platform_controls": list(PLATFORM_CONTROL_SURFACES),
        "data_mode": str(state.get("data_mode") or ""),
    }


def ensure_full_sandbox_contract(
    state: MutableMapping[str, Any],
    *,
    organization: Any,
    facility: Any,
    role: str,
    actor: str,
    engine: Engine,
) -> dict[str, Any]:
    """Self-heal and verify every operational DEV Sandbox system."""
    if not is_dev_role(role) or not is_dev_sandbox_scope(organization, facility):
        return {
            "ready": True,
            "skipped": True,
            "systems": {},
            "missing": [],
        }

    force_sandbox_operational_sources(state)

    # Session payload is the source for retail/reporting/repack/data-hub pages.
    # If any of those pieces are missing, rebuild the living synthetic session.
    session_report = session_sandbox_system_readiness(state)
    if not session_report.get("ready"):
        from services.demo_data import ensure_full_app_demo_session

        ensure_full_app_demo_session(state, actor=actor, force=True)
        force_sandbox_operational_sources(state)
        session_report = session_sandbox_system_readiness(state)

    organization_id = str(getattr(organization, "id", "") or "").strip()
    facility_id = str(getattr(facility, "id", "") or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("DEV Sandbox context is missing organization/facility IDs.")

    core = core_sandbox_readiness(engine, organization_id, facility_id)
    if not core.get("ready"):
        rebuild_core_sandbox(engine, state, actor=actor)
        core = core_sandbox_readiness(engine, organization_id, facility_id)

    # Core refresh intentionally clears extension rows because they reference
    # replaced synthetic products/orders. Re-seed all newer durable systems now.
    market = market_sandbox_readiness(engine, organization_id, facility_id)
    if not market.get("ready"):
        market = seed_market_sandbox(
            engine,
            organization_id,
            facility_id,
            actor=actor,
            state=state,
        )

    report = full_sandbox_system_readiness(
        engine,
        state,
        organization_id,
        facility_id,
        core=core,
        market=market,
    )
    state["demo_sandbox_system_readiness"] = report
    state["demo_sandbox_market_readiness"] = market
    if report.get("ready"):
        state.pop("_sandbox_market_seed_error", None)
        state.pop("_sandbox_system_contract_error", None)
    else:
        detail = "DEV Sandbox systems missing data: " + ", ".join(report.get("missing") or [])
        state["_sandbox_system_contract_error"] = detail
    return report
