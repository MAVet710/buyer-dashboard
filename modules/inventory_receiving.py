"""Inbound inventory receiving for Inventory v2.

Receive Inventory stays inside the Inventory workspace as a right-side work
window. Users choose an inbound order, complete its Receive Details, optionally
pull read-only Metrc lab results, review the physical receipt, and then post a
new durable Inventory snapshot. State traceability acceptance remains external.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.data_hub_repository import DataHubRepository
from services.inventory_state import get_active_inventory_df, set_active_inventory_df
from services.metrc_client import get_default_metrc_integrator_key
from services.metrc_receiving import (
    fetch_all_delivery_packages,
    fetch_all_incoming_transfers,
    fetch_all_transfer_deliveries,
    fetch_metrc_lab_results,
)
from user_integrations_store import UserIntegrationsStore


LOCATION_SETTINGS_DATASET_KEY = "location_settings"
RECEIVE_MAPPINGS_DATASET_KEY = "inventory_receive_mappings"
DEFAULT_LOCATION_SETTINGS = {
    "auto_map_products_during_receive": False,
    "default_receiving_room": "Receiving",
}

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
    "Traceability Incoming Item",
    "Traceability Item ID",
    "Traceability Package Record ID",
    "Lab Testing State",
    "Lab Result Summary",
    "Inventory Unit",
)


@dataclass(frozen=True)
class TraceabilityCredentials:
    configured: bool
    state: str = ""
    user_api_key: str = ""
    integrator_api_key: str = ""
    license_number: str = ""
    message: str = ""


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _username(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_username")
        or state.get("auth_user_id")
        or ""
    ).strip()


def _scope(state: MutableMapping[str, Any]) -> tuple[str, str, str]:
    organization_id = str(state.get("active_organization_id") or "").strip()
    facility_id = str(state.get("active_facility_id") or "").strip()
    return organization_id, facility_id, f"{organization_id}|{facility_id}"


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
        message=(
            "Metrc inbound queue is ready."
            if configured
            else "Connect Metrc and a facility license to load live inbound transfers."
        ),
    )


def _repository() -> DataHubRepository:
    return DataHubRepository(create_coman_engine())


def _load_json_dataset(
    state: MutableMapping[str, Any],
    *,
    dataset_key: str,
    session_key: str,
    default: dict[str, Any],
) -> dict[str, Any]:
    organization_id, facility_id, scope = _scope(state)
    cached = state.get(session_key)
    if isinstance(cached, dict) and cached.get("scope") == scope and isinstance(cached.get("value"), dict):
        return dict(cached["value"])
    if not organization_id or not facility_id:
        return dict(default)
    try:
        source = next(
            (
                item
                for item in _repository().list_active_sources(organization_id, facility_id)
                if str(item.dataset_key) == dataset_key
            ),
            None,
        )
        value = json.loads(source.payload.decode("utf-8")) if source is not None else dict(default)
        if not isinstance(value, dict):
            value = dict(default)
    except Exception:
        value = dict(default)
    state[session_key] = {"scope": scope, "value": dict(value)}
    return dict(value)


def _publish_json_dataset(
    state: MutableMapping[str, Any],
    *,
    dataset_key: str,
    dataset_label: str,
    cache_key: str,
    session_key: str,
    filename: str,
    value: dict[str, Any],
) -> str:
    organization_id, facility_id, scope = _scope(state)
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before saving location settings.")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fingerprint = hashlib.sha256(payload).hexdigest()
    record = _repository().publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key=dataset_key,
        dataset_label=dataset_label,
        cache_key=cache_key,
        filename=filename,
        fingerprint=fingerprint,
        payload=payload,
        inspection={"rows": 1, "columns": len(value), "quality": "Ready", "matches": {}, "missing": []},
        content_type="application/json",
        imported_by_user_id=state.get("auth_user_id"),
        imported_by=_username(state) or "system",
    )
    state[session_key] = {"scope": scope, "value": dict(value)}
    return str(record.id)


def load_location_receive_settings(state: MutableMapping[str, Any]) -> dict[str, Any]:
    value = _load_json_dataset(
        state,
        dataset_key=LOCATION_SETTINGS_DATASET_KEY,
        session_key="_location_receive_settings_cache",
        default=DEFAULT_LOCATION_SETTINGS,
    )
    return {**DEFAULT_LOCATION_SETTINGS, **value}


def save_location_receive_settings(
    state: MutableMapping[str, Any], *, auto_map_products_during_receive: bool, default_receiving_room: str
) -> str:
    value = {
        "auto_map_products_during_receive": bool(auto_map_products_during_receive),
        "default_receiving_room": str(default_receiving_room or "Receiving").strip() or "Receiving",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return _publish_json_dataset(
        state,
        dataset_key=LOCATION_SETTINGS_DATASET_KEY,
        dataset_label="Location Settings",
        cache_key="_cache_location_settings",
        session_key="_location_receive_settings_cache",
        filename="location_settings.json",
        value=value,
    )


def load_receive_mapping_history(state: MutableMapping[str, Any]) -> dict[str, Any]:
    value = _load_json_dataset(
        state,
        dataset_key=RECEIVE_MAPPINGS_DATASET_KEY,
        session_key="_inventory_receive_mapping_cache",
        default={"mappings": {}},
    )
    mappings = value.get("mappings")
    return dict(mappings) if isinstance(mappings, dict) else {}


def _mapping_key(source: str, row: pd.Series | dict[str, Any]) -> str:
    getter = row.get
    traceability_item_id = str(getter("Traceability Item ID") or "").strip()
    if traceability_item_id and traceability_item_id != "0":
        identity = f"item:{traceability_item_id}"
    else:
        identity = "|".join(
            [
                f"name:{_norm(getter('Incoming Item'))}",
                f"category:{_norm(getter('Category'))}",
                f"vendor:{_norm(getter('Vendor'))}",
            ]
        )
    return f"{_norm(source)}|{identity}"


def persist_receive_mapping_history(
    state: MutableMapping[str, Any], editor: pd.DataFrame, *, source: str
) -> str:
    mappings = load_receive_mapping_history(state)
    now = datetime.now(timezone.utc).isoformat()
    for _, row in editor.iterrows():
        product = str(row.get("Mapped Product") or "").strip()
        if not product:
            continue
        mappings[_mapping_key(source, row)] = {
            "incoming_item": str(row.get("Incoming Item") or ""),
            "traceability_item_id": str(row.get("Traceability Item ID") or ""),
            "vendor": str(row.get("Vendor") or ""),
            "catalog_product": product,
            "catalog_sku": str(row.get("Mapped SKU") or ""),
            "catalog_category": str(row.get("Mapped Category") or ""),
            "updated_at": now,
        }
    return _publish_json_dataset(
        state,
        dataset_key=RECEIVE_MAPPINGS_DATASET_KEY,
        dataset_label="Inventory Receive Mappings",
        cache_key="_cache_receive_mappings",
        session_key="_inventory_receive_mapping_cache",
        filename="inventory_receive_mappings.json",
        value={"mappings": mappings, "updated_at": now},
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


def _selected_rows(event: Any) -> list[int]:
    try:
        return [int(value) for value in event.selection.rows]
    except Exception:
        pass
    try:
        return [int(value) for value in event.get("selection", {}).get("rows", [])]
    except Exception:
        return []


def _received_manifest_numbers(state: MutableMapping[str, Any]) -> set[str]:
    inventory, _ = get_active_inventory_df()
    if inventory.empty:
        return set()
    column = _pick(inventory, ("Traceability Manifest", "Manifest #", "Manifest Number"))
    if not column:
        return set()
    return {str(value).strip() for value in inventory[column].dropna().tolist() if str(value).strip()}


def build_sandbox_inbound_queue(state: MutableMapping[str, Any]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Adapt the DEV Sandbox manifest into a pending inbound training queue."""

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

    already_received = _received_manifest_numbers(state)
    queue_rows: list[dict[str, Any]] = []
    package_sets: dict[str, pd.DataFrame] = {}
    for manifest_number, group in manifest.groupby(manifest_col, dropna=False):
        source_manifest = str(manifest_number or "Sandbox inbound").strip() or "Sandbox inbound"
        queue_manifest = f"{source_manifest}-PENDING"
        if queue_manifest in already_received:
            continue
        vendor = str(group[vendor_col].iloc[0] if vendor_col else "Sandbox Vendor")
        package_count = int(group[package_col].nunique()) if package_col else int(len(group))
        queue_rows.append(
            {
                "Transfer ID": queue_manifest,
                "Manifest": queue_manifest,
                "Vendor": vendor,
                "Package Count": package_count,
                "Received Count": 0,
                "Estimated Arrival": "Ready to receive",
                "Source": "Sandbox",
            }
        )
        package_rows: list[dict[str, Any]] = []
        for position, (_, row) in enumerate(group.iterrows(), start=1):
            original_package = str(row.get(package_col) or "") if package_col else str(position)
            synthetic_tag = "SBX-IN-" + hashlib.sha256(
                f"{queue_manifest}|{original_package}|{position}".encode("utf-8")
            ).hexdigest()[:14].upper()
            category_col = _pick(group, ("Category",))
            sku_col = _pick(group, ("SKU",))
            coa_col = _pick(group, ("COA ID",))
            cost_col = _pick(group, ("Unit Cost", "Cost"))
            package_rows.append(
                {
                    "Incoming Item": str(row.get(product_col) or ""),
                    "Package ID": synthetic_tag,
                    "Traceability Package ID": "",
                    "Traceability Item ID": "",
                    "Quantity": float(pd.to_numeric(pd.Series([row.get(qty_col) if qty_col else 0]), errors="coerce").fillna(0.0).iloc[0]),
                    "Unit": "unit",
                    "Shipment State": "Accepted",
                    "Lab Testing State": "TestPassed",
                    "Category": str(row.get(category_col) or "") if category_col else "",
                    "Vendor": vendor,
                    "SKU": str(row.get(sku_col) or "") if sku_col else "",
                    "COA ID": str(row.get(coa_col) or "") if coa_col else "",
                    "Unit Cost": float(pd.to_numeric(pd.Series([row.get(cost_col) if cost_col else 0]), errors="coerce").fillna(0.0).iloc[0]),
                    "Retail Price": 0.0,
                    "Expiration Date": "",
                    "Strain": "",
                    "Brand": "",
                }
            )
        package_sets[queue_manifest] = pd.DataFrame(package_rows)
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
                "Traceability Package ID": str(item.get("PackageId") or ""),
                "Traceability Item ID": str(item.get("ItemId") or ""),
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
                "Expiration Date": str(item.get("ExpirationDate") or item.get("UseByDate") or ""),
                "Strain": str(item.get("ItemStrainName") or ""),
                "Brand": str(item.get("ItemBrandName") or ""),
            }
        )
    return pd.DataFrame(rows)


def _catalog_frame(state: MutableMapping[str, Any]) -> pd.DataFrame:
    catalog = _first_frame(
        state,
        "demo_catalog_df",
        "active_inventory_df",
        "inv_raw_df",
        "detail_product_cached_df",
    )
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
    auto_map_history: bool = False,
    mapping_history: dict[str, Any] | None = None,
    source: str = "Metrc",
) -> pd.DataFrame:
    """Prepare Receive Details, using only approved historical mappings when enabled."""

    if packages is None or packages.empty:
        return pd.DataFrame()
    catalog = catalog.copy() if isinstance(catalog, pd.DataFrame) else pd.DataFrame()
    catalog_by_name = {
        str(row["Product Name"]).strip(): row
        for _, row in catalog.iterrows()
        if str(row.get("Product Name") or "").strip()
    }
    history = mapping_history or {}
    rows = []
    for _, package in packages.iterrows():
        mapped_product = ""
        if auto_map_history:
            prior = history.get(_mapping_key(source, package), {})
            prior_name = str(prior.get("catalog_product") or "").strip() if isinstance(prior, dict) else ""
            if prior_name in catalog_by_name:
                mapped_product = prior_name
        match = catalog_by_name.get(mapped_product)
        rows.append(
            {
                **package.to_dict(),
                "Mapped Product": mapped_product,
                "Mapped SKU": str(match.get("SKU") or "") if match is not None else "",
                "Mapped Category": str(match.get("Category") or package.get("Category") or "") if match is not None else str(package.get("Category") or ""),
                "Room": str(default_room or "Receiving"),
                "Unit Cost": float(match.get("Unit Cost") or package.get("Unit Cost") or 0.0) if match is not None else float(package.get("Unit Cost") or 0.0),
                "Retail Price": float(match.get("Retail Price") or package.get("Retail Price") or 0.0) if match is not None else float(package.get("Retail Price") or 0.0),
                "Lab Results": "Not requested",
            }
        )
    return pd.DataFrame(rows)


def sync_catalog_fields(editor: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Keep SKU/category/cost defaults aligned when a user changes Catalog product."""

    if editor is None or editor.empty:
        return editor
    catalog_by_name = {
        str(row["Product Name"]).strip(): row
        for _, row in catalog.iterrows()
        if str(row.get("Product Name") or "").strip()
    }
    updated = editor.copy()
    for index, row in updated.iterrows():
        match = catalog_by_name.get(str(row.get("Mapped Product") or "").strip())
        if match is None:
            continue
        updated.at[index, "Mapped SKU"] = str(match.get("SKU") or "")
        updated.at[index, "Mapped Category"] = str(match.get("Category") or row.get("Category") or "")
        if float(row.get("Unit Cost") or 0.0) <= 0:
            updated.at[index, "Unit Cost"] = float(match.get("Unit Cost") or 0.0)
        if float(row.get("Retail Price") or 0.0) <= 0:
            updated.at[index, "Retail Price"] = float(match.get("Retail Price") or 0.0)
    return updated


def validate_receipt_editor(editor: pd.DataFrame, *, require_traceability_acceptance: bool) -> list[str]:
    issues: list[str] = []
    if editor is None or editor.empty:
        return ["No inbound packages are selected."]
    if editor["Mapped Product"].fillna("").astype(str).str.strip().eq("").any():
        issues.append("Every incoming package must have a Catalog product *.")
    if editor["Room"].fillna("").astype(str).str.strip().eq("").any():
        issues.append("Every incoming package needs a Room *.")
    if (pd.to_numeric(editor["Quantity"], errors="coerce").fillna(0.0) <= 0).any():
        issues.append("Every incoming package needs a Received qty * greater than zero.")
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


def _inventory_status_for_lab_state(value: Any) -> str:
    state = _norm(value).replace(" ", "")
    sellable_states = {
        "testpassed",
        "retestpassed",
        "passed",
        "notrequired",
        "processvalidated",
        "decontaminated",
        "randdcompleted",
    }
    return "Available" if state in sellable_states else "Hold"


def apply_receipt_to_inventory(
    current: pd.DataFrame, editor: pd.DataFrame, *, manifest: str, source: str
) -> pd.DataFrame:
    """Return a new inventory snapshot while rejecting duplicate package receipts."""

    current = current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    if current.empty:
        current = pd.DataFrame(columns=list(CANONICAL_INVENTORY_COLUMNS))
    package_col = _target_column(current, ("Package ID", "METRC Package ID", "package_id"), "Package ID")
    if package_col not in current.columns:
        current[package_col] = ""
    existing_packages = {
        str(value).strip().casefold()
        for value in current[package_col].dropna().tolist()
        if str(value).strip()
    }
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
        "incoming_item": _target_column(current, ("Traceability Incoming Item",), "Traceability Incoming Item"),
        "item_id": _target_column(current, ("Traceability Item ID",), "Traceability Item ID"),
        "package_record_id": _target_column(current, ("Traceability Package Record ID",), "Traceability Package Record ID"),
        "lab": _target_column(current, ("Lab Testing State",), "Lab Testing State"),
        "lab_summary": _target_column(current, ("Lab Result Summary",), "Lab Result Summary"),
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
        payload[mapping["status"]] = _inventory_status_for_lab_state(row.get("Lab Testing State"))
        payload[mapping["received"]] = now
        payload[mapping["expiration"]] = str(row.get("Expiration Date") or "")
        payload[mapping["coa"]] = str(row.get("COA ID") or "")
        payload[mapping["manifest"]] = str(manifest or "")
        payload[mapping["source"]] = str(source or "")
        payload[mapping["incoming_item"]] = str(row.get("Incoming Item") or "")
        payload[mapping["item_id"]] = str(row.get("Traceability Item ID") or "")
        payload[mapping["package_record_id"]] = str(row.get("Traceability Package ID") or "")
        payload[mapping["lab"]] = str(row.get("Lab Testing State") or "")
        payload[mapping["lab_summary"]] = str(row.get("Lab Results") or "Not requested")
        payload[mapping["unit"]] = str(row.get("Unit") or "unit")
        new_rows.append(payload)
    return pd.concat([current, pd.DataFrame(new_rows, columns=current.columns)], ignore_index=True)


def persist_received_inventory(
    state: MutableMapping[str, Any], updated: pd.DataFrame, *, manifest: str, actor: str
) -> str:
    """Publish the new Inventory snapshot through the existing durable Data Hub repository."""

    organization_id, facility_id, _ = _scope(state)
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before posting inventory.")
    payload = updated.to_csv(index=False).encode("utf-8")
    fingerprint = hashlib.sha256(payload).hexdigest()
    safe_manifest = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in str(manifest or "receipt")
    )
    filename = f"inventory_after_{safe_manifest or 'receipt'}.csv"
    record = _repository().publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key="inventory",
        dataset_label="Inventory",
        cache_key="_cache_inv",
        filename=filename,
        fingerprint=fingerprint,
        payload=payload,
        inspection={
            "rows": len(updated),
            "columns": len(updated.columns),
            "quality": "Ready",
            "matches": {},
            "missing": [],
        },
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


def _refresh_live_queue(
    state: MutableMapping[str, Any], credentials: TraceabilityCredentials
) -> tuple[bool, str]:
    result = fetch_all_incoming_transfers(
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
    state.pop("inventory_inbound_package_transfer_id", None)
    return True, f"Loaded {len(queue)} inbound transfer(s) from Metrc."


def _load_live_packages(
    credentials: TraceabilityCredentials, transfer: pd.Series | dict[str, Any]
) -> tuple[pd.DataFrame, str]:
    delivery_ids: list[str] = []
    direct_delivery = str(transfer.get("Delivery ID") or "").strip()
    if direct_delivery:
        delivery_ids.append(direct_delivery)
    if not delivery_ids:
        result = fetch_all_transfer_deliveries(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            transfer_id=str(transfer.get("Transfer ID") or ""),
        )
        if not result.get("ok"):
            return pd.DataFrame(), str(result.get("message") or "Metrc delivery details could not be loaded.")
        for delivery in result.get("deliveries") or []:
            delivery_id = str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip()
            if delivery_id:
                delivery_ids.append(delivery_id)
    package_rows: list[dict[str, Any]] = []
    for delivery_id in delivery_ids:
        result = fetch_all_delivery_packages(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            delivery_id=delivery_id,
        )
        if not result.get("ok"):
            return pd.DataFrame(), str(result.get("message") or "Metrc package details could not be loaded.")
        package_rows.extend(result.get("packages") or [])
    packages = normalize_metrc_packages(package_rows, vendor=str(transfer.get("Vendor") or ""))
    return packages, f"Loaded {len(packages)} package(s) for this inbound transfer."


def _sandbox_lab_results(packages: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, package in packages.iterrows():
        rows.append(
            {
                "Package ID": str(package.get("Package ID") or ""),
                "Traceability Package ID": str(package.get("Traceability Package ID") or ""),
                "Test Type": "Sandbox COA",
                "Result": "Passed",
                "Passed": True,
                "Overall Passed": True,
                "Lab": "DEV Sandbox Lab",
                "Performed": "Sandbox",
            }
        )
    return pd.DataFrame(rows)


def _live_lab_results(
    packages: pd.DataFrame, credentials: TraceabilityCredentials
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for _, package in packages.iterrows():
        trace_package_id = str(package.get("Traceability Package ID") or "").strip()
        if not trace_package_id:
            continue
        result = fetch_metrc_lab_results(
            state=credentials.state,
            user_api_key=credentials.user_api_key,
            integrator_api_key=credentials.integrator_api_key,
            license_number=credentials.license_number,
            package_id=trace_package_id,
        )
        if not result.get("ok"):
            warnings.append(
                f"{package.get('Package ID')}: {result.get('message') or 'Lab results unavailable.'}"
            )
            continue
        for lab in result.get("lab_results") or []:
            rows.append(
                {
                    "Package ID": str(package.get("Package ID") or ""),
                    "Traceability Package ID": trace_package_id,
                    "Test Type": str(lab.get("TestTypeName") or lab.get("LabTestTypeName") or ""),
                    "Result": lab.get("TestResultLevel") if lab.get("TestResultLevel") is not None else lab.get("Quantity"),
                    "Passed": lab.get("TestPassed"),
                    "Overall Passed": lab.get("OverallPassed"),
                    "Lab": str(lab.get("LabFacilityName") or ""),
                    "Performed": str(lab.get("TestPerformedDate") or ""),
                }
            )
    return pd.DataFrame(rows), warnings


def _attach_lab_summaries(editor: pd.DataFrame, lab_results: pd.DataFrame) -> pd.DataFrame:
    if editor is None or editor.empty:
        return editor
    updated = editor.copy()
    if lab_results is None or lab_results.empty:
        updated["Lab Results"] = "No results returned"
        return updated
    for index, row in updated.iterrows():
        package_id = str(row.get("Package ID") or "")
        matches = lab_results[lab_results["Package ID"].astype(str) == package_id]
        if matches.empty:
            updated.at[index, "Lab Results"] = "No results returned"
            continue
        passed_values = matches["Overall Passed"].dropna().tolist()
        if not passed_values:
            passed_values = matches["Passed"].dropna().tolist()
        if passed_values and all(bool(value) for value in passed_values):
            status = "Passed"
        elif passed_values and any(not bool(value) for value in passed_values):
            status = "Review"
        else:
            status = "Results loaded"
        updated.at[index, "Lab Results"] = f"{status} · {len(matches)} result(s)"
    return updated


def _receiving_css() -> None:
    st.markdown(
        """
        <style>
        .recv-kicker{color:#ff9a3c;font-size:.66rem;font-weight:820;letter-spacing:.14em;text-transform:uppercase}
        .recv-help{padding:.6rem .7rem;border:1px solid rgba(255,154,60,.17);border-radius:10px;background:rgba(255,154,60,.055);color:#bbb2aa!important;font-size:.76rem;margin:.35rem 0 .65rem}
        .recv-step{color:#aaa49e!important;font-size:.68rem;font-weight:760;letter-spacing:.08em;text-transform:uppercase;margin-top:.5rem}
        .recv-context{padding:.55rem .65rem;border:1px solid rgba(255,255,255,.08);border-radius:10px;background:#101010;margin:.35rem 0 .7rem;color:#b9b2ab!important;font-size:.75rem}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_queue(
    state: MutableMapping[str, Any],
    *,
    credentials: TraceabilityCredentials,
    is_sandbox: bool,
) -> None:
    top = st.columns([1.6, 1, 1])
    top[0].caption(
        "DEV Sandbox is using its pending demo manifest queue."
        if is_sandbox
        else credentials.message
    )
    if credentials.configured and top[1].button(
        "Refresh Metrc", width="stretch", key="recv_refresh_metrc"
    ):
        ok, message = _refresh_live_queue(state, credentials)
        (st.success if ok else st.error)(message)
        if ok:
            st.rerun()
    if is_sandbox and top[2].button(
        "Use Sandbox", width="stretch", key="recv_use_sandbox"
    ):
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
        st.info("No inbound orders are loaded. Refresh Metrc or use the Sandbox queue.")
        return

    st.markdown('<div class="recv-step">INBOUND QUEUE</div>', unsafe_allow_html=True)
    st.caption("Click an inbound order to open Receive Details.")
    queue_display_columns = [
        column
        for column in (
            "Manifest",
            "Vendor",
            "Package Count",
            "Received Count",
            "Estimated Arrival",
            "Source",
        )
        if column in queue.columns
    ]
    event = st.dataframe(
        queue[queue_display_columns],
        width="stretch",
        hide_index=True,
        height=min(430, 48 + len(queue) * 36),
        on_select="rerun",
        selection_mode="single-row",
        key="recv_inbound_queue_table",
    )
    positions = _selected_rows(event)
    if not positions:
        return
    selected = queue.iloc[positions[0]].to_dict()
    source = str(selected.get("Source") or state.get("inventory_inbound_source") or "")
    manifest = str(selected.get("Manifest") or selected.get("Transfer ID") or "")
    if source == "Sandbox":
        packages = (state.get("inventory_inbound_sandbox_packages") or {}).get(manifest)
        if not isinstance(packages, pd.DataFrame) or packages.empty:
            st.error("This Sandbox order does not contain package details.")
            return
    else:
        if not credentials.configured:
            st.error("Metrc credentials are not configured for this user.")
            return
        packages, message = _load_live_packages(credentials, selected)
        if packages.empty:
            st.error(message)
            return
    state["inventory_receive_selected_transfer"] = selected
    state["inventory_inbound_packages_df"] = packages.reset_index(drop=True)
    state["inventory_inbound_package_transfer_id"] = str(selected.get("Transfer ID") or "")
    state["inventory_receive_stage"] = "details"
    state.pop("inventory_receive_lab_results_df", None)
    st.rerun()


def _render_receive_details(
    state: MutableMapping[str, Any],
    *,
    credentials: TraceabilityCredentials,
    settings: dict[str, Any],
) -> None:
    selected = state.get("inventory_receive_selected_transfer")
    packages = state.get("inventory_inbound_packages_df")
    if not isinstance(selected, dict) or not isinstance(packages, pd.DataFrame) or packages.empty:
        state["inventory_receive_stage"] = "queue"
        st.rerun()

    source = str(selected.get("Source") or "")
    manifest = str(selected.get("Manifest") or selected.get("Transfer ID") or "")
    header = st.columns([1, 2.4])
    if header[0].button("← Inbound Queue", width="stretch", key="recv_back_queue"):
        state["inventory_receive_stage"] = "queue"
        state.pop("inventory_receive_selected_transfer", None)
        state.pop("inventory_inbound_packages_df", None)
        st.rerun()
    header[1].markdown("### Receive Details")
    st.markdown(
        f'<div class="recv-context"><strong>{manifest}</strong><br>{selected.get("Vendor") or "Unknown vendor"} · {len(packages)} package(s) · {source}</div>',
        unsafe_allow_html=True,
    )

    auto_map = bool(settings.get("auto_map_products_during_receive"))
    st.caption(
        f"Auto-map products during receive: {'On' if auto_map else 'Off'} · configured in Data & Settings → Location"
    )
    get_labs = st.toggle(
        "Get Metrc Lab Results",
        value=False,
        key=f"recv_get_labs_{source}_{manifest}",
        help="Optional. Reads package lab results from Metrc; it does not modify or release lab results.",
    )

    lab_results = state.get("inventory_receive_lab_results_df")
    if get_labs and not isinstance(lab_results, pd.DataFrame):
        if source == "Sandbox":
            lab_results = _sandbox_lab_results(packages)
            state["inventory_receive_lab_results_df"] = lab_results
        elif credentials.configured:
            with st.spinner("Getting Metrc lab results…"):
                lab_results, warnings = _live_lab_results(packages, credentials)
            state["inventory_receive_lab_results_df"] = lab_results
            if warnings:
                state["inventory_receive_lab_warnings"] = warnings
        else:
            st.warning("Metrc credentials are not configured, so lab results cannot be retrieved.")
    elif not get_labs:
        lab_results = None

    warnings = state.get("inventory_receive_lab_warnings") or []
    if get_labs and warnings:
        with st.expander("Lab result warnings"):
            for warning in warnings:
                st.caption(str(warning))

    catalog = _catalog_frame(state)
    if catalog.empty:
        st.warning("Buyer Dash does not have a product catalog to map this receipt against.")
        return
    current_inventory, _ = get_active_inventory_df()
    room_col = _pick(current_inventory, ("Room", "Location")) if isinstance(current_inventory, pd.DataFrame) else None
    existing_rooms = (
        sorted(
            {
                str(value).strip()
                for value in current_inventory[room_col].dropna().tolist()
                if str(value).strip()
            }
        )
        if room_col
        else []
    )
    default_room = str(settings.get("default_receiving_room") or "Receiving")
    room_options = list(
        dict.fromkeys([default_room, "Receiving", "Vault", "Sales Floor", "Quarantine", *existing_rooms])
    )
    product_options = sorted(
        {str(value).strip() for value in catalog["Product Name"].tolist() if str(value).strip()}
    )
    mapping_history = load_receive_mapping_history(state) if auto_map else {}

    editor_seed_key = f"inventory_receipt_editor_{source}_{manifest}"
    if editor_seed_key not in state:
        state[editor_seed_key] = prepare_receipt_editor(
            packages,
            catalog,
            default_room=default_room,
            auto_map_history=auto_map,
            mapping_history=mapping_history,
            source=source,
        )
    editor_seed = state[editor_seed_key]
    if get_labs and isinstance(lab_results, pd.DataFrame):
        editor_seed = _attach_lab_summaries(editor_seed, lab_results)
        state[editor_seed_key] = editor_seed

    st.markdown('<div class="recv-step">RECEIVE DETAILS</div>', unsafe_allow_html=True)
    st.caption("Fields marked with * are required. Auto-mapped catalog products can always be changed.")
    edited = st.data_editor(
        editor_seed,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        column_order=[
            "Incoming Item",
            "Mapped Product",
            "Package ID",
            "Quantity",
            "Unit",
            "Room",
            "Unit Cost",
            "Retail Price",
            "Shipment State",
            "Lab Testing State",
            "Lab Results",
        ],
        column_config={
            "Incoming Item": st.column_config.TextColumn("Incoming item"),
            "Mapped Product": st.column_config.SelectboxColumn(
                "Catalog product *", options=product_options, required=True
            ),
            "Package ID": st.column_config.TextColumn("Package ID"),
            "Quantity": st.column_config.NumberColumn("Received qty *", min_value=0.000001),
            "Unit": st.column_config.TextColumn("Unit"),
            "Room": st.column_config.SelectboxColumn("Room *", options=room_options, required=True),
            "Unit Cost": st.column_config.NumberColumn("Unit cost", min_value=0.0, format="$%.2f"),
            "Retail Price": st.column_config.NumberColumn("Retail price", min_value=0.0, format="$%.2f"),
            "Shipment State": st.column_config.TextColumn("Traceability state"),
            "Lab Testing State": st.column_config.TextColumn("Lab state"),
            "Lab Results": st.column_config.TextColumn("Lab results"),
        },
        disabled=[
            "Incoming Item",
            "Package ID",
            "Unit",
            "Shipment State",
            "Lab Testing State",
            "Lab Results",
        ],
        key=f"recv_editor_widget_{source}_{manifest}",
    )
    edited = sync_catalog_fields(edited, catalog)
    state[editor_seed_key] = edited

    if get_labs and isinstance(lab_results, pd.DataFrame) and not lab_results.empty:
        with st.expander(f"Metrc lab results · {len(lab_results)} record(s)"):
            st.dataframe(lab_results, width="stretch", hide_index=True)

    issues = validate_receipt_editor(
        edited,
        require_traceability_acceptance=source == "Metrc",
    )
    st.markdown('<div class="recv-step">REVIEW</div>', unsafe_allow_html=True)
    metrics = st.columns(4)
    metrics[0].metric("Packages", len(edited))
    metrics[1].metric(
        "Mapped",
        int(edited["Mapped Product"].fillna("").astype(str).str.strip().ne("").sum()),
    )
    metrics[2].metric(
        "Accepted",
        int(
            edited["Shipment State"]
            .fillna("")
            .astype(str)
            .str.casefold()
            .isin({"accepted", "received"})
            .sum()
        ),
    )
    metrics[3].metric(
        "On hold",
        int(
            edited["Lab Testing State"]
            .map(_inventory_status_for_lab_state)
            .eq("Hold")
            .sum()
        ),
    )
    for issue in issues:
        st.warning(issue)
    confirm = st.checkbox(
        "I verified the physical count, product matches, destination rooms, and receipt details.",
        key=f"recv_confirm_{source}_{manifest}",
    )
    if st.button(
        "Post inventory",
        type="primary",
        width="stretch",
        disabled=bool(issues) or not confirm,
        key=f"recv_post_{source}_{manifest}",
    ):
        try:
            updated = apply_receipt_to_inventory(
                current_inventory,
                edited,
                manifest=manifest,
                source=source,
            )
            durable_id = persist_received_inventory(
                state,
                updated,
                manifest=manifest,
                actor=_username(state) or "system",
            )
        except Exception as exc:
            st.error(str(exc))
            return
        try:
            persist_receive_mapping_history(state, edited, source=source)
        except Exception as exc:
            state["inventory_receive_mapping_warning"] = str(exc)
        labels_frame = edited[["Mapped Product", "Package ID", "Room", "Quantity", "Unit"]].copy()
        labels_frame.insert(0, "Manifest", manifest)
        state["inventory_last_received_labels"] = labels_frame
        state["inventory_last_received_manifest"] = manifest
        state["inventory_last_receipt_durable_id"] = durable_id
        state["inventory_receive_stage"] = "complete"
        state.pop(editor_seed_key, None)
        st.rerun()


def _render_complete(state: MutableMapping[str, Any]) -> None:
    manifest = str(state.get("inventory_last_received_manifest") or "receipt")
    labels_frame = state.get("inventory_last_received_labels")
    st.success(f"{manifest} posted to Inventory and durably versioned in Supabase.")
    mapping_warning = str(state.pop("inventory_receive_mapping_warning", "") or "")
    if mapping_warning:
        st.warning("Inventory posted, but Buyer Dash could not save the receive auto-map history.")
        st.caption(mapping_warning)
    st.markdown('<div class="recv-step">LABELS</div>', unsafe_allow_html=True)
    if isinstance(labels_frame, pd.DataFrame) and not labels_frame.empty:
        st.dataframe(labels_frame, width="stretch", hide_index=True)
        st.download_button(
            "Download label queue",
            data=labels_frame.to_csv(index=False).encode("utf-8"),
            file_name=f"labels_{manifest}.csv",
            mime="text/csv",
            width="stretch",
            key="recv_download_labels",
        )
    if st.button("Back to inbound queue", width="stretch", key="recv_complete_back"):
        state["inventory_receive_stage"] = "queue"
        state.pop("inventory_receive_selected_transfer", None)
        state.pop("inventory_inbound_packages_df", None)
        state.pop("inventory_inbound_queue_df", None)
        state.pop("inventory_receive_lab_results_df", None)
        state.pop("inventory_receive_lab_warnings", None)
        st.rerun()


def render_receive_inventory(state: MutableMapping[str, Any]) -> None:
    _receiving_css()
    credentials = resolve_traceability_credentials(state)
    is_sandbox = str(state.get("active_organization_name") or "").strip().casefold() == "dev sandbox"
    settings = load_location_receive_settings(state)
    stage = str(state.get("inventory_receive_stage") or "queue")
    if stage not in {"queue", "details", "complete"}:
        stage = "queue"
        state["inventory_receive_stage"] = stage

    st.markdown('<div class="recv-kicker">INBOUND INVENTORY</div>', unsafe_allow_html=True)
    st.markdown("## Receive inventory")
    st.markdown(
        '<div class="recv-help"><strong>Workflow:</strong> Inbound Queue → Receive Details → Review → Post Inventory → Labels. Live Metrc access in this window is read-only. State acceptance still happens in Metrc first.</div>',
        unsafe_allow_html=True,
    )

    if stage == "queue":
        _render_queue(state, credentials=credentials, is_sandbox=is_sandbox)
    elif stage == "details":
        _render_receive_details(state, credentials=credentials, settings=settings)
    else:
        _render_complete(state)


def render_receive_inventory_dialog(state: MutableMapping[str, Any]) -> None:
    """Open receiving as the same right-side work-window pattern as Product 360."""

    if hasattr(st, "dialog"):
        @st.dialog("Receive inventory", width="large")
        def dialog() -> None:
            if st.button("Close", key="receive_inventory_close"):
                state["inventory_receive_open"] = False
                state["inventory_receive_stage"] = "queue"
                st.rerun()
            render_receive_inventory(state)

        dialog()
    else:
        with st.container(border=True):
            render_receive_inventory(state)
