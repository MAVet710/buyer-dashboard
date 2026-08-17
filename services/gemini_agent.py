"""Read-only Gemini agent for Buyer Dashboard operational data.

The agent only receives sanitized, bounded views of DataFrames already loaded
into Streamlit session state. It cannot write to Buyer Dashboard, METRC,
Dutchie, or any external system.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping

import pandas as pd

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_TOOL_ROWS = 75
MAX_CELL_CHARS = 500

SENSITIVE_COLUMN_PATTERNS = (
    "password", "secret", "token", "api_key", "apikey", "authorization",
    "email", "phone", "address", "customer", "patient", "employee",
    "first_name", "last_name", "dob", "birth", "ssn",
)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _safe_scalar(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text[:MAX_CELL_CHARS]


def _safe_columns(df: pd.DataFrame) -> list[str]:
    out = []
    for col in df.columns:
        n = _norm(col)
        if any(_norm(pattern) in n for pattern in SENSITIVE_COLUMN_PATTERNS):
            continue
        out.append(str(col))
    return out


def _frame_records(df: pd.DataFrame, columns: list[str] | None = None, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    allowed = _safe_columns(df)
    if columns:
        requested = {_norm(c) for c in columns}
        allowed = [c for c in allowed if _norm(c) in requested]
    if not allowed:
        return []
    subset = df.loc[:, allowed].head(max(1, min(int(limit), MAX_TOOL_ROWS)))
    return [{str(k): _safe_scalar(v) for k, v in row.items()} for row in subset.to_dict(orient="records")]


def _find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lookup = {_norm(c): str(c) for c in df.columns}
    for alias in aliases:
        if _norm(alias) in lookup:
            return lookup[_norm(alias)]
    for alias in aliases:
        needle = _norm(alias)
        for normalized, original in lookup.items():
            if needle and (needle in normalized or normalized in needle):
                return original
    return None


@dataclass
class BuyerDataTools:
    datasets: Mapping[str, pd.DataFrame]

    def _dataset(self, name: str) -> pd.DataFrame:
        key = _norm(name)
        aliases = {
            "inventory": "inventory", "inv": "inventory",
            "sales": "sales", "productsales": "sales",
            "extrasales": "extra_sales", "extra": "extra_sales",
            "delivery": "delivery", "deliveries": "delivery",
        }
        resolved = aliases.get(key, name)
        df = self.datasets.get(resolved)
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"Dataset '{name}' is not loaded.")
        return df

    def list_datasets(self) -> dict[str, Any]:
        """List operational datasets currently loaded in Buyer Dashboard."""
        result: dict[str, Any] = {}
        for name, df in self.datasets.items():
            if isinstance(df, pd.DataFrame):
                result[name] = {"rows": len(df), "columns": _safe_columns(df)[:60]}
        return result

    def preview_dataset(self, dataset: str, limit: int = 20) -> dict[str, Any]:
        """Preview sanitized rows from a loaded operational dataset."""
        df = self._dataset(dataset)
        return {"dataset": dataset, "rows": _frame_records(df, limit=limit)}

    def search_dataset(self, dataset: str, query: str, limit: int = 30) -> dict[str, Any]:
        """Search all non-sensitive text fields in a dataset for a product, brand, category, vendor, or other term."""
        df = self._dataset(dataset)
        safe = _safe_columns(df)
        if not safe:
            return {"dataset": dataset, "matches": []}
        q = str(query or "").strip().lower()
        if not q:
            return self.preview_dataset(dataset, limit)
        mask = pd.Series(False, index=df.index)
        for col in safe:
            mask = mask | df[col].astype(str).str.lower().str.contains(re.escape(q), na=False)
        return {"dataset": dataset, "matches": _frame_records(df.loc[mask], limit=limit)}

    def summarize_numeric(self, dataset: str, column: str) -> dict[str, Any]:
        """Summarize a numeric column with count, total, average, min, max, and median."""
        df = self._dataset(dataset)
        col = _find_col(df, [column])
        if not col or col not in _safe_columns(df):
            raise ValueError(f"Column '{column}' is unavailable.")
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if values.empty:
            return {"dataset": dataset, "column": col, "count": 0}
        return {
            "dataset": dataset, "column": col, "count": int(values.count()),
            "total": float(values.sum()), "average": float(values.mean()),
            "median": float(values.median()), "min": float(values.min()), "max": float(values.max()),
        }

    def top_rows(self, dataset: str, sort_column: str, limit: int = 20, ascending: bool = False) -> dict[str, Any]:
        """Return the highest or lowest rows by a numeric field such as units, sales, cost, price, or inventory."""
        df = self._dataset(dataset).copy()
        col = _find_col(df, [sort_column])
        if not col or col not in _safe_columns(df):
            raise ValueError(f"Column '{sort_column}' is unavailable.")
        df["__sort"] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("__sort", ascending=bool(ascending), na_position="last").drop(columns=["__sort"])
        return {"dataset": dataset, "sort_column": col, "rows": _frame_records(df, limit=limit)}

    def inventory_reorder_candidates(self, days_cover: int = 14, limit: int = 30) -> dict[str, Any]:
        """Calculate read-only reorder candidates by matching inventory quantities to product sales velocity."""
        inv = self._dataset("inventory").copy()
        sales = self._dataset("sales").copy()
        inv_name = _find_col(inv, ["product name", "product", "item name", "item", "name", "sku name"])
        inv_qty = _find_col(inv, ["available", "on hand", "onhand", "quantity", "qty", "inventory available", "med total"])
        sales_name = _find_col(sales, ["product name", "product", "item name", "item", "name", "sku name", "description"])
        sales_qty = _find_col(sales, ["quantity sold", "qty sold", "units sold", "units", "total units"])
        if not all([inv_name, inv_qty, sales_name, sales_qty]):
            return {"error": "Could not identify required product and quantity columns.", "inventory_columns": _safe_columns(inv), "sales_columns": _safe_columns(sales)}

        inv["__name"] = inv[inv_name].astype(str).str.strip().str.lower()
        sales["__name"] = sales[sales_name].astype(str).str.strip().str.lower()
        inv["__qty"] = pd.to_numeric(inv[inv_qty], errors="coerce").fillna(0)
        sales["__sold"] = pd.to_numeric(sales[sales_qty], errors="coerce").fillna(0)
        inv_g = inv.groupby("__name", as_index=False).agg(product=(inv_name, "first"), on_hand=("__qty", "sum"))
        sales_g = sales.groupby("__name", as_index=False).agg(units_sold=("__sold", "sum"))
        merged = inv_g.merge(sales_g, on="__name", how="left").fillna({"units_sold": 0})

        # Sales reports may cover different periods, so this is a relative buyer signal,
        # not a claim about exact daily velocity. We use 30 days as a conservative default.
        merged["daily_velocity_est"] = merged["units_sold"] / 30.0
        merged["target_units"] = (merged["daily_velocity_est"] * max(1, int(days_cover))).round(0)
        merged["suggested_reorder"] = (merged["target_units"] - merged["on_hand"]).clip(lower=0).round(0)
        merged["days_cover_est"] = merged.apply(
            lambda r: round(r["on_hand"] / r["daily_velocity_est"], 1) if r["daily_velocity_est"] > 0 else None, axis=1
        )
        out = merged[merged["suggested_reorder"] > 0].sort_values(["suggested_reorder", "units_sold"], ascending=False)
        cols = ["product", "on_hand", "units_sold", "daily_velocity_est", "days_cover_est", "target_units", "suggested_reorder"]
        return {
            "method_note": "Uses loaded sales units with a 30-day normalization because source report period metadata is not guaranteed.",
            "target_days_cover": int(days_cover), "candidates": _frame_records(out[cols], limit=limit),
        }


class GeminiBuyerAgent:
    """Gemini tool-using agent with strictly read-only Buyer Dashboard tools."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = str(model or DEFAULT_GEMINI_MODEL).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and genai is not None and types is not None)

    def run(self, question: str, datasets: Mapping[str, pd.DataFrame], app_mode: str = "", section: str = "", history: list[dict[str, str]] | None = None) -> str:
        if not self.enabled:
            raise RuntimeError("Gemini is not configured. Add GEMINI_API_KEY to app secrets/environment.")
        tools = BuyerDataTools(datasets)
        functions = [tools.list_datasets, tools.preview_dataset, tools.search_dataset, tools.summarize_numeric, tools.top_rows, tools.inventory_reorder_candidates]
        client = genai.Client(api_key=self.api_key)
        history_text = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in (history or [])[-8:])
        prompt = f"""You are Buyer Agent, a cannabis retail purchasing and inventory analyst inside Buyer Dashboard.

Current app mode: {app_mode}
Current section: {section}
Recent conversation:\n{history_text or '(none)'}

User request: {question}

Rules:
- Use the provided read-only tools whenever the answer depends on loaded operational data.
- Never claim to submit, edit, receive, adjust, transfer, order, or modify inventory. You have no write tools.
- Do not invent values that are not returned by a tool.
- Clearly label estimates and assumptions.
- Give concise buyer-focused recommendations with the evidence that supports them.
- Never infer cannabis regulations from model memory. For compliance/legal questions, tell the user to use Buyer Dashboard's sourced compliance workflow.
- Do not request or expose secrets, customer information, patient information, or employee PII.
"""
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(tools=functions, temperature=0.2, max_output_tokens=1200),
        )
        text = str(getattr(response, "text", "") or "").strip()
        return text or "Buyer Agent did not return an answer."


def datasets_from_session(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    mapping = {
        "inventory": "inv_raw_df", "sales": "sales_raw_df", "extra_sales": "extra_sales_df",
        "delivery": "delivery_raw_df",
    }
    out: dict[str, pd.DataFrame] = {}
    for public_name, session_key in mapping.items():
        value = session_state.get(session_key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            out[public_name] = value
    return out
