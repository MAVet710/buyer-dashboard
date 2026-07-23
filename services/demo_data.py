"""Living, versioned demo company used across every application workspace.

The simulator is intentionally session-first and non-destructive. Real uploads always
win. Co-Man receives a separate durable demo organization when a database is available.
"""
from __future__ import annotations

import io
import math
import os
import random
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from services.demo_data_buyer import build_buyer_demo
from services.demo_data_operations import build_operations_demo

DEMO_DATA_VERSION = "full-app-simulation-v2"
PRIVILEGED_DEMO_ROLES = {"dev", "admin"}
DATASET_SCALES = ("small", "medium", "enterprise")
PERSONAS = (
    "Buyer",
    "Operations Director",
    "Production Manager",
    "CFO",
    "Compliance Officer",
    "CEO",
    "Quality Manager",
    "Sales Director",
)
SCENARIO_PROBLEMS: dict[str, set[str]] = {
    "Healthy baseline": set(),
    "QA holds": {"qa_hold"},
    "Failed COAs": {"failed_coa", "qa_hold"},
    "Supply disruption": {"late_po", "material_shortage"},
    "Production bottleneck": {"machine_downtime", "late_jobs", "low_yield"},
    "Financial stress": {"negative_margin", "overdue_invoice", "slow_movers"},
    "Full operational chaos": {
        "qa_hold",
        "failed_coa",
        "late_po",
        "material_shortage",
        "machine_downtime",
        "late_jobs",
        "low_yield",
        "negative_margin",
        "overdue_invoice",
        "slow_movers",
        "expiring_inventory",
    },
}

DEMO_SESSION_KEYS = {
    "demo_mode_enabled",
    "demo_upload_catalog",
    "demo_data_banner",
    "demo_company_profile",
    "demo_catalog_df",
    "demo_budget_df",
    "demo_dataset_scale",
    "demo_company_seed",
    "demo_catalog_seed",
    "demo_history_seed",
    "demo_problem_set",
    "demo_as_of_date",
    "demo_event_log",
    "demo_training_history",
    "demo_selected_scenario",
    "_full_app_demo_version",
    "_full_app_demo_sections",
    "_coman_demo_seeded",
    "_coman_demo_error",
    "inv_raw_df",
    "sales_raw_df",
    "extra_sales_df",
    "detail_cached_df",
    "detail_product_cached_df",
    "active_inventory_df",
    "active_sales_df",
    "delivery_manifest_df",
    "delivery_sales_df",
    "delivery_raw_df",
    "daily_sales_raw_df",
    "compliance_sources_df",
    "ecc_inventory_log",
    "ecc_run_log",
    "ecc_client_jobs",
    "ecc_job_log",
    "quarantined_items",
    "_cache_inv",
    "_cache_sales",
    "_cache_extra_sales",
    "_cache_quarantine",
    "data_mode",
    "doh_threshold_cache",
    "purchasing_budget_monthly_usd",
    "purchasing_budget_open_po_usd",
    "purchasing_budget_spent_usd",
}


@dataclass(frozen=True)
class DemoSeedResult:
    seeded: bool
    version: str
    sections: tuple[str, ...]
    coman_seeded: bool = False
    coman_error: str = ""


class DemoUploadedFile(io.BytesIO):
    def __init__(self, content: bytes, name: str, mime_type: str = "text/csv") -> None:
        super().__init__(content)
        self.name = name
        self.type = mime_type
        self.size = len(content)


def _authenticated(state: MutableMapping[str, Any]) -> bool:
    return bool(
        state.get("user_authenticated")
        or state.get("is_admin")
        or state.get("auth_user_id")
        or state.get("admin_user")
        or state.get("user_user")
    )


def demo_enabled_for_state(state: MutableMapping[str, Any]) -> bool:
    role = str(state.get("auth_user_role") or "").casefold()
    all_users = os.environ.get("BUYER_DASHBOARD_DEMO_FOR_ALL_AUTHENTICATED", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return bool(
        role in PRIVILEGED_DEMO_ROLES
        or state.get("is_admin")
        or state.get("demo_mode_enabled")
        or (all_users and _authenticated(state))
    )


def _default_config(state: MutableMapping[str, Any], today: date | None = None) -> None:
    state.setdefault("demo_dataset_scale", "medium")
    state.setdefault("demo_company_seed", 710)
    state.setdefault("demo_catalog_seed", 811)
    state.setdefault("demo_history_seed", 912)
    state.setdefault("demo_problem_set", [])
    state.setdefault("demo_as_of_date", today or datetime.now().date())
    state.setdefault("demo_event_log", [])
    state.setdefault("demo_training_history", [])
    state.setdefault("demo_selected_scenario", "Healthy baseline")


def _as_date(value: Any, fallback: date | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed):
        return parsed.date()
    return fallback or datetime.now().date()


def _set(state: MutableMapping[str, Any], key: str, value: Any, force: bool) -> None:
    old = state.get(key)
    empty = (
        old is None
        or (isinstance(old, pd.DataFrame) and old.empty)
        or (isinstance(old, str) and not old.strip())
        or (isinstance(old, (list, tuple, set, dict)) and not old)
    )
    if force or empty:
        state[key] = value.copy() if isinstance(value, pd.DataFrame) else value


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _build_uploads(buyer: dict[str, Any], operations: dict[str, Any]) -> dict[str, tuple[str, bytes, str]]:
    return {
        "buyer_inventory": ("demo_inventory.csv", _csv(buyer["inventory"]), "text/csv"),
        "buyer_sales": ("demo_product_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "buyer_extra_sales": ("demo_extra_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "buyer_quarantine": ("demo_quarantine.csv", _csv(buyer["quarantine"]), "text/csv"),
        "delivery_manifest": ("demo_delivery_manifest.csv", _csv(buyer["manifest"]), "text/csv"),
        "delivery_sales": ("demo_delivery_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "compliance_sources": ("demo_compliance_sources.csv", _csv(buyer["compliance"]), "text/csv"),
        "extraction_inventory": (
            "demo_extraction_inventory.csv",
            _csv(operations["extraction_inventory"]),
            "text/csv",
        ),
        "extraction_runs": ("demo_extraction_runs.csv", _csv(operations["extraction_runs"]), "text/csv"),
        "extraction_jobs": ("demo_extraction_jobs.csv", _csv(operations["extraction_jobs"]), "text/csv"),
    }


def build_demo_payload(
    today: date | None = None,
    *,
    scale: str = "medium",
    company_seed: int = 710,
    catalog_seed: int = 811,
    history_seed: int = 912,
    problems: set[str] | None = None,
) -> dict[str, Any]:
    as_of = today or datetime.now().date()
    normalized_scale = scale if scale in DATASET_SCALES else "medium"
    problem_set = set(problems or set())
    buyer = build_buyer_demo(
        as_of,
        scale=normalized_scale,
        seed=710,
        company_seed=int(company_seed),
        catalog_seed=int(catalog_seed),
        history_seed=int(history_seed),
        problems=problem_set,
    )
    operations = build_operations_demo(
        as_of,
        catalog=buyer["catalog"],
        scale=normalized_scale,
        seed=int(history_seed),
        company=buyer["company_profile"],
        problems=problem_set,
    )
    return {
        **buyer,
        **operations,
        "uploads": _build_uploads(buyer, operations),
        "as_of_date": as_of,
        "scale": normalized_scale,
        "problems": sorted(problem_set),
    }


def _recompute_detail(inventory: pd.DataFrame, sales: pd.DataFrame, reporting_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    inv = inventory.copy()
    sales_df = sales.copy()
    sold = pd.DataFrame(columns=["SKU", "unitssold", "net_sales"])
    if not sales_df.empty and "SKU" in sales_df.columns:
        sold = sales_df.groupby("SKU", as_index=False).agg(
            unitssold=("Quantity Sold", "sum"), net_sales=("Net Sales", "sum")
        )
    merged = inv.merge(sold, on="SKU", how="left")
    merged["unitssold"] = pd.to_numeric(merged.get("unitssold"), errors="coerce").fillna(0.0)
    merged["net_sales"] = pd.to_numeric(merged.get("net_sales"), errors="coerce").fillna(0.0)
    merged["onhandunits"] = pd.to_numeric(merged.get("Available"), errors="coerce").fillna(0.0)
    merged["avgunitsperday"] = merged["unitssold"] / max(int(reporting_days), 1)
    velocity = merged["avgunitsperday"].replace(0, pd.NA)
    merged["daysonhand"] = (
        (merged["onhandunits"] / velocity).fillna(999.0).clip(upper=999.0).round().astype(int)
    )
    merged["reorderqty"] = (
        ((21 - merged["daysonhand"]).clip(lower=0) * merged["avgunitsperday"]).apply(math.ceil)
    )
    merged["reorderpriority"] = merged.apply(
        lambda row: (
            "1 – Reorder ASAP"
            if 0 < row["daysonhand"] <= 7
            else (
                "2 – Watch Closely"
                if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0
                else ("4 – Dead Item" if row["avgunitsperday"] == 0 else "3 – Comfortable Cover")
            )
        ),
        axis=1,
    )
    product = pd.DataFrame(
        {
            "subcategory": merged.get("Category", ""),
            "product_name": merged.get("Product Name", ""),
            "strain_type": merged.get("EComm Strain Type", ""),
            "packagesize": merged.get("Package Size", merged.get("Size", "")),
            "onhandunits": merged["onhandunits"],
            "unitssold": merged["unitssold"],
            "avgunitsperday": merged["avgunitsperday"],
            "daysonhand": merged["daysonhand"],
            "reorderqty": merged["reorderqty"],
            "reorderpriority": merged["reorderpriority"],
            "brand": merged.get("Brand", ""),
            "sku": merged.get("SKU", ""),
            "unit_cost": pd.to_numeric(merged.get("Cost", 0), errors="coerce").fillna(0.0),
            "retail_price": pd.to_numeric(merged.get("Med Price", 0), errors="coerce").fillna(0.0),
            "net_sales": merged["net_sales"],
            "batch_id": merged.get("Batch", ""),
            "package_id": merged.get("Package ID", ""),
            "coa_id": merged.get("COA ID", ""),
            "source_production_order": merged.get("Source Production Order", ""),
            "source_extraction_batch": merged.get("Source Extraction Batch", ""),
        }
    )
    group_cols = ["subcategory", "strain_type", "packagesize"]
    detail = product.groupby(group_cols, dropna=False, as_index=False).agg(
        onhandunits=("onhandunits", "sum"),
        unitssold=("unitssold", "sum"),
        avgunitsperday=("avgunitsperday", "sum"),
        net_sales=("net_sales", "sum"),
    )
    detail_velocity = detail["avgunitsperday"].replace(0, pd.NA)
    detail["daysonhand"] = (
        (detail["onhandunits"] / detail_velocity).fillna(999).clip(upper=999).round().astype(int)
    )
    detail["reorderqty"] = (
        ((21 - detail["daysonhand"]).clip(lower=0) * detail["avgunitsperday"]).apply(math.ceil)
    )
    detail["reorderpriority"] = detail.apply(
        lambda row: (
            "1 – Reorder ASAP"
            if 0 < row["daysonhand"] <= 7
            else (
                "2 – Watch Closely"
                if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0
                else ("4 – Dead Item" if row["avgunitsperday"] == 0 else "3 – Comfortable Cover")
            )
        ),
        axis=1,
    )
    return detail, product


def _apply_living_transition(
    state: MutableMapping[str, Any], payload: dict[str, Any], days: int
) -> dict[str, Any]:
    previous_inventory = state.get("inv_raw_df")
    previous_sales = state.get("sales_raw_df")
    if not isinstance(previous_inventory, pd.DataFrame) or previous_inventory.empty:
        return payload
    inventory = payload["inventory"].copy()
    reporting_days = int(payload.get("reporting_days") or 60)
    sales_for_velocity = previous_sales if isinstance(previous_sales, pd.DataFrame) else payload["sales"]
    velocity = pd.DataFrame(columns=["SKU", "daily"])
    if isinstance(sales_for_velocity, pd.DataFrame) and not sales_for_velocity.empty and "SKU" in sales_for_velocity.columns:
        velocity = sales_for_velocity.groupby("SKU", as_index=False)["Quantity Sold"].sum().rename(
            columns={"Quantity Sold": "units"}
        )
        velocity["daily"] = velocity["units"] / max(reporting_days, 1)
    previous = (
        previous_inventory[["SKU", "Available"]].copy()
        if "SKU" in previous_inventory.columns
        else pd.DataFrame()
    )
    previous["Available"] = pd.to_numeric(previous.get("Available"), errors="coerce").fillna(0.0)
    inventory = inventory.merge(
        previous.rename(columns={"Available": "previous_available"}), on="SKU", how="left"
    )
    inventory = inventory.merge(velocity[["SKU", "daily"]], on="SKU", how="left")
    inventory["previous_available"] = inventory["previous_available"].fillna(
        pd.to_numeric(inventory.get("Available"), errors="coerce").fillna(0.0)
    )
    inventory["daily"] = inventory["daily"].fillna(0.0)
    receipts = pd.Series(dtype=float)
    manifest = payload.get("manifest")
    if isinstance(manifest, pd.DataFrame) and not manifest.empty and "SKU" in manifest.columns:
        receipts = manifest.groupby("SKU")["Received Qty"].sum() * min(max(days / 30.0, 0.15), 1.0)
    complete_runs = payload.get("extraction_runs")
    completed_batches: set[str] = set()
    if isinstance(complete_runs, pd.DataFrame) and not complete_runs.empty:
        complete_mask = complete_runs.get(
            "status", pd.Series(index=complete_runs.index, dtype=str)
        ).astype(str).str.casefold().eq("complete")
        pass_mask = complete_runs.get(
            "coa_status", pd.Series(index=complete_runs.index, dtype=str)
        ).astype(str).str.casefold().eq("passed")
        completed_batches = set(
            complete_runs.loc[complete_mask & pass_mask, "batch_id_internal"].astype(str)
        )
    production_add = (
        inventory.get(
            "Source Extraction Batch", pd.Series(index=inventory.index, dtype=str)
        ).astype(str).isin(completed_batches).astype(float)
        * 18.0
    )
    inventory["Available"] = (
        inventory["previous_available"]
        - (inventory["daily"] * days)
        + inventory["SKU"].map(receipts).fillna(0.0)
        + production_add
    ).clip(lower=0.0).round(0).astype(int)
    inventory = inventory.drop(columns=["previous_available", "daily"], errors="ignore")
    payload["inventory"] = inventory

    fresh_sales = payload["sales"].copy()
    old_sales = previous_sales.copy() if isinstance(previous_sales, pd.DataFrame) else pd.DataFrame()
    cutoff = payload["as_of_date"] - timedelta(days=max(days - 1, 0))
    if "Order Time" in fresh_sales.columns:
        fresh_times = pd.to_datetime(fresh_sales["Order Time"], errors="coerce")
        incremental = fresh_sales[fresh_times.dt.date >= cutoff].copy()
    else:
        incremental = fresh_sales.head(
            max(1, int(len(fresh_sales) * days / max(reporting_days, 1)))
        ).copy()
    combined_sales = pd.concat([old_sales, incremental], ignore_index=True)
    if "Order Time" in combined_sales.columns:
        combined_sales["_order_dt"] = pd.to_datetime(combined_sales["Order Time"], errors="coerce")
        min_date = pd.Timestamp(payload["as_of_date"] - timedelta(days=180))
        combined_sales = combined_sales[combined_sales["_order_dt"] >= min_date].drop(
            columns=["_order_dt"]
        )
    payload["sales"] = combined_sales
    detail, product = _recompute_detail(inventory, combined_sales, reporting_days)
    payload["detail"], payload["detail_product"] = detail, product

    budget = payload.get("budget")
    if isinstance(budget, pd.DataFrame) and not budget.empty:
        budget = budget.copy()
        # Budget currency is decimal; Pandas 3 rejects fractional assignment
        # into an integer column unless it is normalized first.
        budget["Actual"] = pd.to_numeric(
            budget.get("Actual"), errors="coerce"
        ).fillna(0.0).astype(float)
        purchase_spend = (
            float(
                (
                    pd.to_numeric(manifest.get("Received Qty", 0), errors="coerce").fillna(0)
                    * pd.to_numeric(
                        manifest.get(
                            "SKU", pd.Series(index=manifest.index, dtype=str)
                        ).map(inventory.set_index("SKU").get("Cost", pd.Series(dtype=float))),
                        errors="coerce",
                    ).fillna(0)
                ).sum()
            )
            if isinstance(manifest, pd.DataFrame) and not manifest.empty
            else 0.0
        )
        budget.loc[budget.index[0], "Actual"] = (
            float(budget.loc[budget.index[0], "Actual"]) + purchase_spend
        )
        payload["budget"] = budget
    payload["uploads"] = _build_uploads(payload, payload)
    return payload


def _seed_coman(
    state: MutableMapping[str, Any], actor: str, payload: dict[str, Any], force: bool
) -> tuple[bool, str]:
    try:
        from modules.coman.demo_data import ensure_coman_demo_dataset

        result = ensure_coman_demo_dataset(
            state=state, actor=actor, payload=payload, force=force
        )
        return bool(result.get("seeded") or result.get("already_present")), ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _install_payload(
    state: MutableMapping[str, Any], payload: dict[str, Any], *, actor: str, force: bool
) -> DemoSeedResult:
    state["demo_mode_enabled"] = True
    state["demo_upload_catalog"] = payload["uploads"]
    state["demo_data_banner"] = (
        "Living demo company is active. Real uploaded files replace their matching demo source."
    )
    state["demo_company_profile"] = dict(payload["company_profile"])
    state["demo_catalog_df"] = payload["catalog"].copy()
    state["demo_budget_df"] = payload["budget"].copy()
    state["demo_as_of_date"] = payload["as_of_date"]
    state["demo_problem_set"] = list(payload["problems"])

    frames = {
        "inv_raw_df": "inventory",
        "sales_raw_df": "sales",
        "extra_sales_df": "sales",
        "detail_cached_df": "detail",
        "detail_product_cached_df": "detail_product",
        "active_inventory_df": "inventory",
        "active_sales_df": "sales",
        "delivery_manifest_df": "manifest",
        "delivery_sales_df": "sales",
        "delivery_raw_df": "manifest",
        "daily_sales_raw_df": "sales",
        "compliance_sources_df": "compliance",
        "ecc_inventory_log": "extraction_inventory",
        "ecc_run_log": "extraction_runs",
        "ecc_client_jobs": "extraction_jobs",
        "ecc_job_log": "extraction_jobs",
    }
    for state_key, payload_key in frames.items():
        _set(state, state_key, payload[payload_key], force)
    _set(
        state,
        "quarantined_items",
        set(payload["quarantine"]["Product"].tolist()),
        force,
    )
    for key, value in payload["white_label"].items():
        _set(state, key, value, force)
    for cache, source in {
        "_cache_inv": "buyer_inventory",
        "_cache_sales": "buyer_sales",
        "_cache_extra_sales": "buyer_extra_sales",
        "_cache_quarantine": "buyer_quarantine",
    }.items():
        name, content, _ = payload["uploads"][source]
        _set(state, cache, {"name": name, "bytes": content}, force)
    budget = payload["budget"]
    monthly_budget = float(
        pd.to_numeric(budget.get("Budget", 0), errors="coerce").fillna(0).sum()
    )
    committed = float(
        pd.to_numeric(budget.get("Committed", 0), errors="coerce").fillna(0).sum()
    )
    spent = float(
        pd.to_numeric(budget.get("Actual", 0), errors="coerce").fillna(0).sum()
    )
    for key, value in {
        "data_mode": "📁 Uploads",
        "doh_threshold_cache": 21,
        "purchasing_budget_monthly_usd": monthly_budget,
        "purchasing_budget_open_po_usd": committed,
        "purchasing_budget_spent_usd": spent,
    }.items():
        _set(state, key, value, force)

    coman_seeded, coman_error = _seed_coman(state, actor, payload, force)
    state["_coman_demo_seeded"] = coman_seeded
    state["_coman_demo_error"] = coman_error
    sections = (
        "Inventory Dashboard",
        "Trends",
        "Delivery Impact",
        "Slow Movers",
        "PO Builder",
        "Compliance Q&A",
        "Buyer Intelligence",
        "Purchasing Budget",
        "Admin Tools",
        "White Label / Repack",
        "Co-Man Production",
        "Extraction Command Center",
    )
    state["_full_app_demo_version"] = DEMO_DATA_VERSION
    state["_full_app_demo_sections"] = sections
    return DemoSeedResult(
        True, DEMO_DATA_VERSION, sections, coman_seeded, coman_error
    )


def ensure_full_app_demo_session(
    state: MutableMapping[str, Any],
    *,
    actor: str = "demo",
    force: bool = False,
    today: date | None = None,
) -> DemoSeedResult:
    if not demo_enabled_for_state(state):
        return DemoSeedResult(False, DEMO_DATA_VERSION, ())
    _default_config(state, today)
    if state.get("_full_app_demo_version") == DEMO_DATA_VERSION and not force:
        return DemoSeedResult(
            False,
            DEMO_DATA_VERSION,
            tuple(state.get("_full_app_demo_sections", ())),
            bool(state.get("_coman_demo_seeded")),
            str(state.get("_coman_demo_error") or ""),
        )
    payload = build_demo_payload(
        today=_as_date(today or state.get("demo_as_of_date")),
        scale=str(state.get("demo_dataset_scale") or "medium"),
        company_seed=int(state.get("demo_company_seed") or 710),
        catalog_seed=int(state.get("demo_catalog_seed") or 811),
        history_seed=int(state.get("demo_history_seed") or 912),
        problems=set(state.get("demo_problem_set") or []),
    )
    return _install_payload(state, payload, actor=actor, force=force)


def regenerate_demo_company(
    state: MutableMapping[str, Any],
    *,
    actor: str = "demo",
    reason: str = "Regenerated company",
) -> DemoSeedResult:
    state.pop("_full_app_demo_version", None)
    result = ensure_full_app_demo_session(state, actor=actor, force=True)
    state.setdefault("demo_event_log", []).append(
        {"date": _as_date(state.get("demo_as_of_date")).isoformat(), "event": reason}
    )
    return result


def advance_demo_company(
    state: MutableMapping[str, Any], *, days: int = 30, actor: str = "demo"
) -> DemoSeedResult:
    if days < 1:
        raise ValueError("days must be at least 1")
    ensure_full_app_demo_session(state, actor=actor)
    old_date = _as_date(state.get("demo_as_of_date"))
    new_date = old_date + timedelta(days=int(days))
    state["demo_history_seed"] = int(state.get("demo_history_seed") or 912) + int(days)
    payload = build_demo_payload(
        today=new_date,
        scale=str(state.get("demo_dataset_scale") or "medium"),
        company_seed=int(state.get("demo_company_seed") or 710),
        catalog_seed=int(state.get("demo_catalog_seed") or 811),
        history_seed=int(state.get("demo_history_seed") or 912),
        problems=set(state.get("demo_problem_set") or []),
    )
    payload = _apply_living_transition(state, payload, int(days))
    result = _install_payload(state, payload, actor=actor, force=True)
    state.setdefault("demo_event_log", []).append(
        {
            "date": new_date.isoformat(),
            "event": (
                f"Advanced company {days} days: sales consumed inventory, receipts and "
                "completed production replenished stock, and purchasing actuals increased."
            ),
        }
    )
    return result


def inject_demo_problem(
    state: MutableMapping[str, Any], scenario: str, *, actor: str = "demo"
) -> DemoSeedResult:
    if scenario not in SCENARIO_PROBLEMS:
        raise ValueError(f"Unknown demo scenario: {scenario}")
    state["demo_selected_scenario"] = scenario
    state["demo_problem_set"] = sorted(SCENARIO_PROBLEMS[scenario])
    return regenerate_demo_company(
        state, actor=actor, reason=f"Injected scenario: {scenario}"
    )


def randomize_demo_dimension(
    state: MutableMapping[str, Any], dimension: str, *, actor: str = "demo"
) -> DemoSeedResult:
    key_by_dimension = {
        "company": "demo_company_seed",
        "catalog": "demo_catalog_seed",
        "history": "demo_history_seed",
    }
    if dimension not in key_by_dimension:
        raise ValueError("dimension must be company, catalog, or history")
    key = key_by_dimension[dimension]
    state[key] = random.SystemRandom().randint(1_000, 9_999_999)
    return regenerate_demo_company(
        state, actor=actor, reason=f"Randomized {dimension}"
    )


def reset_demo_session(
    state: MutableMapping[str, Any],
    *,
    preserve_auth: bool = True,
    reset_database: bool = False,
) -> None:
    preserved: dict[str, Any] = {}
    if preserve_auth:
        for key in list(state.keys()):
            lowered = str(key).casefold()
            if (
                key.startswith("auth_")
                or key
                in {"is_admin", "admin_user", "user_authenticated", "user_user"}
                or any(
                    token in lowered
                    for token in (
                        "doobie",
                        "metrc",
                        "license",
                        "credential",
                        "api_key",
                    )
                )
            ):
                preserved[key] = state[key]
    for key in list(DEMO_SESSION_KEYS):
        state.pop(key, None)
    for key in list(state.keys()):
        if key.startswith("wl_") or key.startswith("white_label_"):
            state.pop(key, None)
    state.update(preserved)
    if reset_database:
        try:
            from modules.coman.demo_data import reset_coman_demo_dataset

            reset_coman_demo_dataset()
        except Exception:
            pass


def demo_company_summary(state: MutableMapping[str, Any]) -> dict[str, Any]:
    inventory = state.get("inv_raw_df")
    sales = state.get("sales_raw_df")
    runs = state.get("ecc_run_log")
    jobs = state.get("ecc_client_jobs")
    budget = state.get("demo_budget_df")
    inventory = inventory if isinstance(inventory, pd.DataFrame) else pd.DataFrame()
    sales = sales if isinstance(sales, pd.DataFrame) else pd.DataFrame()
    runs = runs if isinstance(runs, pd.DataFrame) else pd.DataFrame()
    jobs = jobs if isinstance(jobs, pd.DataFrame) else pd.DataFrame()
    budget = budget if isinstance(budget, pd.DataFrame) else pd.DataFrame()
    available = pd.to_numeric(inventory.get("Available", 0), errors="coerce").fillna(0)
    cost = pd.to_numeric(inventory.get("Cost", 0), errors="coerce").fillna(0)
    sales_qty = pd.to_numeric(sales.get("Quantity Sold", 0), errors="coerce").fillna(0)
    revenue = pd.to_numeric(sales.get("Net Sales", 0), errors="coerce").fillna(0)
    qa_hold_count = 0
    failed_coas = 0
    if not runs.empty:
        qa_hold_count = int(
            runs.get("qa_hold", pd.Series(False, index=runs.index))
            .fillna(False)
            .astype(bool)
            .sum()
        )
        failed_coas = int(
            runs.get("coa_status", pd.Series("", index=runs.index))
            .astype(str)
            .str.casefold()
            .eq("failed")
            .sum()
        )
    at_risk_jobs = 0
    if not jobs.empty:
        at_risk_jobs = int(
            jobs.get("sla_status", pd.Series("", index=jobs.index))
            .astype(str)
            .str.casefold()
            .eq("at risk")
            .sum()
        )
    budget_amount = float(
        pd.to_numeric(budget.get("Budget", 0), errors="coerce").fillna(0).sum()
    )
    budget_actual = float(
        pd.to_numeric(budget.get("Actual", 0), errors="coerce").fillna(0).sum()
    )
    return {
        "company": dict(state.get("demo_company_profile") or {}),
        "as_of_date": _as_date(state.get("demo_as_of_date")).isoformat(),
        "scale": str(state.get("demo_dataset_scale") or "medium"),
        "problems": list(state.get("demo_problem_set") or []),
        "sku_count": int(len(inventory)),
        "units_on_hand": float(available.sum()),
        "inventory_value": float((available * cost).sum()),
        "sales_rows": int(len(sales)),
        "units_sold": float(sales_qty.sum()),
        "net_sales": float(revenue.sum()),
        "extraction_runs": int(len(runs)),
        "qa_holds": qa_hold_count,
        "failed_coas": failed_coas,
        "at_risk_jobs": at_risk_jobs,
        "budget": budget_amount,
        "budget_actual": budget_actual,
        "budget_variance": budget_amount - budget_actual,
    }


def _grounded_persona_response(
    persona: str, question: str, summary: dict[str, Any]
) -> str:
    problems = set(summary["problems"])
    risks: list[str] = []
    if summary["qa_holds"]:
        risks.append(f"{summary['qa_holds']} extraction run(s) are on QA hold")
    if summary["failed_coas"]:
        risks.append(f"{summary['failed_coas']} COA(s) failed")
    if summary["at_risk_jobs"]:
        risks.append(f"{summary['at_risk_jobs']} client job(s) are at risk")
    if summary["budget_variance"] < 0:
        risks.append(
            f"purchasing is ${abs(summary['budget_variance']):,.0f} over budget"
        )
    if "material_shortage" in problems:
        risks.append("raw-material coverage is constrained")
    if "machine_downtime" in problems:
        risks.append("a production line is unavailable")
    if "negative_margin" in problems:
        risks.append("some output runs are producing negative contribution margin")
    if not risks:
        risks.append("no critical injected incident is active")

    focus = {
        "Buyer": "Protect in-stock rates without buying deeper into slow or quarantined inventory.",
        "Operations Director": "Sequence the constraint, clear blocked work, and align production with demand.",
        "Production Manager": "Rebuild the production queue around available machines, labor, and released material.",
        "CFO": "Protect cash, stop negative-margin work, and require economic justification for emergency buys.",
        "Compliance Officer": "Keep every affected package on hold and preserve package, lot, COA, and disposition traceability.",
        "CEO": "Balance customer service, cash preservation, compliance exposure, and recovery speed.",
        "Quality Manager": "Contain affected lots, define release criteria, and prevent unreviewed material from moving downstream.",
        "Sales Director": "Reset customer promises using confirmed release and production dates, not optimistic capacity.",
    }.get(
        persona,
        "Protect the company while resolving the highest-consequence constraint first.",
    )
    next_action = {
        "Buyer": "Freeze nonessential POs, reorder only released fast movers below 14 days of supply, and redirect budget from slow movers.",
        "Operations Director": "Run a two-hour constraint review and publish one recovery schedule with owner, dependency, and release gate for every blocked order.",
        "Production Manager": "Move feasible work to active lines, reserve released input lots, and reschedule orders using demonstrated rates and crew capacity.",
        "CFO": "Pause negative-margin and discretionary spend, collect overdue invoices, and approve only purchases tied to protected revenue.",
        "Compliance Officer": "Lock affected packages and production orders, document the discrepancy, and release only after QA and traceability records agree.",
        "CEO": "Authorize a single recovery plan, assign an executive owner, and communicate realistic commitments to customers and staff.",
        "Quality Manager": "Open a deviation, quarantine the affected lots, confirm sampling and root-cause steps, and define written release criteria.",
        "Sales Director": "Contact at-risk accounts today with revised dates and offer substitutes only from released, traceable inventory.",
    }.get(persona, "Resolve the highest-consequence issue before adding new work.")
    company_name = summary["company"].get(
        "company_name", "the simulated company"
    )
    return (
        f"### {persona} assessment\n"
        f"**Question:** {question.strip() or 'What requires attention now?'}\n\n"
        f"At {company_name}, the current operating picture is {summary['sku_count']:,} SKUs, "
        f"${summary['net_sales']:,.0f} in simulated sales, {summary['extraction_runs']:,} extraction runs, "
        f"and ${summary['budget_variance']:,.0f} of remaining purchasing variance.\n\n"
        f"**What matters most:** {'; '.join(risks)}.\n\n"
        "**Consequence:** Uncoordinated action can convert a manageable constraint into missed revenue, excess inventory, "
        "customer churn, or a compliance release failure.\n\n"
        f"**Role priority:** {focus}\n\n"
        f"**Safest next action:** {next_action}"
    )


def run_demo_roleplay(
    state: MutableMapping[str, Any], persona: str, question: str
) -> dict[str, Any]:
    if persona not in PERSONAS:
        raise ValueError(f"Unsupported persona: {persona}")
    summary = demo_company_summary(state)
    result: dict[str, Any] | None = None
    try:
        from services.doobie_client import DoobieClient
        from services.doobie_config import resolve_doobie_config

        config = resolve_doobie_config()
        client = DoobieClient(
            str(config.get("base_url") or ""),
            str(config.get("api_key") or ""),
            timeout_seconds=8,
        )
        if client.enabled:
            result = client.copilot(
                question=question,
                persona=persona.casefold().replace(" ", "_"),
                data={
                    "simulated_company": summary,
                    "instruction": "Explain the consequence and safest next action.",
                },
            )
            if result.get("mode") == "fallback" or not str(
                result.get("answer") or ""
            ).strip():
                result = None
    except Exception:
        result = None
    if result is None:
        result = {
            "answer": _grounded_persona_response(persona, question, summary),
            "explanation": "Generated from the current simulated company state.",
            "recommendations": [],
            "confidence": "medium",
            "sources": ["simulated_company_state"],
            "mode": "grounded_demo_fallback",
        }
    state.setdefault("demo_training_history", []).append(
        {
            "date": summary["as_of_date"],
            "persona": persona,
            "question": question,
            "answer": result.get("answer", ""),
            "mode": result.get("mode", "unknown"),
        }
    )
    return result


def _match_demo_upload(label: str, key: str) -> str | None:
    text = f"{label} {key}".casefold()
    if "quarantine" in text:
        return "buyer_quarantine"
    if "compliance" in text and ("source" in text or "qa" in text):
        return "compliance_sources"
    if "manifest" in text:
        return "delivery_manifest"
    if "extraction" in text and "inventory" in text:
        return "extraction_inventory"
    if "extraction" in text and any(
        term in text for term in ("run", "partner", "log")
    ):
        return "extraction_runs"
    if "extraction" in text and "job" in text:
        return "extraction_jobs"
    if "extra sales" in text or "sales detail" in text:
        return "buyer_extra_sales"
    if "product sales" in text:
        return "buyer_sales"
    if ("sales report" in text and "product" not in text) or (
        "delivery" in text and "sales" in text
    ):
        return "delivery_sales"
    if "inventory" in text:
        return "buyer_inventory"
    return None


def install_demo_upload_support(streamlit_module: Any) -> None:
    st = streamlit_module
    original = st.file_uploader
    if getattr(original, "_full_app_demo_wrapper", False):
        return

    def make_wrapper(callable_: Any) -> Any:
        def wrapped(label: Any, *args: Any, **kwargs: Any) -> Any:
            uploaded = callable_(label, *args, **kwargs)
            if uploaded not in (None, []):
                return uploaded
            state = st.session_state
            if not demo_enabled_for_state(state):
                return uploaded
            if not isinstance(state.get("demo_upload_catalog"), dict):
                ensure_full_app_demo_session(
                    state,
                    actor=str(
                        state.get("admin_user")
                        or state.get("user_user")
                        or "demo"
                    ),
                )
            source = _match_demo_upload(
                str(label), str(kwargs.get("key") or "")
            )
            spec = (
                state.get("demo_upload_catalog", {}).get(source)
                if source
                else None
            )
            if not spec:
                return uploaded
            name, content, mime = spec
            demo_file = DemoUploadedFile(content, name, mime)
            return [demo_file] if kwargs.get("accept_multiple_files") else demo_file

        wrapped._full_app_demo_wrapper = True
        return wrapped

    st.file_uploader = make_wrapper(original)
    try:
        st.sidebar.file_uploader = make_wrapper(st.sidebar.file_uploader)
    except Exception:
        pass


def bootstrap_demo_session(streamlit_module: Any) -> DemoSeedResult | None:
    st = streamlit_module
    state = st.session_state
    if not demo_enabled_for_state(state):
        return None
    actor = str(
        state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_user_id")
        or "demo"
    )
    return ensure_full_app_demo_session(state, actor=actor)


def render_demo_control_panel(streamlit_module: Any) -> None:
    st = streamlit_module
    state = st.session_state
    if (
        not demo_enabled_for_state(state)
        or state.get("_demo_control_rendered")
        or state.get("_demo_rendering_panel")
    ):
        return
    state["_demo_rendering_panel"] = True
    try:
        ensure_full_app_demo_session(
            state,
            actor=str(
                state.get("admin_user") or state.get("user_user") or "demo"
            ),
        )
        with st.sidebar.expander("Simulation Control Center", expanded=False):
            profile = dict(state.get("demo_company_profile") or {})
            st.caption(
                f"{profile.get('company_name', 'Demo company')} • "
                f"{_as_date(state.get('demo_as_of_date')).isoformat()}"
            )
            scale = st.selectbox(
                "Dataset size",
                list(DATASET_SCALES),
                index=list(DATASET_SCALES).index(
                    str(state.get("demo_dataset_scale") or "medium")
                ),
                key="demo_control_scale",
            )
            scenario_names = list(SCENARIO_PROBLEMS)
            current_scenario = str(
                state.get("demo_selected_scenario") or "Healthy baseline"
            )
            scenario = st.selectbox(
                "Operational scenario",
                scenario_names,
                index=(
                    scenario_names.index(current_scenario)
                    if current_scenario in scenario_names
                    else 0
                ),
                key="demo_control_scenario",
            )
            col_a, col_b = st.columns(2)
            if col_a.button(
                "Regenerate", key="demo_regenerate", use_container_width=True
            ):
                state["demo_dataset_scale"] = scale
                regenerate_demo_company(state, actor="control-center")
                st.rerun()
            if col_b.button(
                "Advance 30 days",
                key="demo_advance_30",
                use_container_width=True,
            ):
                advance_demo_company(state, days=30, actor="control-center")
                st.rerun()
            col_c, col_d = st.columns(2)
            if col_c.button(
                "Inject scenario", key="demo_inject", use_container_width=True
            ):
                state["demo_dataset_scale"] = scale
                inject_demo_problem(state, scenario, actor="control-center")
                st.rerun()
            if col_d.button(
                "Reset demo", key="demo_reset", use_container_width=True
            ):
                reset_demo_session(
                    state, preserve_auth=True, reset_database=True
                )
                ensure_full_app_demo_session(
                    state, actor="control-center", force=True
                )
                st.rerun()
            st.caption("Independent randomization")
            random_cols = st.columns(3)
            for idx, dimension in enumerate(("company", "catalog", "history")):
                if random_cols[idx].button(
                    dimension.title(),
                    key=f"demo_random_{dimension}",
                    use_container_width=True,
                ):
                    randomize_demo_dimension(
                        state, dimension, actor="control-center"
                    )
                    st.rerun()

            summary = demo_company_summary(state)
            st.caption(
                f"{summary['sku_count']:,} SKUs • ${summary['net_sales']:,.0f} sales • "
                f"{summary['qa_holds']} QA holds • {summary['at_risk_jobs']} at-risk jobs"
            )
            if state.get("_coman_demo_error"):
                st.warning(
                    f"Co-Man durable seed unavailable: {state['_coman_demo_error']}"
                )

            st.markdown("#### Executive role training")
            persona = st.selectbox(
                "Act as", list(PERSONAS), key="demo_training_persona"
            )
            question = st.text_area(
                "Decision or situation",
                value=(
                    "What is the highest-consequence issue and what should we do next?"
                ),
                key="demo_training_question",
                height=90,
            )
            if st.button(
                "Run role assessment",
                key="demo_training_run",
                use_container_width=True,
            ):
                result = run_demo_roleplay(state, persona, question)
                state["demo_last_training_answer"] = result.get("answer", "")
            if state.get("demo_last_training_answer"):
                st.markdown(str(state["demo_last_training_answer"]))
    finally:
        state["_demo_rendering_panel"] = False
        state["_demo_control_rendered"] = True


def install_demo_runtime(streamlit_module: Any) -> None:
    """Install bootstrap, upload overrides, and a global control-center render hook."""
    st = streamlit_module
    st.session_state["_demo_control_rendered"] = False
    st.session_state["_demo_rendering_panel"] = False
    install_demo_upload_support(st)
    bootstrap_demo_session(st)

    original_page_config = st.set_page_config
    if not getattr(original_page_config, "_demo_runtime_wrapper", False):
        def page_config_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = original_page_config(*args, **kwargs)
            bootstrap_demo_session(st)
            render_demo_control_panel(st)
            return result

        page_config_wrapper._demo_runtime_wrapper = True
        st.set_page_config = page_config_wrapper

    try:
        original_sidebar_selectbox = st.sidebar.selectbox
        if not getattr(
            original_sidebar_selectbox, "_demo_runtime_wrapper", False
        ):
            def sidebar_selectbox_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not st.session_state.get("_demo_control_rendered"):
                    render_demo_control_panel(st)
                return original_sidebar_selectbox(*args, **kwargs)

            sidebar_selectbox_wrapper._demo_runtime_wrapper = True
            st.sidebar.selectbox = sidebar_selectbox_wrapper
    except Exception:
        pass
