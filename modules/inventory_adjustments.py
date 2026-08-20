from __future__ import annotations

from collections.abc import MutableMapping
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import create_coman_engine
from modules.coman.models import InventoryLot, InventoryTransaction
from modules.data_hub_repository import DataHubRepository
from services.inventory_state import get_active_inventory_df, set_active_inventory_df
from services.metrc_inventory_adjustments import (
    fetch_package_adjustment_reasons,
    submit_package_adjustment,
)


LOCAL_REASONS = (
    "Inventory count correction",
    "Scale variance",
    "Damage / destruction",
    "Waste / disposal",
    "Found inventory",
    "Entry error",
    "Other",
)
ADJUSTMENT_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}
JOURNAL_DATASET_KEY = "inventory_adjustment_journal"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return "".join(ch.lower() for ch in _clean(value) if ch.isalnum())


def _actor(state: MutableMapping[str, Any]) -> str:
    return _clean(
        state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_username")
        or state.get("auth_user_id")
        or "system"
    )


def can_adjust_inventory(state: MutableMapping[str, Any]) -> bool:
    role = _clean(state.get("auth_user_role")).casefold()
    if not role and bool(state.get("is_admin")):
        role = "admin"
    return role in ADJUSTMENT_ROLES


def _pick(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    if frame is None or frame.empty:
        return None
    lookup = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        found = lookup.get(_norm(alias))
        if found:
            return found
    return None


def _credentials(state: MutableMapping[str, Any]):
    try:
        from modules.inventory_receiving import resolve_traceability_credentials

        return resolve_traceability_credentials(state)
    except Exception:
        return None


def _reason_rows(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    credentials = _credentials(state)
    scope = f"{_clean(state.get('active_facility_id'))}|{getattr(credentials, 'license_number', '')}"
    cached = state.get("_inventory_adjustment_reasons")
    if isinstance(cached, dict) and cached.get("scope") == scope and isinstance(cached.get("rows"), list):
        return list(cached["rows"])
    rows: list[dict[str, Any]] = []
    if credentials is not None and getattr(credentials, "configured", False):
        result = fetch_package_adjustment_reasons(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            license_number=credentials.license_number,
        )
        if result.get("ok"):
            rows = [dict(item) for item in result.get("reasons") or [] if isinstance(item, dict)]
    if not rows:
        rows = [{"Name": reason, "RequiresNote": reason == "Other"} for reason in LOCAL_REASONS]
    state["_inventory_adjustment_reasons"] = {"scope": scope, "rows": rows}
    return rows


def _journal_entries(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    if not organization_id or not facility_id:
        return []
    try:
        source = next(
            (
                item
                for item in DataHubRepository(create_coman_engine()).list_active_sources(organization_id, facility_id)
                if item.dataset_key == JOURNAL_DATASET_KEY
            ),
            None,
        )
        if source is None:
            return []
        payload = json.loads(source.payload.decode("utf-8"))
        rows = payload.get("entries") if isinstance(payload, dict) else []
        return [dict(row) for row in rows if isinstance(row, dict)]
    except Exception:
        return []


def _append_journal(state: MutableMapping[str, Any], entry: dict[str, Any]) -> None:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    if not organization_id or not facility_id:
        return
    entries = _journal_entries(state)
    entries.append(dict(entry))
    entries = entries[-1000:]
    payload = json.dumps({"entries": entries}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    DataHubRepository(create_coman_engine()).publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key=JOURNAL_DATASET_KEY,
        dataset_label="Inventory Adjustment Journal",
        cache_key="_cache_inventory_adjustments",
        filename="inventory_adjustment_journal.json",
        fingerprint=hashlib.sha256(payload).hexdigest(),
        payload=payload,
        inspection={"rows": len(entries), "columns": len(entry), "quality": "Ready", "matches": {}, "missing": []},
        content_type="application/json",
        imported_by_user_id=state.get("auth_user_id"),
        imported_by=_actor(state),
        retain_versions=10,
    )


def _retail_current_and_row(package_id: str) -> tuple[pd.DataFrame, int, float, float, str]:
    current, _ = get_active_inventory_df()
    if current.empty:
        raise ValueError("No active retail inventory is loaded.")
    package_col = _pick(current, ("External Package ID", "METRC Package ID", "Package ID", "package_id"))
    if not package_col:
        raise ValueError("The active inventory source does not contain an External Package ID column.")
    matches = current[current[package_col].fillna("").astype(str).str.strip().str.casefold() == package_id.casefold()]
    if len(matches) != 1:
        raise ValueError("The selected package could not be uniquely matched in the active retail inventory.")
    index = int(matches.index[0])
    reserved_col = _pick(current, ("Reserved", "Reserved Quantity", "Allocated", "Committed"))
    reserved = float(pd.to_numeric(current.loc[index, reserved_col], errors="coerce") or 0.0) if reserved_col else 0.0
    total_col = _pick(current, ("On Hand Total", "On Hand", "Quantity", "Qty"))
    available_col = _pick(current, ("Available",))
    if total_col:
        total = float(pd.to_numeric(current.loc[index, total_col], errors="coerce") or 0.0)
    elif available_col:
        total = float(pd.to_numeric(current.loc[index, available_col], errors="coerce") or 0.0) + reserved
    else:
        raise ValueError("The active inventory source does not contain an adjustable quantity column.")
    unit_col = _pick(current, ("Inventory Unit", "Unit", "UOM"))
    unit = _clean(current.loc[index, unit_col]) if unit_col else "unit"
    return current, index, total, reserved, unit or "unit"


def _persist_retail_snapshot(state: MutableMapping[str, Any], updated: pd.DataFrame, package_id: str) -> str:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before adjusting inventory.")
    payload = updated.to_csv(index=False).encode("utf-8")
    filename = f"inventory_after_adjustment_{''.join(ch if ch.isalnum() else '_' for ch in package_id)[-32:]}.csv"
    record = DataHubRepository(create_coman_engine()).publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key="inventory",
        dataset_label="Inventory",
        cache_key="_cache_inv",
        filename=filename,
        fingerprint=hashlib.sha256(payload).hexdigest(),
        payload=payload,
        inspection={"rows": len(updated), "columns": len(updated.columns), "quality": "Ready", "matches": {}, "missing": []},
        content_type="text/csv",
        imported_by_user_id=state.get("auth_user_id"),
        imported_by=_actor(state),
    )
    state["_cache_inv"] = {
        "name": filename,
        "bytes": payload,
        "fingerprint": hashlib.sha256(payload).hexdigest(),
        "dataset": "Inventory",
        "durable_id": record.id,
        "durable": True,
        "rows": len(updated),
        "columns": len(updated.columns),
        "quality": "Ready",
    }
    set_active_inventory_df(updated, source_name=filename, source_type="inventory_adjustment")
    return str(record.id)


def _apply_retail_local(state: MutableMapping[str, Any], package_id: str, final_quantity: float) -> tuple[float, str]:
    current, index, current_total, reserved, unit = _retail_current_and_row(package_id)
    if final_quantity < reserved - 1e-9:
        raise ValueError(f"Final quantity cannot be below {reserved:g} currently reserved.")
    delta = final_quantity - current_total
    updated = current.copy()
    total_columns = [column for column in ("On Hand Total", "On Hand", "Quantity") if column in updated.columns]
    for column in total_columns:
        updated.at[index, column] = final_quantity
    available_col = _pick(updated, ("Available",))
    if available_col:
        updated.at[index, available_col] = max(0.0, final_quantity - reserved)
    if not total_columns and not available_col:
        raise ValueError("No writable retail quantity column was found.")
    _persist_retail_snapshot(state, updated, package_id)
    return delta, unit


def _production_snapshot(state: MutableMapping[str, Any], lot_id: str) -> tuple[float, str]:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    sessions = sessionmaker(bind=create_coman_engine(), expire_on_commit=False, future=True)
    with sessions() as session:
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
            raise ValueError("The selected production lot is outside the active facility.")
        balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot_id)) or 0.0)
        unit = session.scalar(select(InventoryTransaction.unit).where(InventoryTransaction.lot_id == lot_id).order_by(InventoryTransaction.occurred_at.desc()).limit(1))
    return balance, _clean(unit) or "unit"


def _apply_production_local(
    state: MutableMapping[str, Any], lot_id: str, *, final_quantity: float, reason: str, note: str, external_status: str
) -> tuple[float, str]:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    current, unit = _production_snapshot(state, lot_id)
    delta = final_quantity - current
    sessions = sessionmaker(bind=create_coman_engine(), expire_on_commit=False, future=True)
    with sessions.begin() as session:
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
            raise ValueError("The selected production lot is outside the active facility.")
        session.add(
            InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot_id,
                transaction_type="inventory_adjustment",
                quantity_delta=delta,
                unit=unit,
                reason=_clean(reason),
                reference=(f"Inventory adjustment | external={external_status} | {_clean(note)}")[:255],
                actor=_actor(state),
            )
        )
    return delta, unit


def apply_inventory_adjustment(
    state: MutableMapping[str, Any],
    *,
    operation_mode: str,
    package_id: str,
    durable_lot_id: str,
    adjustment_type: str,
    entered_quantity: float,
    reason: str,
    reason_note: str,
    sync_to_metrc: bool,
    bypass_state_system: bool,
) -> dict[str, Any]:
    if not can_adjust_inventory(state):
        raise PermissionError("Your Buyer Dash role does not allow inventory adjustments.")
    package_id = _clean(package_id)
    if not package_id:
        raise ValueError("An External Package ID is required.")
    mode = _clean(adjustment_type).casefold()
    is_production = _clean(operation_mode).casefold().startswith("production")

    if is_production:
        current, unit = _production_snapshot(state, durable_lot_id)
    else:
        _frame, _index, current, _reserved, unit = _retail_current_and_row(package_id)
    final_quantity = current + float(entered_quantity) if mode.startswith("increment") else float(entered_quantity)
    if final_quantity < -1e-9:
        raise ValueError("Final inventory quantity cannot be negative.")
    final_quantity = max(0.0, final_quantity)
    delta = final_quantity - current
    if abs(delta) <= 1e-9:
        raise ValueError("The adjustment does not change the current quantity.")

    credentials = _credentials(state)
    metrc_status = "not_configured"
    if sync_to_metrc and not bypass_state_system:
        if credentials is None or not getattr(credentials, "configured", False):
            raise ValueError("Metrc sync was requested, but this user/facility does not have a complete Metrc connection.")
        result = submit_package_adjustment(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            license_number=credentials.license_number,
            package_label=package_id,
            adjustment_type="incremental" if mode.startswith("increment") else "absolute",
            quantity=delta if mode.startswith("increment") else final_quantity,
            unit=unit,
            reason=reason,
            reason_note=reason_note,
        )
        if not result.get("ok"):
            raise RuntimeError(str(result.get("message") or "Metrc rejected the inventory adjustment."))
        metrc_status = "synced"
    elif bypass_state_system:
        metrc_status = "bypassed"

    if is_production:
        local_delta, local_unit = _apply_production_local(
            state,
            durable_lot_id,
            final_quantity=final_quantity,
            reason=reason,
            note=reason_note,
            external_status=metrc_status,
        )
    else:
        local_delta, local_unit = _apply_retail_local(state, package_id, final_quantity)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": _actor(state),
        "operation_mode": operation_mode,
        "external_package_id": package_id,
        "durable_lot_id": durable_lot_id,
        "adjustment_type": "Incremental" if mode.startswith("increment") else "Set Quantity",
        "previous_quantity": current,
        "delta": local_delta,
        "final_quantity": final_quantity,
        "unit": local_unit,
        "reason": _clean(reason),
        "reason_note": _clean(reason_note),
        "metrc_status": metrc_status,
    }
    try:
        _append_journal(state, entry)
    except Exception:
        pass
    return entry


def open_inventory_adjustment_dialog(
    state: MutableMapping[str, Any], rows: pd.DataFrame | list[dict[str, Any]], *, operation_mode: str
) -> int:
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows or [])
    candidates: list[dict[str, Any]] = []
    if not frame.empty:
        for _, row in frame.iterrows():
            package_id = _clean(row.get("External Package ID") or row.get("Package ID"))
            if not package_id:
                continue
            available = float(pd.to_numeric(row.get("Available"), errors="coerce") or 0.0)
            reserved = float(pd.to_numeric(row.get("Reserved"), errors="coerce") or 0.0)
            candidates.append(
                {
                    "Product": _clean(row.get("Product")),
                    "External Package ID": package_id,
                    "Durable Lot ID": _clean(row.get("Durable Lot ID")),
                    "Current": available if _clean(operation_mode).casefold().startswith("production") else available + reserved,
                    "Unit": _clean(row.get("Unit")) or "unit",
                }
            )
    state["inventory_adjustment_candidates"] = candidates
    state["inventory_adjustment_operation_mode"] = operation_mode
    state["inventory_adjustment_open"] = bool(candidates)
    return len(candidates)


def render_inventory_adjustment_dialog(state: MutableMapping[str, Any]) -> None:
    if not state.get("inventory_adjustment_open"):
        return
    candidates = [dict(row) for row in state.get("inventory_adjustment_candidates", []) if isinstance(row, dict)]
    if not candidates:
        state["inventory_adjustment_open"] = False
        return

    def body() -> None:
        head = st.columns([3, 1])
        with head[0]:
            st.caption("INVENTORY / ADJUST")
            st.markdown("## Adjust inventory")
            st.caption("Every adjustment requires a reason and is recorded in the inventory adjustment journal.")
        if head[1].button("Close", key="inventory_adjustment_close"):
            state["inventory_adjustment_open"] = False
            st.rerun()

        if not can_adjust_inventory(state):
            st.error("Your Buyer Dash role does not allow inventory adjustments.")
            return

        labels = [f"{row['Product']} · {row['External Package ID']}" for row in candidates]
        selected_label = st.selectbox("Package *", labels, key="inventory_adjustment_target")
        target = candidates[labels.index(selected_label)]
        current = float(target.get("Current") or 0.0)
        unit = _clean(target.get("Unit")) or "unit"
        st.metric("Current quantity", f"{current:,.3f} {unit}".rstrip("0").rstrip("."))

        mode = st.segmented_control(
            "Adjustment type *",
            ["Incremental", "Set Quantity"],
            default="Incremental",
            key="inventory_adjustment_type",
        ) or "Incremental"
        if mode == "Incremental":
            entered = st.number_input("Change (+ / -) *", value=0.0, step=0.1, key="inventory_adjustment_value")
            final = current + float(entered)
        else:
            entered = st.number_input("New quantity *", min_value=0.0, value=float(current), step=0.1, key="inventory_adjustment_value_absolute")
            final = float(entered)
        st.caption(f"Final quantity: {final:,.3f} {unit}".rstrip("0").rstrip("."))

        reason_rows = _reason_rows(state)
        reason_names = [_clean(item.get("Name")) for item in reason_rows if _clean(item.get("Name"))]
        reason = st.selectbox("Reason *", reason_names, key="inventory_adjustment_reason")
        reason_meta = next((row for row in reason_rows if _clean(row.get("Name")) == reason), {})
        note_required = bool(reason_meta.get("RequiresNote"))
        note = st.text_area("Reason note *" if note_required else "Reason note", key="inventory_adjustment_note")

        credentials = _credentials(state)
        metrc_ready = bool(credentials is not None and getattr(credentials, "configured", False))
        sync = st.toggle(
            "Sync adjustment to Metrc",
            value=metrc_ready,
            disabled=not metrc_ready,
            key="inventory_adjustment_sync",
            help="When enabled, Buyer Dash submits the package adjustment to Metrc before posting the local inventory change.",
        )
        role = _clean(state.get("auth_user_role")).casefold()
        can_bypass = role in {"dev", "admin"} or bool(state.get("is_admin"))
        bypass = st.toggle(
            "Bypass state system",
            value=False,
            disabled=not (metrc_ready and can_bypass),
            key="inventory_adjustment_bypass",
            help="Administrative exception for correcting Buyer Dash after the state system was already updated separately.",
        )
        if bypass:
            sync = False
            st.warning("This changes Buyer Dash only. Use bypass only when the state system has already been handled separately.")
        elif not metrc_ready:
            st.info("No complete Metrc connection is available for this user/facility. This adjustment will be local only.")

        reviewed = st.checkbox("I reviewed the package, final quantity, and adjustment reason.", key="inventory_adjustment_reviewed")
        if st.button("Adjust inventory", type="primary", width="stretch", disabled=not reviewed, key="inventory_adjustment_commit"):
            if final < 0:
                st.error("Final quantity cannot be negative.")
                return
            if note_required and not _clean(note):
                st.error("This adjustment reason requires a note.")
                return
            try:
                entry = apply_inventory_adjustment(
                    state,
                    operation_mode=_clean(state.get("inventory_adjustment_operation_mode")) or "Retail Ops",
                    package_id=target["External Package ID"],
                    durable_lot_id=target.get("Durable Lot ID", ""),
                    adjustment_type=mode,
                    entered_quantity=float(entered),
                    reason=reason,
                    reason_note=note,
                    sync_to_metrc=bool(sync),
                    bypass_state_system=bool(bypass),
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                state["inventory_adjustment_open"] = False
                state["inventory_adjustment_flash"] = (
                    f"Adjusted {entry['external_package_id']} by {entry['delta']:+,.3f} {entry['unit']} · final {entry['final_quantity']:,.3f}."
                )
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog("Adjust inventory", width="large")
        def dialog() -> None:
            body()
        dialog()
    else:
        with st.container(border=True):
            body()
