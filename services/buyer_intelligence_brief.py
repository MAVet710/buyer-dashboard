"""Data-backed Buyer Intelligence brief generation.

Buyer Intelligence should remain useful even when an AI provider is unavailable.
This module builds deterministic store evidence first, then optionally asks the
read-only Gemini Buyer Agent to interpret those exact datasets. Generic advice
is rejected when it does not reference the supplied assortment/SKU evidence.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from modules.buyer_assortment import build_assortment_priorities
from services.agent_registry import PROFILES
from services.gemini_agent import GeminiWorkspaceAgent


def resolve_gemini_api_key() -> str:
    value = str(os.getenv("GEMINI_API_KEY") or "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get("GEMINI_API_KEY") or "").strip()
    except Exception:
        return ""


def buyer_intelligence_ai_enabled() -> bool:
    return GeminiWorkspaceAgent(
        api_key=resolve_gemini_api_key(), profile=PROFILES["buyer"]
    ).enabled


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _sku_risks(by_product: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    frame = _safe_frame(by_product)
    if frame.empty:
        return frame
    required = {"product_name", "units_sold", "on_hand_units", "days_of_cover"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame["units_sold"] = _numeric(frame["units_sold"]).fillna(0)
    frame["on_hand_units"] = _numeric(frame["on_hand_units"])
    frame["days_of_cover"] = _numeric(frame["days_of_cover"])
    if "risk_flag" in frame.columns:
        frame = frame[frame["risk_flag"].astype(str).eq("Reorder Risk")].copy()
    else:
        frame = frame[frame["days_of_cover"].le(14)].copy()
    if frame.empty:
        return frame
    return frame.sort_values(
        ["days_of_cover", "units_sold"], ascending=[True, False], na_position="last"
    ).head(max(1, int(limit)))


def _overstock_watch(by_product: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    frame = _safe_frame(by_product)
    if frame.empty:
        return frame
    required = {"product_name", "units_sold", "on_hand_units", "days_of_cover"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame["units_sold"] = _numeric(frame["units_sold"]).fillna(0)
    frame["on_hand_units"] = _numeric(frame["on_hand_units"])
    frame["days_of_cover"] = _numeric(frame["days_of_cover"])
    # A 60+ day cover is a watch signal, not an automatic markdown recommendation.
    watch = frame[
        frame["on_hand_units"].gt(0)
        & (frame["units_sold"].le(0) | frame["days_of_cover"].ge(60))
    ].copy()
    if watch.empty:
        return watch
    return watch.sort_values(
        ["units_sold", "days_of_cover", "on_hand_units"],
        ascending=[True, False, False],
        na_position="last",
    ).head(max(1, int(limit)))


def _format_number(value: Any, decimals: int = 0) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if pd.isna(numeric):
        return "n/a"
    if decimals:
        return f"{numeric:,.{decimals}f}"
    return f"{numeric:,.0f}"


def _data_confidence(by_product: pd.DataFrame, priorities: pd.DataFrame) -> str:
    if not isinstance(by_product, pd.DataFrame) or by_product.empty:
        return "Low"
    required = {"product_name", "units_sold", "on_hand_units", "days_of_cover"}
    if not required.issubset(by_product.columns):
        return "Low"
    coverage = pd.to_numeric(by_product["on_hand_units"], errors="coerce").notna().mean()
    if coverage >= 0.9 and not priorities.empty:
        return "High"
    if coverage >= 0.5:
        return "Medium"
    return "Low"


def build_store_evidence_markdown(
    summary: Mapping[str, Any],
    by_category: pd.DataFrame,
    by_product: pd.DataFrame,
    lookback_days: int,
) -> tuple[str, dict[str, pd.DataFrame]]:
    """Build an exact, useful buyer read before any model is called."""

    priorities = build_assortment_priorities(by_product)
    risks = _sku_risks(by_product)
    overstock = _overstock_watch(by_product)
    categories = _safe_frame(by_category).head(8)
    confidence = _data_confidence(by_product, priorities)

    sections: list[str] = []
    sections.append(
        "**Store snapshot**\n\n"
        f"{_format_number(summary.get('tracked_skus'))} tracked SKUs · "
        f"{_format_number(summary.get('total_units_sold'))} units sold in the selected "
        f"{int(lookback_days)}-day window · "
        f"{_format_number(summary.get('at_risk_skus'))} reorder-risk SKUs"
    )

    if not priorities.empty:
        lines = []
        for _, row in priorities.head(6).iterrows():
            lines.append(
                f"- **{row.get('Need', 'Assortment need')}**: target **{_format_number(row.get('Recommended units'))} units**; "
                f"{_format_number(row.get('Current on hand'), 1)} on hand, "
                f"{_format_number(row.get('Days of cover'), 1)} days cover, "
                f"{_format_number(row.get('Units sold'))} sold."
            )
        sections.append("**Buy first**\n\n" + "\n".join(lines))
    else:
        sections.append(
            "**Buy first**\n\nNo assortment-level replenishment gap can be supported by the loaded data."
        )

    if not risks.empty:
        lines = []
        for _, row in risks.head(6).iterrows():
            lines.append(
                f"- **{row.get('product_name', 'Unknown SKU')}**: "
                f"{_format_number(row.get('on_hand_units'), 1)} on hand, "
                f"{_format_number(row.get('units_sold'))} sold, "
                f"{_format_number(row.get('days_of_cover'), 1)} days cover."
            )
        sections.append("**SKU stockout risk**\n\n" + "\n".join(lines))
    else:
        sections.append("**SKU stockout risk**\n\nNo SKU is currently inside the 14-day reorder-risk threshold.")

    if not overstock.empty:
        lines = []
        for _, row in overstock.head(5).iterrows():
            lines.append(
                f"- **{row.get('product_name', 'Unknown SKU')}**: "
                f"{_format_number(row.get('on_hand_units'), 1)} on hand, "
                f"{_format_number(row.get('units_sold'))} sold, "
                f"{_format_number(row.get('days_of_cover'), 1)} days cover."
            )
        sections.append(
            "**Overstock / slow watch**\n\n" + "\n".join(lines)
            + "\n\nThese are review candidates, not automatic markdown instructions."
        )
    else:
        sections.append("**Overstock / slow watch**\n\nNo 60+ day-cover or zero-sales watch item was identified in the analyzed rows.")

    sections.append(
        f"**Data confidence: {confidence}**\n\n"
        "Confidence reflects whether product, sales, on-hand, and coverage evidence is present. "
        "Recommendations use the selected sales window and should be adjusted for known incoming POs or deliveries not represented in the loaded data."
    )

    datasets = {
        "purchase_priorities": priorities,
        "sku_risk": risks,
        "overstock_watch": overstock,
        "category_summary": categories,
    }
    datasets = {name: frame for name, frame in datasets.items() if not frame.empty}
    return "\n\n---\n\n".join(sections), datasets


def _evidence_anchors(datasets: Mapping[str, pd.DataFrame]) -> list[str]:
    anchors: list[str] = []
    priorities = datasets.get("purchase_priorities")
    if isinstance(priorities, pd.DataFrame) and "Need" in priorities.columns:
        anchors.extend(str(value).strip() for value in priorities["Need"].head(5) if str(value).strip())
    risks = datasets.get("sku_risk")
    if isinstance(risks, pd.DataFrame) and "product_name" in risks.columns:
        anchors.extend(str(value).strip() for value in risks["product_name"].head(5) if str(value).strip())
    return anchors


def _is_data_specific(answer: str, datasets: Mapping[str, pd.DataFrame]) -> bool:
    text = str(answer or "").casefold()
    anchors = _evidence_anchors(datasets)
    if not anchors:
        return bool(text.strip())
    return any(anchor.casefold() in text for anchor in anchors)


def generate_buyer_intelligence_brief(
    summary: Mapping[str, Any],
    by_category: pd.DataFrame,
    by_product: pd.DataFrame,
    lookback_days: int,
) -> str:
    """Return exact store evidence plus a Gemini interpretation when available."""

    evidence, datasets = build_store_evidence_markdown(
        summary, by_category, by_product, lookback_days
    )
    api_key = resolve_gemini_api_key()
    agent = GeminiWorkspaceAgent(api_key=api_key, profile=PROFILES["buyer"])
    if not agent.enabled or not datasets:
        return evidence

    instruction = f"""Build the Buyer Intelligence action brief for the current store using ONLY the read-only datasets provided.

You MUST inspect the available datasets with tools before answering. Prioritize `purchase_priorities`, then `sku_risk`, `overstock_watch`, and `category_summary` when present.

Selected sales window: {int(lookback_days)} days.

Output exactly these sections:
1. **Do this first**: 3 to 5 ranked actions. Every action must name an exact SKU or exact `Need` value from the data and include numeric evidence such as on-hand, units sold, days cover, or recommended units.
2. **Why it matters**: explain the strongest demand/coverage signals using exact store numbers.
3. **Watch, don't auto-act**: identify overstock/slow candidates and explain what should be checked before markdowns or cuts.
4. **Missing evidence**: state any limitation, especially incoming POs/deliveries or an unclear reporting period.

Hard rules:
- No generic retail strategy or filler.
- Do not say things like "close assortment gaps" unless you immediately name the exact gap and numbers.
- No external web sources, compliance section, legal discussion, or generic market references.
- No internal rule IDs, source tokens, citation markup, mailto links, or implementation metadata.
- Do not invent products, categories, quantities, sales, margins, or inventory values.
- If the data cannot support an action, say that clearly instead of guessing.
"""
    try:
        answer = agent.run(
            instruction,
            datasets,
            app_mode="🛒 Buyer Operations",
            section="🧠 Buyer Intelligence",
            profile=PROFILES["buyer"],
        )
    except Exception:
        return evidence

    if not _is_data_specific(answer, datasets):
        return evidence

    return evidence + "\n\n---\n\n**Gemini buyer interpretation**\n\n" + answer.strip()
