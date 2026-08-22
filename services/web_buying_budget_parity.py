"""Buyer Dash Purchasing Budget parity calculations.

Mirrors the purchasing-budget formulas in app.py while remaining UI independent.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().casefold())


def _detect(columns, aliases):
    mapping = {_norm(column): column for column in columns}
    for alias in aliases:
        key = _norm(alias)
        if key in mapping:
            return mapping[key]
    return None


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False), errors="coerce").fillna(0)


def calculate_sales_window(sales_df: pd.DataFrame, selected_days: int):
    if sales_df is None or sales_df.empty:
        return pd.DataFrame(), 0.0, None, None
    frame = sales_df.copy()
    frame.columns = frame.columns.astype(str).str.strip().str.lower()
    date_col = _detect(frame.columns, ["date", "sold date", "sales date", "order date", "created at"])
    sales_col = _detect(frame.columns, ["net sales", "total", "gross sales", "revenue", "retail sales", "sales"])
    if sales_col is None:
        return frame, 0.0, date_col, None
    frame[sales_col] = _numeric(frame[sales_col])
    if date_col is not None:
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        max_date = frame[date_col].max()
        if pd.notna(max_date):
            frame = frame[frame[date_col] >= max_date - pd.Timedelta(max(int(selected_days), 1) - 1, unit="D")]
    return frame, float(frame[sales_col].sum()), date_col, sales_col


def calculate_active_inventory_cost(inventory_df: pd.DataFrame, cogs_pct: float, include_dead: bool, include_quarantine: bool, include_accessories: bool):
    if inventory_df is None or inventory_df.empty:
        return pd.DataFrame(), 0.0
    frame = inventory_df.copy()
    frame.columns = frame.columns.astype(str).str.strip().str.lower()
    qty_col = _detect(frame.columns, ["on hand", "qty", "quantity", "onhandunits", "quantity on hand", "available", "available quantity", "inventory available", "med total", "med sellable"])
    cat_col = _detect(frame.columns, ["mastercategory", "subcategory", "category", "product category"])
    total_cost_col = _detect(frame.columns, ["total cost", "inventory cost", "cost total", "extended cost"])
    cost_col = _detect(frame.columns, ["unit_cost", "cost", "cost/unit", "unit cost", "wholesale price"])
    retail_col = _detect(frame.columns, ["retail price", "price", "retail", "med price"])
    dos_col = _detect(frame.columns, ["daysonhand", "dos", "days of supply"])
    name_col = _detect(frame.columns, ["itemname", "product name", "name"])
    if qty_col is None:
        return frame, 0.0
    frame[qty_col] = _numeric(frame[qty_col])
    if total_cost_col is not None:
        frame["_active_cost"] = _numeric(frame[total_cost_col])
    else:
        if cost_col is not None:
            unit_cost = _numeric(frame[cost_col])
        else:
            unit_cost = pd.Series(0.0, index=frame.index)
        if retail_col is not None:
            retail_est = _numeric(frame[retail_col]) * float(cogs_pct)
            unit_cost = unit_cost.where(unit_cost > 0, retail_est)
        frame["_active_cost"] = frame[qty_col] * unit_cost
    if not include_accessories and cat_col is not None:
        frame = frame[~frame[cat_col].astype(str).str.lower().str.contains("accessor", na=False)]
    if not include_dead:
        if dos_col is not None:
            frame = frame[pd.to_numeric(frame[dos_col], errors="coerce").fillna(0) != 999]
        if name_col is not None:
            frame = frame[~frame[name_col].astype(str).str.lower().str.contains("dead", na=False)]
    if not include_quarantine and name_col is not None:
        frame = frame[~frame[name_col].astype(str).str.lower().str.contains("quarantine|hold", na=False)]
    return frame, float(frame["_active_cost"].sum())


def build_budget(inventory_df: pd.DataFrame, sales_df: pd.DataFrame, *, selected_days: int = 30, target_dos: float = 45, cogs_pct: float = 0.50, safety_stock: float = 0.10, growth_adj: float = 0.0, include_dead: bool = False, include_quarantine: bool = False, include_accessories: bool = False, on_order_cost: float = 0.0):
    sales_window, sales_total, _date_col, sales_col = calculate_sales_window(sales_df, selected_days)
    active_inventory, active_inventory_cost = calculate_active_inventory_cost(inventory_df, cogs_pct, include_dead, include_quarantine, include_accessories)
    if sales_col is None:
        raise ValueError("Could not detect a retail sales column in your sales file.")
    avg_daily_sales = sales_total / max(int(selected_days), 1)
    avg_daily_cogs = avg_daily_sales * float(cogs_pct)
    target_inventory_cost = avg_daily_cogs * float(target_dos)
    target_inventory_cost *= 1 + float(safety_stock)
    target_inventory_cost *= 1 + float(growth_adj)
    recommended_budget = target_inventory_cost - active_inventory_cost - float(on_order_cost)
    available_to_buy = max(recommended_budget, 0.0)

    category_rows = []
    inv_cat = _detect(active_inventory.columns, ["mastercategory", "subcategory", "category"])
    sales_cat = _detect(sales_window.columns, ["mastercategory", "subcategory", "category"])
    if inv_cat and sales_cat:
        inv_group = active_inventory.groupby(active_inventory[inv_cat].astype(str))["_active_cost"].sum()
        local_sales = sales_window.copy()
        local_sales["_sales_value"] = _numeric(local_sales[sales_col])
        sales_group = local_sales.groupby(local_sales[sales_cat].astype(str))["_sales_value"].sum()
        categories = sorted(set(inv_group.index) | set(sales_group.index))
        for category in categories:
            cat_sales = float(sales_group.get(category, 0.0))
            cat_daily_cogs = (cat_sales / max(int(selected_days), 1)) * float(cogs_pct)
            cat_target = cat_daily_cogs * float(target_dos) * (1 + float(safety_stock)) * (1 + float(growth_adj))
            current = float(inv_group.get(category, 0.0))
            recommended = cat_target - current
            status = "Buy" if recommended > 0 else "Overstocked" if recommended < 0 else "Hold"
            notes = "Allocate purchasing budget" if status == "Buy" else "Reduce buys and sell-through" if status == "Overstocked" else "Near target"
            category_rows.append({
                "Category": category,
                "Sales Window Retail Sales": cat_sales,
                "Avg Daily Sales": cat_sales / max(int(selected_days), 1),
                "Avg Daily COGS": cat_daily_cogs,
                "Current Inventory at Cost": current,
                "Target Inventory at Cost": cat_target,
                "Recommended Budget": recommended,
                "Budget Status": status,
                "Notes": notes,
            })

    scenarios = []
    for name, dos, ss, gr in [("Conservative", 30, 0.05, 0.0), ("Balanced", float(target_dos), float(safety_stock), float(growth_adj)), ("Aggressive", 60, 0.15, 0.10)]:
        target = (avg_daily_cogs * dos) * (1 + ss) * (1 + gr)
        budget = target - active_inventory_cost - float(on_order_cost)
        scenarios.append({"Scenario": name, "Target Inventory": target, "Current Active Inventory": active_inventory_cost, "On Order": float(on_order_cost), "Recommended Budget": budget, "Status": "Available to Buy" if budget >= 0 else "Overbought"})
    return {
        "summary": {"recommended_budget": available_to_buy, "active_inventory_cost": active_inventory_cost, "target_inventory_cost": target_inventory_cost, "recommended_position": recommended_budget, "avg_daily_cogs": avg_daily_cogs, "on_order_cost": float(on_order_cost), "sales_window_total": sales_total},
        "categories": category_rows,
        "scenarios": scenarios,
    }
