"""Inbound inventory receiving for Inventory v2.

The workflow intentionally separates state traceability acceptance from Buyer
Dash inventory posting. Live Metrc access is read-only here: Buyer Dash loads the
inbound queue and package details, requires external packages to already be
accepted, then posts a reviewed inventory snapshot through the existing durable
Data Hub source versioning path.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
import hashlib
from typing import Any

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.data_hub_repository import DataHubRepository
from services.inventory_state import get_active_inventory_df, set_active_inventory_df
from services.metrc_client import (
    fetch_metrc_delivery_packages,
    fetch_metrc_incoming_transfers,
    fetch_metrc_transfer_deliveries,
    get_default_metrc_integrator_key,
)
from user_integrations_store import UserIntegrationsStore


@dataclass(frozen=True)
class TraceabilityCredentials:
    configured: bool
    state: str = ""
    user_api_key: str = ""
    integrator_api_key: str = ""
    license_number: str = ""
    message: str = ""


CANONICAL_INVENTORY_COLUMNS = (
    "Product Name",
    "SKU",
    "Category",
    "Package ID",
    "Vendor",
    "Room",
    "On Hand",
    "Available",
    "Cost",
    "Med Price",
    "Status",
    "Received Date",
    "Expiration Date",
    "COA ID",
    "Traceability Manifest",
    "Traceability Source",
    "Lab Testing State",
    "Inventory Unit",
)


def _username(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_username")
        or state.get("auth_user_id")
        or ""
    ).strip()


def resolve_traceability_credentials(state: MutableMapping[str, Any]) -> TraceabilityCredentials:
    username = _username(state)
    if not username:
        return TraceabilityCredentials(False, message="No authenticated integration identity is available.")
    record = UserIntegrationsStore().get_user(username)
    if record is None:
        return TraceabilityCredentials(False, message="No Metrc integration is saved for this user.")
    integrator = str(get_default_metrc_integrator_key().get("api_key") or "").strip()
    configured = bool(record.metrc_api_key and record.metrc_state and record.metrc_license and integrator)
    return TraceabilityCredentials(
        configured=configured,
        state=str(record.metrc_state or ""),
        user_api_key=str(record.metrc_api_key or ""),
        integrator_api_key=integrator,
        license_number=str(record.metrc_license or ""),
        message="Metrc inbound queue is ready." if configured else "Connect Metrc and a facility license to load live inbound transfers.",
    )


def _first_frame(state: MutableMapping[str, Any], *keys: str) -> pd.DataFrame:
    for key in keys:
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy()
    return pd.DataFrame()


def _pick(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized = {str(column).strip().casefold(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias.casefold() in normalized:
            return normalized[alias.casefold()]
    return None


def build_sandbox_inbound_queue(state: MutableMapping[str, Any]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Adapt the durable DEV Sandbox delivery manifest into the same inbound UI."""

    manifest = _first_frame(state, "delivery_manifest_df", "delivery_raw_df")
    if manifest.empty:
        return pd.DataFrame(), {}
    manifest_col = _pick(manifest, ("Manifest #", "Manifest Number", "Manifest"))
    vendor_col = _pick(manifest, ("Vendor", "Shipper Facility Name"))
    package_col = _pick(manifest, ("Package ID", "METRC Package ID"))
    product_col = _pick(manifest, ("Product", "Product Name", "Item Name"))
    qty_col = _pick(manifest, ("Received Qty", "Quantity", "Shipped Quantity"))
    if not manifest_col or not product_col:
        return pd.DataFrame(), {}

    queue_rows: list[dict[str, Any]] = []
    package_sets: dict[str, pd.DataFrame] = {}
    for manifest_number, group in manifest.groupby(manifest_col, dropna=False):
        key = str(manifest_number or "Sandbox inbound").strip() or "Sandbox inbound"
        vendor = str(group[vendor_col].iloc[0] if vendor_col else "Sandbox Vendor")
        package_count = int(group[package_col].nunique()) if package_col else int(len(group))
        queue_rows.append(
            {
                "Transfer ID": key,
                "Manifest": key,
                "Vendor": vendor,
                "Package Count": package_count,
                "Received Count": 0,
                "Estimated Arrival": "Sandbox",
                "Source": "Sandbox",
                "Accepted in traceability": True,
            }
        )
        packages = pd.DataFrame(
            {
                "Incoming Item": group[product_col].astype(str),
                "Package ID": group[package_col].astype(str) if package_col else [f"SANDBOX-{index + 1}" for index in range(len(group))],
                "Quantity": pd.to_numeric(group[qty_col], errors="coerce").fillna(0.0) if qty_col else 0.0,
                "Unit": "unit",
                "Shipment State": "Accepted",
                "Lab Testing State": "Passed",
                "Category": group[_pick(group, ("Category",))].astype(str) if _pick(group, ("Category",)) else "",
                "Vendor": vendor,
                "SKU": group[_pick(group, ("SKU",))].astype(str) if _pick(group, ("SKU",)) else "",
                "COA ID": group[_pick(group, ("COA ID",))].astype(str) if _pick(group, ("COA ID",)) else "",
                "Unit Cost": pd.to_numeric(group[_pick(group, ("Unit Cost", "Cost"))], errors="coerce").fillna(0.0) if _pick(group, ("Unit Cost", "Cost")) else 0.0,
                "Retail Price": 0.0,
                "Expiration Date": "",
            }
        )
        package_sets[key] = packages.reset_index(drop=True)
    return pd.DataFrame(queue_rows), package_sets


def normalize_metrc_transfers(transfers: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in transfers:
        rows.append(
            {
                "Transfer ID": str(item.get("Id") or ""),
                "Delivery ID": str(item.get("DeliveryId") or ""),
                "Manifest": str(item.get("ManifestNumber") or ""),
                "Vendor": str(item.get("ShipperFacilityName") or item.get("ShipperFacilityLicenseNumber") or ""),
                "Vendor License": str(item.get("ShipperFacilityLicenseNumber") or ""),
                "Package Count": int(item.get("PackageCount") or item.get("DeliveryPackageCount") or 0),
                "Received Count": int(item.get("ReceivedPackageCount") or item.get("DeliveryReceivedPackageCount") or 0),
                "Estimated Arrival": str(item.get("EstimatedArrivalDateTime") or ""),
                "Source": "Metrc",
                "Accepted in traceability": bool(item.get("ReceivedDateTime")),
            }
        )
    return pd.DataFrame(rows)


def normalize_metrc_packages(packages: list[dict[str, Any]], *, vendor: str = "") -> pd.DataFrame:
    rows = []
    for item in packages:
        shipped = float(item.get("ShippedQuantity") or 0.0)
        received_raw = item.get("ReceivedQuantity")
        received = float(received_raw) if received_raw is not None else shipped
        rows.append(
            {
                "Incoming Item": str(item.get("ItemName") or ""),
                "Package ID": str(item.get("PackageLabel") or ""),
                "Quantity": received,
                "Unit": str(item.get("ReceivedUnitOfMeasureName") or item.get("ShippedUnitOfMeasureName") or "unit"),
                "Shipment State": str(item.get("ShipmentPackageState") or ""),
                "Lab Testing State": str(item.get("LabTestingState") or ""),
                "Category": str(item.get("ItemCategoryName") or ""),
                "Vendor": vendor,
                "SKU": "",
                "COA ID": "",
                "Unit Cost": 0.0,
                "Retail Price": 0.0,
                "Expiration Date": str(item.get("ExpirationDate") or ""),
            }
        )
    return pd.DataFrame(rows)


def _catalog_frame(state: MutableMapping[str, Any]) -> pd.DataFrame:
    catalog = _first_frame(state, "demo_catalog_df", "active_inventory_df", "inv_raw_df", "detail_product_cached_df")
    if catalog.empty:
        return catalog
    product_col = _pick(catalog, ("product_name", "Product Name", "Product", "name"))
    if not product_col:
        return pd.DataFrame()
    out = pd.DataFrame({"Product Name": catalog[product_col].fillna("").astype(str).str.strip()})
    sku_col = _pick(catalog, ("sku", "SKU"))
    category_col = _pick(catalog, ("category", "Category", "subcategory"))
    cost_col = _pick(catalog, ("unit_cost", "Unit Cost", "Cost"))
    retail_col = _pick(catalog, ("retail_price", "Retail Price", "Med Price", "Price"))
    out["SKU"] = catalog[sku_col].fillna("").astype(str).str.strip() if sku_col else ""
    out["Category"] = catalog[category_col].fillna("").astype(str).str.strip() if category_col else ""
    out["Unit Cost"] = pd.to_numeric(catalog[cost_col], errors="coerce").fillna(0.0) if cost_col else 0.0
    out["Retail Price"] = pd.to_numeric(catalog[retail_col], errors="coerce").fillna(0.0) if retail_col else 0.0
    return out.drop_duplicates(subset=["Product Name"]).reset_index(drop=True)


def prepare_receipt_editor(
    packages: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    default_room: str = "Receiving",
) -> pd.DataFrame:
    """Auto-match inbound items to the current product master without guessing."""

    if packages is None or packages.empty:
        return pd.DataFrame()
    catalog = catalog.copy() if isinstance(catalog, pd.DataFrame) else pd.DataFrame()
    exact = {
        str(row["Product Name"]).strip().casefold(): row
        for _, row in catalog.iterrows()
        if str(row.get("Product Name") or "").strip()
    }
    rows = []
    for _, package in packages.iterrows():
        incoming = str(package.get("Incoming Item") or "").strip()
        match = exact.get(incoming.casefold())
        rows.append(
            {
                **package.to_dict(),
                "Mapped Product": str(match.get("Product Name") or "") if match is not None else "",
                "Mapped SKU": str(match.get("SKU") or package.get("SKU") or "") if match is not None else str(package.get("SKU") or ""),
                "Mapped Category": str(match.get("Category") or package.get("Category") or "") if match is not None else str(package.get("Category") or ""),
                "Room": default_room,
                "Unit Cost": float(match.get("Unit Cost") or package.get("Unit Cost") or 0.0) if match is not None else float(package.get("Unit Cost") or 0.0),
                "Retail Price": float(match.get("Retail Price") or package.get("Retail Price") or 0.0) if match is not None else float(package.get("Retail Price") or 0.0),
            }
        )
    return pd.DataFrame(rows)


def validate_receipt_editor(editor: pd.DataFrame, *, require_traceability_acceptance: bool) -> list[str]:
    issues: list[str] = []
    if editor is None or editor.empty:
        return ["No inbound packages are selected."]
    if editor["Mapped Product"].fillna("").astype(str).str.strip().eq("").any():
        issues.append("Every incoming package must be matched to a Buyer Dash product.")
    if editor["Room"].fillna("").astype(str).str.strip().eq("").any():
        issues.append("Every incoming package needs a destination room.")
    if (pd.to_numeric(editor["Quantity"], errors="coerce").fillna(0.0) <= 0).any():
        issues.append("Every incoming package needs a positive received quantity.")
    package_ids = editor["Package ID"].fillna("").astype(str).str.strip()
    if package_ids.eq("").any() or package_ids.duplicated().any():
        issues.append("Package IDs must be present and unique within the receipt.")
    if require_traceability_acceptance:
        states = editor["Shipment State"].fillna("").astype(str).str.strip().str.casefold()
        if (~states.isin({"accepted", "received"})).any():
            issues.append("External state-traceability packages must be accepted before Buyer Dash can post them.")
    return issues


def _target_column(frame: pd.DataFrame, aliases: tuple[str, ...], fallback: str) -> str:
    found = _pick(frame, aliases)
    return found or fallback


def apply_receipt_to_inventory(current: pd.DataFrame, editor: pd.DataFrame, *, manifest: str, source: str) -> pd.DataFrame:
    """Return a new inventory snapshot while rejecting duplicate package receipts."""

    current = current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    if current.empty:
        current = pd.DataFrame(columns=list(CANONICAL_INVENTORY_COLUMNS))
    package_col = _target_column(current, ("Package ID", "METRC Package ID", "package_id"), "Package ID")
    if package_col not in current.columns:
        current[package_col] = ""
    existing_packages = {str(value).strip().casefold() for value in current[package_col].dropna().tolist() if str(value).strip()}
    incoming_packages = [str(value).strip() for value in editor["Package ID"].tolist()]
    duplicates = [value for value in incoming_packages if value.casefold() in existing_packages]
    if duplicates:
        raise ValueError(f"Package already exists in inventory: {duplicates[0]}")

    mapping = {
        "product": _target_column(current, ("Product Name", "Product", "product_name"), "Product Name"),
        "sku": _target_column(current, ("SKU", "sku"), "SKU"),
        "category": _target_column(current, ("Category", "category", "Master Category"), "Category"),
        "package": package_col,
        "vendor": _target_column(current, ("Vendor", "vendor"), "Vendor"),
        "room": _target_column(current, ("Room", "Location", "room"), "Room"),
        "on_hand": _target_column(current, ("On Hand", "Available", "Quantity", "on_hand"), "On Hand"),
        "cost": _target_column(current, ("Cost", "Unit Cost", "unit_cost"), "Cost"),
        "price": _target_column(current, ("Med Price", "Retail Price", "Price", "retail_price"), "Med Price"),
        "status": _target_column(current, ("Status", "status"), "Status"),
        "received": _target_column(current, ("Received Date", "received_date"), "Received Date"),
        "expiration": _target_column(current, ("Expiration Date", "expiration_date"), "Expiration Date"),
        "coa": _target_column(current, ("COA ID", "coa_id"), "COA ID"),
        "manifest": _target_column(current, ("Traceability Manifest", "Manifest #", "Manifest Number"), "Traceability Manifest"),
        "source": _target_column(current, ("Traceability Source",), "Traceability Source"),
        "lab": _target_column(current, ("Lab Testing State",), "Lab Testing State"),
        "unit": _target_column(current, ("Inventory Unit", "Unit"), "Inventory Unit"),
    }
    for column in mapping.values():
        if column not in current.columns:
            current[column] = ""

    now = pd.Timestamp.now(tz="UTC").isoformat()
    new_rows = []
    for _, row in editor.iterrows():
        payload = {column: "" for column in current.columns}
        payload[mapping["product"]] = str(row.get("Mapped Product") or "")
        payload[mapping["sku"]] = str(row.get("Mapped SKU") or "")
        payload[mapping["category"]] = str(row.get("Mapped Category") or row.get("Category") or "")
        payload[mapping["package"]] = str(row.get("Package ID") or "")
        payload[mapping["vendor"]] = str(row.get("Vendor") or "")
        payload[mapping["room"]] = str(row.get("Room") or "Receiving")
        payload[mapping["on_hand"]] = float(row.get("Quantity") or 0.0)
        payload[mapping["cost"]] = float(row.get("Unit Cost") or 0.0)
        payload[mapping["price"]] = float(row.get("Retail Price") or 0.0)
        payload[mapping["status"]] = "Available"
        payload[mapping["received"]] = now
        payload[mapping["expiration"]] = str(row.get("Expiration Date") or "")
        payload[mapping["coa"]] = str(row.get("COA ID") or "")
        payload[mapping["manifest"]] = str(manifest or "")
        payload[mapping["source"]] = str(source or "")
        payload[mapping["lab"]] = str(row.get("Lab Testing State") or "")
        payload[mapping["unit"]] = str(row.get("Unit") or "unit")
        new_rows.append(payload)
    return pd.concat([current, pd.DataFrame(new_rows, columns=current.columns)], ignore_index=True)


def persist_received_inventory(
    state: MutableMapping[str, Any], updated: pd.DataFrame, *, manifest: str, actor: str
) -> str:
    """Publish the new Inventory snapshot through the existing durable Data Hub repository."""

    organization_id = str(state.get("active_organization_id") or "").strip()
    facility_id = str(state.get("active_facility_id") or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before posting inventory.")
    payload = updated.to_csv(index=False).encode("utf-8")
    fingerprint = hashlib.sha256(payload).hexdigest()
    safe_manifest = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(manifest or "receipt"))
    filename = f"inventory_after_{safe_manifest or 'receipt'}.csv"
    repository = DataHubRepository(create_coman_engine())
    record = repository.publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key="inventory",
        dataset_label="Inventory",
        cache_key="_cache_inv",
        filename=filename,
        fingerprint=fingerprint,
        payload=payload,
        inspection={"rows": len(updated), "columns": len(updated.columns), "quality": "Ready", "matches": {}, "missing": []},
        content_type="text/csv",
        imported_by_user_id=state.get("auth_user_id"),
        imported_by=actor or "system",
    )
    state["_cache_inv"] = {
        "name": filename,
        "bytes": payload,
        "fingerprint": fingerprint,
        "dataset": "Inventory",
        "durable_id": record.id,
        "durable": True,
        "rows": len(updated),
        "columns": len(updated.columns),
        "quality": "Ready",
    }
    set_active_inventory_df(updated, source_name=filename, source_type="inbound_receipt")
    return str(record.id)


def _refresh_live_queue(state: MutableMapping[str, Any], credentials: TraceabilityCredentials) -> tuple[bool, str]:
    result = fetch_metrc_incoming_transfers(
        state=credentials.state,
        user_api_key=credentials.user_api_key,
        integrator_api_key=credentials.integrator_api_key,
        license_number=credentials.license_number,
    )
    if not result.get("ok"):
        return False, str(result.get("message") or "Metrc inbound queue could not be loaded.")
    queue = normalize_metrc_transfers(result.get("transfers") or [])
    state["inventory_inbound_queue_df"] = queue
    state["inventory_inbound_source"] = "Metrc"
    state.pop("inventory_inbound_packages_df", None)
    return True, f"Loaded {len(queue)} inbound transfer(s) from Metrc."


def _load_live_packages(
    state: MutableMapping[str, Any], credentials: TraceabilityCredentials, transfer: pd.Series
) -> tuple[bool, str]:
    delivery_ids: list[str] = []
    direct_delivery = str(transfer.get("Delivery ID") or "").strip()
    if direct_delivery:
        delivery_ids.append(direct_delivery)
    if not delivery_ids:
        result = fetch_metrc_transfer_deliveries(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            transfer_id=str(transfer.get("Transfer ID") or ""),
        )
        if not result.get("ok"):
            return False, str(result.get("message") or "Metrc delivery details could not be loaded.")
        for delivery in result.get("deliveries") or []:
            delivery_id = str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip()
            if delivery_id:
                delivery_ids.append(delivery_id)
    package_rows: list[dict[str, Any]] = []
    for delivery_id in delivery_ids:
        result = fetch_metrc_delivery_packages(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            delivery_id=delivery_id,
        )
        if not result.get("ok"):
            return False, str(result.get("message") or "Metrc package details could not be loaded.")
        package_rows.extend(result.get("packages") or [])
    packages = normalize_metrc_packages(package_rows, vendor=str(transfer.get("Vendor") or ""))
    state["inventory_inbound_packages_df"] = packages
    state["inventory_inbound_package_transfer_id"] = str(transfer.get("Transfer ID") or "")
    return True, f"Loaded {len(packages)} package(s) for this inbound transfer."


def _receiving_css() -> None:
    st.markdown(
        """
        <style>
        .recv-kicker{color:#ff9a3c;font-size:.66rem;font-weight:820;letter-spacing:.14em;text-transform:uppercase}
        .recv-help{padding:.6rem .7rem;border:1px solid rgba(255,154,60,.17);border-radius:10px;background:rgba(255,154,60,.055);color:#bbb2aa!important;font-size:.76rem;margin:.35rem 0 .65rem}
        .recv-step{color:#aaa49e!important;font-size:.68rem;font-weight:760;letter-spacing:.08em;text-transform:uppercase;margin-top:.5rem}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_receive_inventory(state: MutableMapping[str, Any]) -> None:
    _receiving_css()
    credentials = resolve_traceability_credentials(state)
    is_sandbox = str(state.get("active_organization_name") or "").strip().casefold() == "dev sandbox"

    st.markdown('<div class="recv-kicker">INBOUND INVENTORY</div>', unsafe_allow_html=True)
    st.markdown("## Receive inventory")
    st.markdown(
        '<div class="recv-help"><strong>Buyer Dash flow:</strong> Inbound Queue → Match Products → Receive Details → Review → Post Inventory → Labels. Live Metrc access is read-only here. External packages must already be accepted in the state traceability system before Buyer Dash posts them.</div>',
        unsafe_allow_html=True,
    )

    top = st.columns([1.5, 1.2, 1.2])
    top[0].caption(credentials.message if not is_sandbox else "DEV Sandbox is using its durable inbound manifest dataset.")
    if credentials.configured and top[1].button("Refresh Metrc queue", width="stretch", key="recv_refresh_metrc"):
        ok, message = _refresh_live_queue(state, credentials)
        (st.success if ok else st.error)(message)
        if ok:
            st.rerun()
    if is_sandbox and top[2].button("Use Sandbox queue", width="stretch", key="recv_use_sandbox"):
        queue, packages_by_manifest = build_sandbox_inbound_queue(state)
        state["inventory_inbound_queue_df"] = queue
        state["inventory_inbound_sandbox_packages"] = packages_by_manifest
        state["inventory_inbound_source"] = "Sandbox"
        st.rerun()

    if is_sandbox and not isinstance(state.get("inventory_inbound_queue_df"), pd.DataFrame):
        queue, packages_by_manifest = build_sandbox_inbound_queue(state)
        state["inventory_inbound_queue_df"] = queue
        state["inventory_inbound_sandbox_packages"] = packages_by_manifest
        state["inventory_inbound_source"] = "Sandbox"

    queue = state.get("inventory_inbound_queue_df")
    if not isinstance(queue, pd.DataFrame) or queue.empty:
        st.info("No inbound transfers are loaded. Refresh Metrc or use the Sandbox queue.")
        return

    st.markdown('<div class="recv-step">1 · INBOUND QUEUE</div>', unsafe_allow_html=True)
    queue_display = queue[[column for column in ("Manifest", "Vendor", "Package Count", "Received Count", "Estimated Arrival", "Source") if column in queue.columns]]
    st.dataframe(queue_display, width="stretch", hide_index=True, height=min(300, 48 + len(queue_display) * 36))
    labels = [f"{row.get('Manifest') or row.get('Transfer ID')} · {row.get('Vendor') or 'Unknown vendor'} · {int(row.get('Package Count') or 0)} package(s)" for _, row in queue.iterrows()]
    selected_label = st.selectbox("Inbound transfer", labels, key="recv_selected_transfer")
    selected_index = labels.index(selected_label)
    selected = queue.iloc[selected_index]
    source = str(selected.get("Source") or state.get("inventory_inbound_source") or "")
    manifest = str(selected.get("Manifest") or selected.get("Transfer ID") or "")

    packages: pd.DataFrame | None = None
    if source == "Sandbox":
        package_sets = state.get("inventory_inbound_sandbox_packages") or {}
        packages = package_sets.get(manifest)
    else:
        loaded_for = str(state.get("inventory_inbound_package_transfer_id") or "")
        if loaded_for == str(selected.get("Transfer ID") or ""):
            candidate = state.get("inventory_inbound_packages_df")
            packages = candidate if isinstance(candidate, pd.DataFrame) else None
        if st.button("Load transfer packages", type="primary", width="stretch", key="recv_load_packages"):
            if not credentials.configured:
                st.error("Metrc credentials are not configured for this user.")
            else:
                ok, message = _load_live_packages(state, credentials, selected)
                (st.success if ok else st.error)(message)
                if ok:
                    st.rerun()

    if packages is None or packages.empty:
        st.info("Load this transfer's package details to continue.")
        return

    catalog = _catalog_frame(state)
    if catalog.empty:
        st.warning("Buyer Dash does not have a product catalog to map this receipt against.")
        return
    current_inventory, _ = get_active_inventory_df()
    room_col = _pick(current_inventory, ("Room", "Location")) if isinstance(current_inventory, pd.DataFrame) else None
    rooms = sorted({str(value).strip() for value in current_inventory[room_col].dropna().tolist() if str(value).strip()}) if room_col else []
    room_options = list(dict.fromkeys(["Receiving", "Vault", "Sales Floor", "Quarantine", *rooms]))
    product_options = sorted({str(value).strip() for value in catalog["Product Name"].tolist() if str(value).strip()})

    editor_seed_key = f"inventory_receipt_editor_{source}_{manifest}"
    if editor_seed_key not in state:
        state[editor_seed_key] = prepare_receipt_editor(packages, catalog)

    st.markdown('<div class="recv-step">2 · MATCH PRODUCTS & RECEIVE DETAILS</div>', unsafe_allow_html=True)
    edited = st.data_editor(
        state[editor_seed_key],
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Mapped Product": st.column_config.SelectboxColumn("Mapped Product", options=product_options, required=True),
            "Room": st.column_config.SelectboxColumn("Room", options=room_options, required=True),
            "Unit Cost": st.column_config.NumberColumn("Unit Cost", min_value=0.0, format="$%.2f"),
            "Retail Price": st.column_config.NumberColumn("Retail Price", min_value=0.0, format="$%.2f"),
            "Quantity": st.column_config.NumberColumn("Received Qty", min_value=0.0),
        },
        disabled=["Incoming Item", "Package ID", "Unit", "Shipment State", "Lab Testing State", "Category", "Vendor", "SKU", "COA ID", "Expiration Date", "Mapped SKU", "Mapped Category"],
        key=f"recv_editor_widget_{source}_{manifest}",
    )
    state[editor_seed_key] = edited

    require_acceptance = source == "Metrc"
    issues = validate_receipt_editor(edited, require_traceability_acceptance=require_acceptance)
    st.markdown('<div class="recv-step">3 · REVIEW & POST</div>', unsafe_allow_html=True)
    metrics = st.columns(4)
    metrics[0].metric("Packages", len(edited))
    metrics[1].metric("Mapped", int(edited["Mapped Product"].fillna("").astype(str).str.strip().ne("").sum()))
    metrics[2].metric("Accepted", int(edited["Shipment State"].fillna("").astype(str).str.casefold().isin({"accepted", "received"}).sum()))
    metrics[3].metric("Lab passed", int(edited["Lab Testing State"].fillna("").astype(str).str.casefold().isin({"passed", "testpassed", "testingpassed"}).sum()))

    if issues:
        for issue in issues:
            st.warning(issue)
    confirm = st.checkbox("I verified the physical count, product matches, destination rooms, and receipt details.", key=f"recv_confirm_{source}_{manifest}")
    can_post = not issues and confirm
    if st.button("Post inventory", type="primary", width="stretch", disabled=not can_post, key=f"recv_post_{source}_{manifest}"):
        try:
            updated = apply_receipt_to_inventory(current_inventory, edited, manifest=manifest, source=source)
            durable_id = persist_received_inventory(state, updated, manifest=manifest, actor=_username(state) or "system")
        except (ValueError, RuntimeError, Exception) as exc:
            st.error(str(exc))
            return
        labels_frame = edited[["Mapped Product", "Package ID", "Room", "Quantity", "Unit"]].copy()
        labels_frame.insert(0, "Manifest", manifest)
        state["inventory_last_received_labels"] = labels_frame
        state["inventory_last_received_manifest"] = manifest
        state["inventory_last_receipt_durable_id"] = durable_id
        state.pop(editor_seed_key, None)
        st.success(f"Posted {len(edited)} package(s) to Inventory. The updated inventory source is durably versioned in Supabase.")
        st.rerun()

    labels_frame = state.get("inventory_last_received_labels")
    if isinstance(labels_frame, pd.DataFrame) and not labels_frame.empty:
        st.markdown('<div class="recv-step">4 · LABELS</div>', unsafe_allow_html=True)
        st.dataframe(labels_frame, width="stretch", hide_index=True)
        st.download_button(
            "Download label queue",
            data=labels_frame.to_csv(index=False).encode("utf-8"),
            file_name=f"labels_{state.get('inventory_last_received_manifest') or 'receipt'}.csv",
            mime="text/csv",
            width="stretch",
            key="recv_download_labels",
        )


def render_receive_inventory_dialog(state: MutableMapping[str, Any]) -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Receive inventory", width="large")
        def dialog() -> None:
            if st.button("Close", key="receive_inventory_close"):
                state["inventory_receive_open"] = False
                st.rerun()
            render_receive_inventory(state)
        dialog()
    else:
        with st.container(border=True):
            render_receive_inventory(state)
