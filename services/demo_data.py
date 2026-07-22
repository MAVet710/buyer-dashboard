"""Versioned, non-destructive demo bootstrap for every app workspace."""
from __future__ import annotations

import io
import os
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from services.demo_data_buyer import build_buyer_demo
from services.demo_data_operations import build_operations_demo

DEMO_DATA_VERSION = "full-app-demo-v1"
PRIVILEGED_DEMO_ROLES = {"dev", "admin"}


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
        self.name, self.type, self.size = name, mime_type, len(content)


def demo_enabled_for_state(state: MutableMapping[str, Any]) -> bool:
    role = str(state.get("auth_user_role") or "").casefold()
    all_users = os.environ.get("BUYER_DASHBOARD_DEMO_FOR_ALL_AUTHENTICATED", "").strip().casefold() in {"1", "true", "yes", "on"}
    authenticated = state.get("user_authenticated") or state.get("is_admin") or state.get("auth_user_id")
    return bool(role in PRIVILEGED_DEMO_ROLES or state.get("demo_mode_enabled") or (all_users and authenticated))


def _set(state: MutableMapping[str, Any], key: str, value: Any, force: bool) -> None:
    old = state.get(key)
    empty = old is None or (isinstance(old, pd.DataFrame) and old.empty) or (isinstance(old, str) and not old.strip()) or (isinstance(old, (list, tuple, set, dict)) and not old)
    if force or empty:
        state[key] = value.copy() if isinstance(value, pd.DataFrame) else value


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def build_demo_payload(today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now().date()
    buyer, operations = build_buyer_demo(today), build_operations_demo(today)
    uploads = {
        "buyer_inventory": ("demo_inventory.csv", _csv(buyer["inventory"]), "text/csv"),
        "buyer_sales": ("demo_product_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "buyer_extra_sales": ("demo_extra_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "buyer_quarantine": ("demo_quarantine.csv", _csv(buyer["quarantine"]), "text/csv"),
        "delivery_manifest": ("demo_delivery_manifest.csv", _csv(buyer["manifest"]), "text/csv"),
        "delivery_sales": ("demo_delivery_sales.csv", _csv(buyer["sales"]), "text/csv"),
        "compliance_sources": ("demo_compliance_sources.csv", _csv(buyer["compliance"]), "text/csv"),
        "extraction_inventory": ("demo_extraction_inventory.csv", _csv(operations["extraction_inventory"]), "text/csv"),
        "extraction_runs": ("demo_extraction_runs.csv", _csv(operations["extraction_runs"]), "text/csv"),
    }
    return {**buyer, **operations, "uploads": uploads}


def _seed_coman(state: MutableMapping[str, Any], actor: str) -> tuple[bool, str]:
    try:
        from modules.coman.demo_data import ensure_coman_demo_dataset
        result = ensure_coman_demo_dataset(state=state, actor=actor)
        return bool(result.get("seeded") or result.get("already_present")), ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def ensure_full_app_demo_session(state: MutableMapping[str, Any], *, actor: str = "demo",
        force: bool = False, today: date | None = None) -> DemoSeedResult:
    if not demo_enabled_for_state(state):
        return DemoSeedResult(False, DEMO_DATA_VERSION, ())
    if state.get("_full_app_demo_version") == DEMO_DATA_VERSION and not force:
        return DemoSeedResult(False, DEMO_DATA_VERSION,
            tuple(state.get("_full_app_demo_sections", ())), bool(state.get("_coman_demo_seeded")),
            str(state.get("_coman_demo_error") or ""))
    payload = build_demo_payload(today)
    state["demo_mode_enabled"] = True
    state["demo_upload_catalog"] = payload["uploads"]
    state["demo_data_banner"] = "Full-app demo data is active. Upload a real file to replace a demo source."
    frames = {"inv_raw_df":"inventory","sales_raw_df":"sales","extra_sales_df":"sales",
        "detail_cached_df":"detail","detail_product_cached_df":"detail_product",
        "active_inventory_df":"inventory","active_sales_df":"sales",
        "delivery_manifest_df":"manifest","delivery_sales_df":"sales",
        "delivery_raw_df":"manifest","daily_sales_raw_df":"sales",
        "compliance_sources_df":"compliance","ecc_inventory_log":"extraction_inventory",
        "ecc_run_log":"extraction_runs","ecc_client_jobs":"extraction_jobs","ecc_job_log":"extraction_jobs"}
    for state_key, payload_key in frames.items():
        _set(state, state_key, payload[payload_key], force)
    _set(state, "quarantined_items", set(payload["quarantine"]["Product"].tolist()), force)
    for key, value in payload["white_label"].items():
        _set(state, key, value, force)
    for cache, source in {"_cache_inv":"buyer_inventory","_cache_sales":"buyer_sales",
            "_cache_extra_sales":"buyer_extra_sales","_cache_quarantine":"buyer_quarantine"}.items():
        name, content, _ = payload["uploads"][source]
        _set(state, cache, {"name": name, "bytes": content}, force)
    for key, value in {"data_mode":"📁 Uploads","doh_threshold_cache":21,
            "purchasing_budget_monthly_usd":75000.0,"purchasing_budget_open_po_usd":18650.0,
            "purchasing_budget_spent_usd":42180.0}.items():
        _set(state, key, value, force)
    coman_seeded, coman_error = _seed_coman(state, actor)
    state["_coman_demo_seeded"], state["_coman_demo_error"] = coman_seeded, coman_error
    sections = ("Inventory Dashboard","Trends","Delivery Impact","Slow Movers","PO Builder",
        "Compliance Q&A","Buyer Intelligence","Purchasing Budget","Admin Tools",
        "White Label / Repack","Co-Man Production","Extraction Command Center")
    state["_full_app_demo_version"], state["_full_app_demo_sections"] = DEMO_DATA_VERSION, sections
    return DemoSeedResult(True, DEMO_DATA_VERSION, sections, coman_seeded, coman_error)


def _match_demo_upload(label: str, key: str) -> str | None:
    text = f"{label} {key}".casefold()
    if "quarantine" in text: return "buyer_quarantine"
    if "compliance" in text and ("source" in text or "qa" in text): return "compliance_sources"
    if "manifest" in text: return "delivery_manifest"
    if "extraction" in text and "inventory" in text: return "extraction_inventory"
    if "extraction" in text and any(term in text for term in ("run", "partner", "log")): return "extraction_runs"
    if "extra sales" in text or "sales detail" in text: return "buyer_extra_sales"
    if "product sales" in text: return "buyer_sales"
    if ("sales report" in text and "product" not in text) or ("delivery" in text and "sales" in text): return "delivery_sales"
    if "inventory" in text: return "buyer_inventory"
    return None


def install_demo_upload_support(streamlit_module: Any) -> None:
    st, original = streamlit_module, streamlit_module.file_uploader
    if getattr(original, "_full_app_demo_wrapper", False):
        return
    def make_wrapper(callable_):
        def wrapped(label, *args, **kwargs):
            uploaded = callable_(label, *args, **kwargs)
            if uploaded not in (None, []):
                return uploaded
            state = st.session_state
            if not demo_enabled_for_state(state):
                return uploaded
            if not isinstance(state.get("demo_upload_catalog"), dict):
                ensure_full_app_demo_session(state,
                    actor=str(state.get("admin_user") or state.get("user_user") or "demo"))
            source = _match_demo_upload(str(label), str(kwargs.get("key") or ""))
            spec = state.get("demo_upload_catalog", {}).get(source) if source else None
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
