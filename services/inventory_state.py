from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from core.session_keys import (
    ACTIVE_INVENTORY_DF,
    ACTIVE_INVENTORY_META,
    ACTIVE_SALES_DF,
    ACTIVE_SALES_META,
    BUYER_READY,
    INV_RAW,
    SALES_RAW,
)

_LEGACY_INVENTORY_KEYS = [
    "buyer_inventory_df",
    "normalized_inventory_df",
    "inventory_df",
    "uploaded_inventory_df",
    "current_inventory_df",
    "inventory_report_df",
    "raw_inventory_df",
]


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _base_meta(source_name: str, source_type: str, source_key: str, df: pd.DataFrame) -> dict[str, Any]:
    return {
        "source_name": source_name or "",
        "source_type": source_type or "upload",
        "source_key": source_key,
        "rows": int(len(df)) if isinstance(df, pd.DataFrame) else 0,
        "columns": list(df.columns) if isinstance(df, pd.DataFrame) else [],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "Loaded" if isinstance(df, pd.DataFrame) and not df.empty else "Missing",
    }


def set_active_inventory_df(df: pd.DataFrame, source_name: str = "", source_type: str = "upload") -> None:
    safe_df = df.copy() if isinstance(df, pd.DataFrame) else _empty_df()
    st.session_state[INV_RAW] = safe_df
    st.session_state[ACTIVE_INVENTORY_DF] = safe_df
    st.session_state[ACTIVE_INVENTORY_META] = _base_meta(source_name, source_type, ACTIVE_INVENTORY_DF, safe_df)


def get_active_inventory_df() -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates = [ACTIVE_INVENTORY_DF, INV_RAW, BUYER_READY, *_LEGACY_INVENTORY_KEYS]
    for key in candidates:
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            meta = st.session_state.get(ACTIVE_INVENTORY_META, {}) if key == ACTIVE_INVENTORY_DF else {}
            if not isinstance(meta, dict) or not meta:
                meta = _base_meta("", "session", key, df)
            else:
                meta = {**meta, "source_key": meta.get("source_key") or key, "rows": len(df), "columns": list(df.columns), "status": "Loaded"}
            if key != ACTIVE_INVENTORY_DF:
                st.session_state[ACTIVE_INVENTORY_DF] = df.copy()
                st.session_state[ACTIVE_INVENTORY_META] = meta
                st.session_state[INV_RAW] = df.copy()
            return df.copy(), meta
    missing_meta = st.session_state.get(ACTIVE_INVENTORY_META, {})
    if not isinstance(missing_meta, dict):
        missing_meta = {}
    missing_meta = {
        "source_name": missing_meta.get("source_name", ""),
        "source_type": missing_meta.get("source_type", ""),
        "source_key": missing_meta.get("source_key", ""),
        "rows": 0,
        "columns": [],
        "uploaded_at": missing_meta.get("uploaded_at", ""),
        "status": "Missing",
    }
    return _empty_df(), missing_meta


def has_active_inventory() -> bool:
    df, _ = get_active_inventory_df()
    return isinstance(df, pd.DataFrame) and not df.empty


def clear_active_inventory() -> None:
    st.session_state[ACTIVE_INVENTORY_DF] = _empty_df()
    st.session_state[INV_RAW] = _empty_df()
    st.session_state[BUYER_READY] = _empty_df()
    st.session_state[ACTIVE_INVENTORY_META] = _base_meta("", "", ACTIVE_INVENTORY_DF, _empty_df())


def set_active_sales_df(df: pd.DataFrame, source_name: str = "", source_type: str = "upload") -> None:
    safe_df = df.copy() if isinstance(df, pd.DataFrame) else _empty_df()
    st.session_state[SALES_RAW] = safe_df
    st.session_state[ACTIVE_SALES_DF] = safe_df
    st.session_state[ACTIVE_SALES_META] = _base_meta(source_name, source_type, ACTIVE_SALES_DF, safe_df)


def get_active_sales_df() -> tuple[pd.DataFrame, dict[str, Any]]:
    for key in [ACTIVE_SALES_DF, SALES_RAW]:
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            meta = st.session_state.get(ACTIVE_SALES_META, {}) if key == ACTIVE_SALES_DF else {}
            if not isinstance(meta, dict) or not meta:
                meta = _base_meta("", "session", key, df)
            else:
                meta = {**meta, "source_key": meta.get("source_key") or key, "rows": len(df), "columns": list(df.columns), "status": "Loaded"}
            if key != ACTIVE_SALES_DF:
                st.session_state[ACTIVE_SALES_DF] = df.copy()
                st.session_state[ACTIVE_SALES_META] = meta
                st.session_state[SALES_RAW] = df.copy()
            return df.copy(), meta
    return _empty_df(), {"source_name": "", "source_type": "", "source_key": "", "rows": 0, "columns": [], "uploaded_at": "", "status": "Missing"}


def clear_active_sales() -> None:
    st.session_state[ACTIVE_SALES_DF] = _empty_df()
    st.session_state[SALES_RAW] = _empty_df()
    st.session_state[ACTIVE_SALES_META] = _base_meta("", "", ACTIVE_SALES_DF, _empty_df())
