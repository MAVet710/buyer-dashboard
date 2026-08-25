from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .sanitization import norm


def find_col(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lookup = {norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        if norm(alias) in lookup:
            return lookup[norm(alias)]
    return None


def numeric(frame: pd.DataFrame, aliases: tuple[str, ...], default: float = 0.0) -> pd.Series:
    column = find_col(frame, aliases)
    if column is None:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def inventory_health(inventory: pd.DataFrame, sales: pd.DataFrame, *, sales_days: int = 30) -> pd.DataFrame:
    if inventory.empty:
        return pd.DataFrame()
    inv_name = find_col(inventory, ("product name", "product", "item name", "item", "name", "sku name"))
    inv_sku = find_col(inventory, ("sku", "product sku", "item sku"))
    qty = find_col(inventory, ("available", "on hand", "onhand", "onhandunits", "on hand units", "quantity", "qty", "inventory available", "med total"))
    cost = find_col(inventory, ("cost", "unit cost", "wholesale cost"))
    price = find_col(inventory, ("retail price", "price", "med price"))
    received = find_col(inventory, ("received date", "received_at", "received"))
    expiration = find_col(inventory, ("expiration date", "expiration_at", "expiry"))
    if not inv_name or not qty:
        return pd.DataFrame()
    working = pd.DataFrame({
        "product": inventory[inv_name].fillna("").astype(str),
        "sku": inventory[inv_sku].fillna("").astype(str) if inv_sku else "",
        "on_hand": pd.to_numeric(inventory[qty], errors="coerce").fillna(0.0),
        "unit_cost": pd.to_numeric(inventory[cost], errors="coerce").fillna(0.0) if cost else 0.0,
        "retail_price": pd.to_numeric(inventory[price], errors="coerce").fillna(0.0) if price else 0.0,
    })
    working["__key"] = working["sku"].str.strip().str.casefold()
    missing_key = working["__key"].eq("")
    working.loc[missing_key, "__key"] = working.loc[missing_key, "product"].str.strip().str.casefold()
    if received:
        working["received_date"] = pd.to_datetime(inventory[received], errors="coerce", utc=True)
    if expiration:
        working["expiration_date"] = pd.to_datetime(inventory[expiration], errors="coerce", utc=True)
    agg: dict[str, Any] = {"product": "first", "sku": "first", "on_hand": "sum", "unit_cost": "mean", "retail_price": "mean"}
    if "received_date" in working:
        agg["received_date"] = "min"
    if "expiration_date" in working:
        agg["expiration_date"] = "min"
    output = working.groupby("__key", dropna=False).agg(agg).reset_index()

    velocity = pd.DataFrame(columns=["__key", "units_sold"])
    if sales is not None and not sales.empty:
        sales_name = find_col(sales, ("product name", "product", "item name", "item", "name", "description"))
        sales_sku = find_col(sales, ("sku", "product sku", "item sku"))
        sold = find_col(sales, ("quantity sold", "qty sold", "units sold", "unitssold", "units", "total units", "quantity"))
        if sales_name and sold:
            velocity = pd.DataFrame({
                "__key": sales[sales_sku].fillna("").astype(str).str.strip().str.casefold() if sales_sku else "",
                "__name": sales[sales_name].fillna("").astype(str).str.strip().str.casefold(),
                "units_sold": pd.to_numeric(sales[sold], errors="coerce").fillna(0.0),
            })
            blank = velocity["__key"].eq("")
            velocity.loc[blank, "__key"] = velocity.loc[blank, "__name"]
            velocity = velocity.groupby("__key", as_index=False)["units_sold"].sum()
    output = output.merge(velocity, on="__key", how="left").fillna({"units_sold": 0.0})
    days = max(1, int(sales_days))
    output["daily_velocity"] = output["units_sold"] / days
    output["days_of_supply"] = np.where(output["daily_velocity"] > 0, output["on_hand"] / output["daily_velocity"], np.nan)
    output["weeks_of_supply"] = output["days_of_supply"] / 7.0
    output["inventory_value"] = output["on_hand"] * output["unit_cost"]
    output["unit_margin"] = output["retail_price"] - output["unit_cost"]
    output["gross_margin_pct"] = np.where(output["retail_price"] > 0, output["unit_margin"] / output["retail_price"] * 100.0, np.nan)
    output["sell_through_pct"] = np.where(output["on_hand"] + output["units_sold"] > 0, output["units_sold"] / (output["on_hand"] + output["units_sold"]) * 100.0, 0.0)
    output["stockout_risk"] = np.select(
        [output["on_hand"] <= 0, output["days_of_supply"] <= 7, output["days_of_supply"] <= 14],
        ["critical", "high", "medium"],
        default="low",
    )
    output["overstock"] = output["days_of_supply"].fillna(9999).gt(60) & output["on_hand"].gt(0)
    output["slow_mover"] = output["daily_velocity"].le(0.1) & output["on_hand"].gt(0)
    now = pd.Timestamp.now(tz="UTC")
    if "received_date" in output:
        output["age_days"] = (now - output["received_date"]).dt.days
    if "expiration_date" in output:
        output["days_to_expiration"] = (output["expiration_date"] - now).dt.days
    return output.drop(columns=["__key"])


def reorder_candidates(inventory: pd.DataFrame, sales: pd.DataFrame, *, target_days: int = 21, lead_time_days: int = 0, open_po: pd.DataFrame | None = None) -> pd.DataFrame:
    health = inventory_health(inventory, sales)
    if health.empty:
        return health
    target = max(1, int(target_days)) + max(0, int(lead_time_days))
    health["target_units"] = np.ceil(health["daily_velocity"] * target)
    health["open_po_quantity"] = 0.0
    if open_po is not None and not open_po.empty:
        name = find_col(open_po, ("product", "product name", "item", "description"))
        sku = find_col(open_po, ("sku", "sku_snapshot", "product sku"))
        qty = find_col(open_po, ("outstanding_quantity", "outstanding quantity", "open quantity", "remaining quantity", "quantity"))
        if name and qty:
            po = pd.DataFrame({
                "key": open_po[sku].fillna("").astype(str).str.strip().str.casefold() if sku else "",
                "name": open_po[name].fillna("").astype(str).str.strip().str.casefold(),
                "qty": pd.to_numeric(open_po[qty], errors="coerce").fillna(0.0),
            })
            blank = po["key"].eq("")
            po.loc[blank, "key"] = po.loc[blank, "name"]
            sums = po.groupby("key")["qty"].sum().to_dict()
            keys = health["sku"].fillna("").astype(str).str.strip().str.casefold()
            names = health["product"].fillna("").astype(str).str.strip().str.casefold()
            health["open_po_quantity"] = [float(sums.get(key or name, 0.0)) for key, name in zip(keys, names)]
    health["recommended_reorder"] = (health["target_units"] - health["on_hand"] - health["open_po_quantity"]).clip(lower=0.0)
    return health.loc[health["recommended_reorder"] > 0].sort_values(["days_of_supply", "recommended_reorder"], ascending=[True, False], na_position="last")


def audit_metrics(lines: pd.DataFrame) -> pd.DataFrame:
    if lines.empty:
        return pd.DataFrame()
    expected = numeric(lines, ("expected_quantity", "expected count", "expected", "system quantity"))
    actual = numeric(lines, ("counted_quantity", "actual count", "actual", "counted"))
    unit_cost = numeric(lines, ("unit_cost", "cost", "unit cost"))
    output = lines.copy()
    output["expected_count"] = expected
    output["actual_count"] = actual
    output["variance_units"] = actual - expected
    output["absolute_variance"] = output["variance_units"].abs()
    output["variance_pct"] = np.where(expected.abs() > 0, output["variance_units"] / expected.abs() * 100.0, np.where(actual != 0, 100.0, 0.0))
    output["variance_value"] = output["variance_units"] * unit_cost
    output["recount_priority"] = np.select(
        [output["absolute_variance"] >= 10, output["variance_pct"].abs() >= 10, output["variance_value"].abs() >= 100],
        ["critical", "high", "high"],
        default="normal",
    )
    return output


def production_attainment(orders: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame()
    order_id = find_col(orders, ("id", "production_order_id", "order_id"))
    planned = find_col(orders, ("requested_units", "planned_quantity", "target_quantity", "quantity", "planned"))
    if not order_id or not planned:
        return pd.DataFrame()
    output = pd.DataFrame({
        "production_order_id": orders[order_id].astype(str),
        "planned_quantity": pd.to_numeric(orders[planned], errors="coerce").fillna(0.0),
    })
    for target, aliases in {
        "order_number": ("order_number",), "status": ("status",), "product_name": ("product_name", "product"), "due_at": ("due_at", "due_date"),
    }.items():
        column = find_col(orders, aliases)
        if column:
            output[target] = orders[column]
    if actuals is not None and not actuals.empty:
        actual_order = find_col(actuals, ("production_order_id", "order_id"))
        actual_qty = find_col(actuals, ("actual_units", "quantity", "actual_quantity", "good_units", "output_quantity"))
        if actual_order and actual_qty:
            done = pd.DataFrame({"production_order_id": actuals[actual_order].astype(str), "actual_quantity": pd.to_numeric(actuals[actual_qty], errors="coerce").fillna(0.0)}).groupby("production_order_id", as_index=False)["actual_quantity"].sum()
            output = output.merge(done, on="production_order_id", how="left")
    if "actual_quantity" not in output:
        output["actual_quantity"] = 0.0
    output["actual_quantity"] = pd.to_numeric(output["actual_quantity"], errors="coerce").fillna(0.0)
    output["attainment_pct"] = np.where(output["planned_quantity"] > 0, output["actual_quantity"] / output["planned_quantity"] * 100.0, np.nan)
    output["remaining_quantity"] = (output["planned_quantity"] - output["actual_quantity"]).clip(lower=0.0)
    return output


def purchase_order_metrics(orders: pd.DataFrame, lines: pd.DataFrame, receipts: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame()
    order_id = find_col(orders, ("id", "commercial_order_id", "order_id"))
    if not order_id:
        return pd.DataFrame()
    order_type = find_col(orders, ("order_type",))
    working_orders = orders.copy()
    if order_type:
        working_orders = working_orders.loc[working_orders[order_type].astype(str).str.casefold().eq("purchase")].copy()
    if working_orders.empty:
        return pd.DataFrame()
    output = pd.DataFrame({"order_id": working_orders[order_id].astype(str)})
    for target, aliases in {
        "order_number": ("order_number",), "partner_id": ("partner_id",), "status": ("status",), "order_date": ("order_date",), "due_at": ("due_at", "due_date"),
    }.items():
        column = find_col(working_orders, aliases)
        if column:
            output[target] = working_orders[column].values

    line_order = find_col(lines, ("commercial_order_id", "order_id")) if lines is not None and not lines.empty else None
    line_qty = find_col(lines, ("quantity", "ordered_quantity")) if line_order else None
    line_fulfilled = find_col(lines, ("fulfilled_quantity", "received_quantity")) if line_order else None
    line_price = find_col(lines, ("unit_price", "unit_price_usd", "cost")) if line_order else None
    aggregates: dict[str, dict[str, float]] = {}
    if line_order and line_qty:
        for _, row in lines.iterrows():
            key = str(row.get(line_order) or "")
            item = aggregates.setdefault(key, {"ordered_quantity": 0.0, "received_quantity": 0.0, "ordered_value": 0.0, "received_value": 0.0})
            ordered = float(pd.to_numeric(pd.Series([row.get(line_qty)]), errors="coerce").fillna(0.0).iloc[0])
            received = float(pd.to_numeric(pd.Series([row.get(line_fulfilled)]), errors="coerce").fillna(0.0).iloc[0]) if line_fulfilled else 0.0
            price = float(pd.to_numeric(pd.Series([row.get(line_price)]), errors="coerce").fillna(0.0).iloc[0]) if line_price else 0.0
            item["ordered_quantity"] += ordered
            item["received_quantity"] += received
            item["ordered_value"] += ordered * price
            item["received_value"] += received * price
    for column in ("ordered_quantity", "received_quantity", "ordered_value", "received_value"):
        output[column] = output["order_id"].map({key: value[column] for key, value in aggregates.items()}).fillna(0.0)
    output["outstanding_quantity"] = (output["ordered_quantity"] - output["received_quantity"]).clip(lower=0.0)
    output["outstanding_value"] = (output["ordered_value"] - output["received_value"]).clip(lower=0.0)
    output["fill_rate_pct"] = np.where(output["ordered_quantity"] > 0, output["received_quantity"] / output["ordered_quantity"] * 100.0, 100.0)

    receipt_order = find_col(receipts, ("commercial_order_id", "order_id")) if receipts is not None and not receipts.empty else None
    receipt_time = find_col(receipts, ("occurred_at", "received_at", "date")) if receipt_order else None
    if receipt_order and receipt_time:
        receipt_frame = pd.DataFrame({"order_id": receipts[receipt_order].astype(str), "received_at": pd.to_datetime(receipts[receipt_time], errors="coerce", utc=True)})
        latest = receipt_frame.groupby("order_id")["received_at"].max().to_dict()
        output["latest_receipt_at"] = output["order_id"].map(latest)
    if "due_at" in output:
        due = pd.to_datetime(output["due_at"], errors="coerce", utc=True)
        now = pd.Timestamp.now(tz="UTC")
        output["days_until_due"] = (due - now).dt.days
        latest_receipt = pd.to_datetime(output.get("latest_receipt_at"), errors="coerce", utc=True) if "latest_receipt_at" in output else pd.Series(pd.NaT, index=output.index, dtype="datetime64[ns, UTC]")
        completed = output["outstanding_quantity"] <= 1e-9
        output["on_time"] = np.where(completed & latest_receipt.notna() & due.notna(), latest_receipt <= due, np.nan)
        output["delivery_risk"] = np.select(
            [(output["outstanding_quantity"] > 0) & (output["days_until_due"] < 0), (output["outstanding_quantity"] > 0) & (output["days_until_due"] <= 2)],
            ["critical", "high"],
            default="normal",
        )
    return output


def vendor_performance(orders: pd.DataFrame, lines: pd.DataFrame, receipts: pd.DataFrame, partners: pd.DataFrame) -> pd.DataFrame:
    metrics = purchase_order_metrics(orders, lines, receipts)
    if metrics.empty or "partner_id" not in metrics:
        return pd.DataFrame()
    grouped = metrics.groupby("partner_id", dropna=False).agg(
        purchase_orders=("order_id", "count"),
        ordered_quantity=("ordered_quantity", "sum"),
        received_quantity=("received_quantity", "sum"),
        outstanding_quantity=("outstanding_quantity", "sum"),
        ordered_value=("ordered_value", "sum"),
        outstanding_value=("outstanding_value", "sum"),
    ).reset_index()
    grouped["fill_rate_pct"] = np.where(grouped["ordered_quantity"] > 0, grouped["received_quantity"] / grouped["ordered_quantity"] * 100.0, 100.0)
    if "on_time" in metrics:
        completed = metrics.dropna(subset=["on_time"])
        if not completed.empty:
            rates = completed.groupby("partner_id")["on_time"].mean().mul(100.0).to_dict()
            grouped["on_time_delivery_pct"] = grouped["partner_id"].map(rates)
    if partners is not None and not partners.empty:
        partner_id = find_col(partners, ("id", "partner_id"))
        name = find_col(partners, ("name", "partner_name", "vendor"))
        if partner_id and name:
            names = dict(zip(partners[partner_id].astype(str), partners[name].astype(str)))
            grouped["vendor"] = grouped["partner_id"].astype(str).map(names).fillna("")
    return grouped.sort_values(["outstanding_value", "fill_rate_pct"], ascending=[False, True])


def production_capacity_risks(orders: pd.DataFrame, machines: pd.DataFrame, crew: pd.DataFrame) -> dict[str, Any]:
    if orders.empty:
        return {"rows": [], "missing_data": []}
    status = find_col(orders, ("status",))
    requested = find_col(orders, ("requested_units", "planned_quantity", "quantity"))
    if not requested:
        return {"rows": [], "missing_data": ["Production order requested quantity"]}
    open_orders = orders.copy()
    if status:
        open_orders = open_orders.loc[~open_orders[status].astype(str).str.casefold().isin({"complete", "cancelled"})]
    demand = float(pd.to_numeric(open_orders[requested], errors="coerce").fillna(0.0).sum())
    rate_col = find_col(machines, ("effective_rate", "rate")) if machines is not None and not machines.empty else None
    total_rate = float(pd.to_numeric(machines[rate_col], errors="coerce").fillna(0.0).sum()) if rate_col else 0.0
    if total_rate <= 0:
        return {"rows": [{"open_requested_units": demand, "aggregate_machine_rate_units_per_hour": 0.0, "capacity_hours_required": None, "capacity_risk": "unknown"}], "missing_data": ["Active machine effective-rate data"]}
    hours = demand / total_rate
    crew_hours = None
    if crew is not None and not crew.empty:
        people = find_col(crew, ("available_people", "people"))
        shift = find_col(crew, ("shift_hours", "hours"))
        if people and shift:
            crew_hours = float((pd.to_numeric(crew[people], errors="coerce").fillna(0.0) * pd.to_numeric(crew[shift], errors="coerce").fillna(0.0)).sum())
    return {"rows": [{"open_requested_units": demand, "aggregate_machine_rate_units_per_hour": total_rate, "capacity_hours_required": round(hours, 2), "available_person_hours": round(crew_hours, 2) if crew_hours is not None else None, "capacity_risk": "review" if demand > 0 else "normal"}], "missing_data": ([] if crew_hours is not None else ["Crew availability for labor-capacity comparison"]), "limitation": "Aggregate capacity only; production orders are not durably routed to individual machines in the current schema."}


def commercial_fulfillment(orders: pd.DataFrame, lines: pd.DataFrame, allocations: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame()
    order_id = find_col(orders, ("id", "order_id", "commercial_order_id"))
    if not order_id:
        return pd.DataFrame()
    output = pd.DataFrame({"order_id": orders[order_id].astype(str)})
    for target, aliases in {
        "status": ("status",), "order_number": ("order_number", "order number"),
        "due_date": ("due_at", "due_date", "due date", "requested_delivery_date"), "partner_id": ("partner_id", "partner"),
    }.items():
        column = find_col(orders, aliases)
        if column:
            output[target] = orders[column]
    required: dict[str, float] = {}
    allocated: dict[str, float] = {}
    if lines is not None and not lines.empty:
        line_order = find_col(lines, ("commercial_order_id", "order_id"))
        quantity = find_col(lines, ("quantity", "required_quantity"))
        if line_order and quantity:
            required = pd.DataFrame({"order": lines[line_order].astype(str), "qty": pd.to_numeric(lines[quantity], errors="coerce").fillna(0.0)}).groupby("order")["qty"].sum().to_dict()
    if allocations is not None and not allocations.empty:
        alloc_order = find_col(allocations, ("commercial_order_id", "order_id"))
        quantity = find_col(allocations, ("quantity", "allocated_quantity"))
        if alloc_order and quantity:
            allocated = pd.DataFrame({"order": allocations[alloc_order].astype(str), "qty": pd.to_numeric(allocations[quantity], errors="coerce").fillna(0.0)}).groupby("order")["qty"].sum().to_dict()
    output["required_quantity"] = output["order_id"].map(required).fillna(0.0)
    output["allocated_quantity"] = output["order_id"].map(allocated).fillna(0.0)
    output["shortage_quantity"] = (output["required_quantity"] - output["allocated_quantity"]).clip(lower=0.0)
    output["fill_rate_pct"] = np.where(output["required_quantity"] > 0, output["allocated_quantity"] / output["required_quantity"] * 100.0, 100.0)
    if "due_date" in output:
        due = pd.to_datetime(output["due_date"], errors="coerce", utc=True)
        output["days_until_due"] = (due - pd.Timestamp.now(tz="UTC")).dt.days
        output["due_date_risk"] = np.select([(output["days_until_due"] < 0) & (output["shortage_quantity"] > 0), (output["days_until_due"] <= 3) & (output["shortage_quantity"] > 0)], ["critical", "high"], default="normal")
    return output


def cultivation_metrics(plants: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if plants.empty:
        return {"summary": pd.DataFrame(), "harvest_forecast": pd.DataFrame(), "exceptions": pd.DataFrame()}
    phase = find_col(plants, ("phase",))
    room = find_col(plants, ("room_code", "room"))
    strain = find_col(plants, ("strain_name", "strain"))
    planted = find_col(plants, ("planted_at", "planted date"))
    harvest = find_col(plants, ("estimated_harvest_date", "harvest date"))
    working = plants.copy()
    if planted:
        planted_dates = pd.to_datetime(working[planted], errors="coerce", utc=True)
        working["phase_age_days"] = (pd.Timestamp.now(tz="UTC") - planted_dates).dt.days
    if harvest:
        harvest_dates = pd.to_datetime(working[harvest], errors="coerce", utc=True)
        working["days_until_harvest"] = (harvest_dates - pd.Timestamp.now(tz="UTC")).dt.days
    group_cols = [column for column in (phase, room, strain) if column]
    summary = working.groupby(group_cols, dropna=False).size().reset_index(name="plant_count") if group_cols else pd.DataFrame({"plant_count": [len(working)]})
    forecast = working.copy()
    if "days_until_harvest" in forecast:
        forecast = forecast.loc[forecast["days_until_harvest"].between(-7, 60, inclusive="both")].sort_values("days_until_harvest")
    exception_mask = pd.Series(False, index=working.index)
    if planted:
        exception_mask |= working[planted].isna()
    if harvest and phase:
        exception_mask |= working[phase].astype(str).str.casefold().eq("flowering") & working[harvest].isna()
        exception_mask |= working[phase].astype(str).str.casefold().isin({"clone", "seedling"}) & working[harvest].notna() & (pd.to_datetime(working[harvest], errors="coerce", utc=True) < pd.Timestamp.now(tz="UTC"))
    exceptions = working.loc[exception_mask].copy()
    return {"summary": summary, "harvest_forecast": forecast, "exceptions": exceptions}
