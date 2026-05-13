import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors


EMPLOYEE_COLUMNS = [
    "employee_name", "role", "hourly_wage", "employment_status", "hire_date", "average_weekly_hours",
    "availability_notes", "preferred_shifts", "department", "manager_notes", "callouts_last_90_days",
    "late_arrivals_last_90_days", "no_call_no_show_count", "writeups_count", "last_raise_date", "last_review_date",
    "training_completed", "promotion_interest", "engagement_score",
]
SCHEDULE_COLUMNS = [
    "date", "employee_name", "role", "shift_start", "shift_end", "scheduled_hours", "hourly_wage", "labor_cost",
    "day_of_week", "hour_block", "shift_classification", "actual_hours", "overtime_hours", "callout_flag", "late_flag",
    "covered_shift_flag", "notes",
]
SALES_COLUMNS = ["date", "hour", "day_of_week", "total_sales", "transactions", "units_sold", "average_ticket", "items_per_transaction"]
POS_HOUR_TOTALS_REQUIRED_HEADERS = [
    "Location Name", "Day", "Starting Hour", "Total Orders", "Gross Sales", "Total Inventory Sold", "Total Delivery Orders"
]


def _safe_numeric_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _safe_numeric_sum(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return float(default)
    return float(_safe_numeric_series(df, col, default).sum())


def _safe_numeric_mean(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return float(default)
    s = _safe_numeric_series(df, col, default)
    return float(s.mean()) if len(s) else float(default)


def _read_upload(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def _first_existing_column(df: pd.DataFrame, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _detect_pos_hour_totals(df_raw: pd.DataFrame, scan_rows: int = 10):
    required = {h.lower().strip() for h in POS_HOUR_TOTALS_REQUIRED_HEADERS}
    max_rows = min(scan_rows, len(df_raw))
    for idx in range(max_rows):
        row_values = {str(v).strip().lower() for v in df_raw.iloc[idx].tolist() if pd.notna(v)}
        if required.issubset(row_values):
            return idx
    return None


def _parse_pos_metadata(df_raw: pd.DataFrame, header_row: int):
    metadata = {"export_date": None, "from_date": None, "to_date": None, "location": None, "source_type": "pos_hour_totals"}
    key_map = {"export date": "export_date", "from date": "from_date", "to date": "to_date", "location": "location"}
    for idx in range(max(0, header_row)):
        row = [str(v).strip() for v in df_raw.iloc[idx].tolist() if pd.notna(v) and str(v).strip()]
        if len(row) < 2:
            continue
        key = row[0].lower().rstrip(":")
        if key in key_map:
            metadata[key_map[key]] = row[1]
    metadata["detected_header_row"] = header_row + 1
    return metadata


def _read_sales_upload(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame(columns=SALES_COLUMNS), {"source_type": "unknown"}
    is_excel = uploaded_file.name.lower().endswith((".xlsx", ".xls"))
    df_raw = pd.read_excel(uploaded_file, header=None) if is_excel else pd.read_csv(uploaded_file, header=None)
    header_row = _detect_pos_hour_totals(df_raw, scan_rows=10)
    if header_row is None:
        uploaded_file.seek(0)
        df = _read_upload(uploaded_file)
        return df, {"source_type": "generic_sales"}

    headers = [str(v).strip() for v in df_raw.iloc[header_row].tolist()]
    table = df_raw.iloc[header_row + 1:].copy()
    table.columns = headers
    table = table.dropna(how="all").reset_index(drop=True)
    sales = pd.DataFrame()
    sales["location_name"] = table.get("Location Name")
    sales["day_of_week"] = table.get("Day")
    sales["hour"] = pd.to_numeric(table.get("Starting Hour"), errors="coerce").fillna(-1).astype(int)
    sales["avg_transactions"] = pd.to_numeric(table.get("Total Orders"), errors="coerce").fillna(0.0)
    sales["avg_sales"] = pd.to_numeric(table.get("Gross Sales"), errors="coerce").fillna(0.0)
    sales["avg_items_sold"] = pd.to_numeric(table.get("Total Inventory Sold"), errors="coerce").fillna(0.0)
    sales["avg_delivery_orders"] = pd.to_numeric(table.get("Total Delivery Orders"), errors="coerce").fillna(0.0)
    sales["source_type"] = "pos_hour_totals"
    sales["analysis_granularity"] = "weekday_hour_average"
    # compatibility aliases
    sales["transactions"] = sales["avg_transactions"]
    sales["gross_sales"] = sales["avg_sales"]
    sales["total_sales"] = sales["avg_sales"]
    sales["units_sold"] = sales["avg_items_sold"]
    sales["delivery_orders"] = sales["avg_delivery_orders"]
    sales["net_sales"] = sales["avg_sales"]
    sales["average_ticket"] = sales["avg_sales"] / sales["avg_transactions"].replace(0, pd.NA)
    sales["items_per_transaction"] = sales["avg_items_sold"] / sales["avg_transactions"].replace(0, pd.NA)
    sales["average_ticket"] = sales["average_ticket"].fillna(0.0)
    sales["items_per_transaction"] = sales["items_per_transaction"].fillna(0.0)
    grouped = sales.groupby(["day_of_week", "hour"], dropna=False).agg(
        avg_transactions=("avg_transactions", "mean"),
        avg_sales=("avg_sales", "mean"),
        avg_items_sold=("avg_items_sold", "mean"),
        avg_delivery_orders=("avg_delivery_orders", "mean"),
    ).reset_index()
    # compatibility aliases
    grouped["transactions"] = grouped["avg_transactions"]
    grouped["gross_sales"] = grouped["avg_sales"]
    grouped["total_sales"] = grouped["avg_sales"]
    grouped["units_sold"] = grouped["avg_items_sold"]
    grouped["delivery_orders"] = grouped["avg_delivery_orders"]
    grouped["average_ticket"] = grouped["avg_sales"] / grouped["avg_transactions"].replace(0, pd.NA)
    grouped["items_per_transaction"] = grouped["avg_items_sold"] / grouped["avg_transactions"].replace(0, pd.NA)
    grouped["average_ticket"] = grouped["average_ticket"].fillna(0.0)
    grouped["items_per_transaction"] = grouped["items_per_transaction"].fillna(0.0)
    grouped["source_type"] = "pos_hour_totals"
    grouped["analysis_granularity"] = "weekday_hour_average"

    metadata = _parse_pos_metadata(df_raw, header_row)
    metadata["rows_processed"] = int(len(grouped))
    return grouped, metadata




def _parse_shift_hour(value):
    if pd.isna(value):
        return None, False
    raw = str(value).strip().lower()
    if not raw:
        return None, False
    compact = raw.replace(" ", "")
    suffix = None
    if compact.endswith("am"):
        suffix = "a"
        compact = compact[:-2]
    elif compact.endswith("pm"):
        suffix = "p"
        compact = compact[:-2]
    elif compact.endswith("a"):
        suffix = "a"
        compact = compact[:-1]
    elif compact.endswith("p"):
        suffix = "p"
        compact = compact[:-1]
    if suffix is None:
        return None, True
    hour_text = compact.split(":")[0] if compact else ""
    if not hour_text.isdigit():
        return None, True
    hour = int(hour_text)
    if hour == 0 and suffix == "a":
        # Common OCR issue in retail schedules where opening hour 10a is parsed as 0a.
        return 10, True
    if hour == 0 and suffix == "p":
        return None, True
    if hour < 0 or hour > 12:
        return None, True
    if suffix == "p" and hour != 12:
        hour += 12
    if suffix == "a" and hour == 12:
        hour = 0
    return hour, False


def _expand_schedule_to_hourly(schedule_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    quality = {
        "rows_processed": 0,
        "rows_with_valid_shift_times": 0,
        "rows_missing_shift_start": 0,
        "rows_missing_shift_end": 0,
        "rows_missing_hourly_wage": 0,
        "rows_needing_review": 0,
        "rows_missing_time_range": 0,
        "hourly_rows_generated": 0,
    }
    hourly_cols = ["date", "day_of_week", "employee_name", "role", "hour", "labor_hours", "hourly_wage", "labor_cost", "shift_start", "shift_end", "needs_review", "wage_missing", "missing_time_range"]
    if not isinstance(schedule_df, pd.DataFrame) or schedule_df.empty:
        return pd.DataFrame(columns=hourly_cols), quality

    schedule = schedule_df.copy()
    schedule["date"] = pd.to_datetime(schedule.get("date"), errors="coerce")
    quality["rows_processed"] = int(len(schedule))
    rows = []
    for _, row in schedule.iterrows():
        start_raw = row.get("shift_start")
        end_raw = row.get("shift_end")
        wage = pd.to_numeric(pd.Series([row.get("hourly_wage")]), errors="coerce").iloc[0]
        wage_missing = pd.isna(wage)
        if wage_missing:
            quality["rows_missing_hourly_wage"] += 1
            wage = 0.0
        if pd.isna(start_raw) or str(start_raw).strip() == "":
            quality["rows_missing_shift_start"] += 1
            quality["rows_missing_time_range"] += 1
            continue
        if pd.isna(end_raw) or str(end_raw).strip() == "":
            quality["rows_missing_shift_end"] += 1
            quality["rows_missing_time_range"] += 1
            continue

        start_hour, start_review = _parse_shift_hour(start_raw)
        end_hour, end_review = _parse_shift_hour(end_raw)
        needs_review = start_review or end_review
        if start_hour is None or end_hour is None:
            quality["rows_needing_review"] += 1
            continue
        if end_hour <= start_hour:
            needs_review = True
            quality["rows_needing_review"] += 1
            continue
        quality["rows_with_valid_shift_times"] += 1
        for hour in range(int(start_hour), int(end_hour)):
            rows.append({
                "date": row.get("date"),
                "day_of_week": row.get("day_of_week") if pd.notna(row.get("day_of_week")) else (row.get("date").day_name() if pd.notna(row.get("date")) else pd.NA),
                "employee_name": row.get("employee_name"),
                "role": row.get("role"),
                "hour": int(hour),
                "labor_hours": 1.0,
                "hourly_wage": float(wage),
                "labor_cost": float(wage),
                "shift_start": start_raw,
                "shift_end": end_raw,
                "needs_review": bool(needs_review),
                "wage_missing": bool(wage_missing),
                "missing_time_range": False,
            })
    hourly = pd.DataFrame(rows, columns=hourly_cols)
    quality["hourly_rows_generated"] = int(len(hourly))
    return hourly, quality


def _normalize_data(employees, schedule, sales, thresholds):
    employees = employees.copy() if isinstance(employees, pd.DataFrame) else pd.DataFrame(columns=EMPLOYEE_COLUMNS)
    schedule = schedule.copy() if isinstance(schedule, pd.DataFrame) else pd.DataFrame(columns=SCHEDULE_COLUMNS)
    sales = sales.copy() if isinstance(sales, pd.DataFrame) else pd.DataFrame(columns=SALES_COLUMNS)
    data_quality = {"analysis_granularity": "incomplete", "warnings": []}

    if not schedule.empty:
        schedule["date"] = pd.to_datetime(schedule.get("date"), errors="coerce")
        schedule["scheduled_hours"] = _safe_numeric_series(schedule, "scheduled_hours", 0)
        if "hourly_wage" not in schedule.columns or schedule["hourly_wage"].isna().any():
            wage_map = employees.set_index("employee_name")["hourly_wage"].to_dict() if "employee_name" in employees.columns and "hourly_wage" in employees.columns else {}
            schedule["hourly_wage"] = pd.to_numeric(schedule.get("hourly_wage"), errors="coerce")
            schedule["hourly_wage"] = schedule["hourly_wage"].fillna(schedule.get("employee_name", pd.Series(dtype=str)).map(wage_map))
        schedule["hourly_wage"] = _safe_numeric_series(schedule, "hourly_wage", 0)
        schedule["labor_cost"] = schedule["scheduled_hours"] * schedule["hourly_wage"]
        schedule["day_of_week"] = schedule["date"].dt.day_name()

    if not sales.empty:
        sales["date"] = pd.to_datetime(sales.get("date"), errors="coerce")
        sales["hour"] = _safe_numeric_series(sales, _first_existing_column(sales, ["hour", "sale_hour"]) or "hour", -1)
        sales["total_sales"] = _safe_numeric_series(sales, "total_sales", 0)
        sales["transactions"] = _safe_numeric_series(sales, "transactions", 0)
        if "day_of_week" not in sales.columns or sales["day_of_week"].isna().all():
            sales["day_of_week"] = sales["date"].dt.day_name()

    if schedule.empty or sales.empty:
        return schedule, sales, pd.DataFrame(), data_quality

    schedule_hourly, quality = _expand_schedule_to_hourly(schedule)
    data_quality.update(quality)

    has_hourly = (not schedule_hourly.empty and "day_of_week" in schedule_hourly.columns and "hour" in schedule_hourly.columns)
    if has_hourly and "day_of_week" in sales.columns and "hour" in sales.columns:
        data_quality["analysis_granularity"] = "weekday_hour_average"
        labor_agg = schedule_hourly.groupby(["day_of_week", "hour"], dropna=False).agg(labor_hours=("labor_hours", "sum"), labor_cost=("labor_cost", "sum")).reset_index()
        sales_agg = sales.groupby(["day_of_week", "hour"], dropna=False).agg(total_sales=("total_sales", "sum"), transactions=("transactions", "sum"), units_sold=("units_sold", "sum")).reset_index()
        analysis = labor_agg.merge(sales_agg, on=["day_of_week", "hour"], how="outer")
    else:
        data_quality["analysis_granularity"] = "daily"
        data_quality["warnings"].append("Hourly labor coverage could not be created because shift_start/shift_end were missing or unreadable.")
        data_quality["warnings"].append("Schedule data does not include usable hourly shift times. Retail Ops is using daily labor analysis.")
        labor_agg = schedule.groupby(["day_of_week"], dropna=False).agg(labor_hours=("scheduled_hours", "sum"), labor_cost=("labor_cost", "sum")).reset_index()
        sales_agg = sales.groupby(["day_of_week"], dropna=False).agg(total_sales=("total_sales", "sum"), transactions=("transactions", "sum"), units_sold=("units_sold", "sum")).reset_index()
        analysis = labor_agg.merge(sales_agg, on=["day_of_week"], how="outer")

    analysis["sales_per_labor_hour"] = analysis["total_sales"] / analysis["labor_hours"].replace(0, pd.NA)
    analysis["transactions_per_labor_hour"] = analysis["transactions"] / analysis["labor_hours"].replace(0, pd.NA)
    analysis["labor_pct_of_sales"] = (analysis["labor_cost"] / analysis["total_sales"].replace(0, pd.NA)) * 100
    analysis["recommended_labor_hours"] = (analysis["total_sales"] / max(float(thresholds["target_sales_per_labor_hour"]), 1)).clip(lower=float(thresholds["minimum_staffing_floor"]), upper=float(thresholds["maximum_staffing_cap"]))
    analysis["labor_variance_hours"] = analysis["labor_hours"] - analysis["recommended_labor_hours"]

    def _status(row):
        if pd.isna(row.get("labor_hours")) or pd.isna(row.get("total_sales")):
            return "Data Incomplete"
        if row["labor_pct_of_sales"] > 20 or row["labor_variance_hours"] > 1:
            return "Heavy"
        if row["labor_pct_of_sales"] < 10 and row.get("transactions_per_labor_hour", 0) >= float(thresholds["target_transactions_per_labor_hour"]):
            return "Lean"
        return "Balanced"

    analysis["schedule_status"] = analysis.apply(_status, axis=1)
    return schedule, sales, analysis, data_quality


def _build_retail_ops_executive_report_pdf(payload: dict) -> bytes:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    w, h = letter
    c.setFillColor(colors.HexColor("#111827")); c.rect(0, 0, w, h, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 22); c.drawString(36, h - 70, "Retail Ops Executive Report")
    c.setFont("Helvetica", 11); c.drawString(36, h - 95, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.setFillColor(colors.HexColor("#F97316")); c.rect(36, h-120, w-72, 4, stroke=0, fill=1)
    y = h - 160
    c.setFillColor(colors.white); c.setFont("Helvetica", 10)
    for line in payload.get("summary_lines", ["No summary available."]):
        c.drawString(36, y, str(line)[:110]); y -= 14
    c.showPage(); c.setFont("Helvetica-Bold", 14); c.drawString(36, h-48, "Recommendations")
    c.setFont("Helvetica", 10); y = h-72
    for rec in payload.get("recommendations", ["No recommendations yet."]):
        c.drawString(36, y, f"• {str(rec)[:100]}"); y -= 14
        if y < 40:
            c.showPage(); y = h - 48
    c.save(); out.seek(0)
    return out.read()


def render_retail_ops_command_center():
    st.markdown("## 🏪 Retail Ops Command Center")
    defaults = {
        "target_labor_pct_low": 12.0, "target_labor_pct_high": 18.0, "target_sales_per_labor_hour": 250.0,
        "target_transactions_per_labor_hour": 8.0, "minimum_staffing_floor": 1.0, "maximum_staffing_cap": 60.0,
    }
    st.session_state.setdefault("retail_ops_employees", pd.DataFrame(columns=EMPLOYEE_COLUMNS))
    st.session_state.setdefault("retail_ops_schedule", pd.DataFrame(columns=SCHEDULE_COLUMNS))
    st.session_state.setdefault("retail_ops_sales", pd.DataFrame(columns=SALES_COLUMNS))
    st.session_state.setdefault("retail_ops_sales_metadata", {"source_type": "unknown"})
    st.session_state.setdefault("retail_ops_analysis", pd.DataFrame())
    st.session_state.setdefault("retail_ops_thresholds", defaults.copy())

    tabs = st.tabs(["Overview", "Employees", "Schedule / Labor", "Sales Demand", "Lean vs Heavy Analysis", "Retention KPIs", "Recommendations", "Export Report"])

    with tabs[1]:
        up = st.file_uploader("Upload Employee Roster (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="retail_emp_upload")
        if up is not None:
            st.session_state["retail_ops_employees"] = _read_upload(up)
        st.session_state["retail_ops_employees"] = st.data_editor(st.session_state["retail_ops_employees"], use_container_width=True, num_rows="dynamic")

    with tabs[2]:
        up = st.file_uploader("Upload Schedule / Labor (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="retail_sched_upload")
        if up is not None:
            st.session_state["retail_ops_schedule"] = _read_upload(up)
        st.session_state["retail_ops_schedule"] = st.data_editor(st.session_state["retail_ops_schedule"], use_container_width=True, num_rows="dynamic")

    with tabs[3]:
        up = st.file_uploader("Upload Sales Demand (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="retail_sales_upload")
        if up is not None:
            sales_df, sales_meta = _read_sales_upload(up)
            st.session_state["retail_ops_sales"] = sales_df
            st.session_state["retail_ops_sales_metadata"] = sales_meta | {"analysis_granularity": sales_df.get("analysis_granularity", pd.Series(dtype=str)).iloc[0] if not sales_df.empty and "analysis_granularity" in sales_df.columns else "date_hour"}
        st.session_state["retail_ops_sales"] = st.data_editor(st.session_state["retail_ops_sales"], use_container_width=True, num_rows="dynamic")
        meta = st.session_state.get("retail_ops_sales_metadata", {})
        if meta.get("source_type") == "pos_hour_totals":
            st.caption("Sales Data Quality")
            st.write({
                "Source Type": "POS Hour Totals",
                "Location": meta.get("location"),
                "From Date": meta.get("from_date"),
                "To Date": meta.get("to_date"),
                "Export Date": meta.get("export_date"),
                "Rows Processed": meta.get("rows_processed"),
                "Detected Header Row": meta.get("detected_header_row"),
                "Analysis Type": "Average Weekday/Hour Demand Pattern",
                "Sales Column": "Gross Sales -> avg_sales",
                "Transaction Column": "Total Orders -> avg_transactions",
                "Units Column": "Total Inventory Sold -> avg_items_sold",
                "Delivery Orders Column": "Total Delivery Orders -> avg_delivery_orders",
            })
            st.warning("This report provides averaged demand by weekday/hour, not exact transaction-level sales.")

    with st.expander("Threshold Settings", expanded=False):
        for k in defaults:
            st.session_state["retail_ops_thresholds"][k] = st.number_input(k, value=float(st.session_state["retail_ops_thresholds"].get(k, defaults[k])), key=f"retail_thr_{k}")

    schedule, sales, analysis, data_quality = _normalize_data(st.session_state["retail_ops_employees"], st.session_state["retail_ops_schedule"], st.session_state["retail_ops_sales"], st.session_state["retail_ops_thresholds"])
    st.session_state["retail_ops_analysis"] = analysis

    total_labor_cost = _safe_numeric_sum(schedule, "labor_cost")
    total_labor_hours = _safe_numeric_sum(schedule, "scheduled_hours")
    total_sales = _safe_numeric_sum(sales, "total_sales")
    total_transactions = _safe_numeric_sum(sales, "transactions")
    sales_per_hour = total_sales / total_labor_hours if total_labor_hours else 0.0
    tx_per_hour = total_transactions / total_labor_hours if total_labor_hours else 0.0
    labor_pct = (total_labor_cost / total_sales * 100) if total_sales else 0.0
    open_hour_rows = int(len(sales[sales.get("hour", pd.Series(dtype=float)).ge(0)]) if not sales.empty and "hour" in sales.columns else 0)
    avg_sales_open_hour = (total_sales / open_hour_rows) if open_hour_rows else 0.0
    avg_tx_open_hour = (total_transactions / open_hour_rows) if open_hour_rows else 0.0
    delivery_total = _safe_numeric_sum(sales, "delivery_orders")
    delivery_share = (delivery_total / total_transactions * 100) if total_transactions else 0.0
    busiest_day = "N/A"
    busiest_hour = "N/A"
    peak_avg_tx = peak_avg_sales = peak_avg_items = peak_avg_delivery = 0.0
    slowest_window = "N/A"
    if not sales.empty and {"day_of_week", "hour", "avg_transactions", "avg_sales", "avg_items_sold", "avg_delivery_orders"}.issubset(set(sales.columns)):
        by_day = sales.groupby("day_of_week", dropna=False)["avg_transactions"].mean().sort_values(ascending=False)
        if not by_day.empty:
            busiest_day = str(by_day.index[0])
        by_hour = sales.groupby("hour", dropna=False)["avg_transactions"].mean().sort_values(ascending=False)
        if not by_hour.empty:
            busiest_hour = f"{int(by_hour.index[0])}:00"
        peak_avg_tx = float(sales["avg_transactions"].max())
        peak_avg_sales = float(sales["avg_sales"].max())
        peak_avg_items = float(sales["avg_items_sold"].max())
        peak_avg_delivery = float(sales["avg_delivery_orders"].max())
        slow_row = sales.loc[sales["avg_transactions"].idxmin()]
        slowest_window = f"{slow_row.get('day_of_week', 'N/A')} @ {int(slow_row.get('hour', -1))}:00"

    status = "Data Incomplete" if analysis.empty else ("Heavy" if labor_pct > 20 else "Lean" if labor_pct < 10 and tx_per_hour > st.session_state["retail_ops_thresholds"]["target_transactions_per_labor_hour"] else "Balanced")

    with tabs[0]:
        cols = st.columns(4)
        metrics = [
            ("Total Labor Cost", f"${total_labor_cost:,.0f}"), ("Total Labor Hours", f"{total_labor_hours:,.1f}"),
            ("Labor Cost per Hour", f"${(total_labor_cost/total_labor_hours if total_labor_hours else 0):,.2f}"), ("Labor % of Sales", f"{labor_pct:.1f}%"),
            ("Avg Demand Sales per Labor Hour", f"${sales_per_hour:,.1f}"), ("Avg Demand Tx per Labor Hour", f"{tx_per_hour:,.1f}"),
            ("Avg Hourly Wage", f"${_safe_numeric_mean(schedule, 'hourly_wage'):,.2f}"), ("Scheduled Employees", str(schedule.get("employee_name", pd.Series(dtype=str)).nunique() if not schedule.empty else 0)),
            ("Lean Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Lean").sum()))), ("Heavy Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Heavy").sum()))),
            ("Balanced Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Balanced").sum()))), ("Retention Risk Score", "0"),
            ("Busiest Day", busiest_day), ("Busiest Hour", busiest_hour),
            ("Peak Avg Transactions", f"{peak_avg_tx:,.1f}"), ("Peak Avg Sales", f"${peak_avg_sales:,.1f}"),
            ("Peak Avg Items Sold", f"{peak_avg_items:,.1f}"), ("Peak Avg Delivery Orders", f"{peak_avg_delivery:,.1f}"),
            ("Average Sales per Open Hour", f"${avg_sales_open_hour:,.1f}"), ("Average Transactions per Open Hour", f"{avg_tx_open_hour:,.1f}"),
            ("Delivery Demand Share", f"{delivery_share:.1f}%"), ("Slowest Demand Window", slowest_window),
        ]
        for i, m in enumerate(metrics):
            cols[i % 4].metric(m[0], m[1])
        st.info(f"Labor Health Status: **{status}**")
        st.caption("Demand interpretation: values are average weekday/hour demand patterns (not transaction-level period totals).")
        st.caption("Schedule Data Quality")
        st.write({
            "Rows Processed": data_quality.get("rows_processed", 0),
            "Rows with Valid shift_start/shift_end": data_quality.get("rows_with_valid_shift_times", 0),
            "Rows Missing shift_start": data_quality.get("rows_missing_shift_start", 0),
            "Rows Missing shift_end": data_quality.get("rows_missing_shift_end", 0),
            "Rows Missing hourly_wage": data_quality.get("rows_missing_hourly_wage", 0),
            "Rows Needing Review": data_quality.get("rows_needing_review", 0),
            "Rows Missing Time Range": data_quality.get("rows_missing_time_range", 0),
            "Hourly Rows Generated": data_quality.get("hourly_rows_generated", 0),
            "Analysis Granularity": data_quality.get("analysis_granularity", "incomplete"),
        })
        for warning in data_quality.get("warnings", []):
            st.warning(warning)

    with tabs[4]:
        if analysis.empty:
            st.warning("Upload schedule and sales data to run lean vs heavy analysis.")
        else:
            st.dataframe(analysis, use_container_width=True)
            if "date" in analysis.columns and pd.api.types.is_datetime64_any_dtype(analysis["date"]):
                by_day = analysis.groupby(analysis["date"].dt.date).agg(labor_cost=("labor_cost", "sum"), total_sales=("total_sales", "sum"), sales_per_labor_hour=("sales_per_labor_hour", "mean"), labor_pct_of_sales=("labor_pct_of_sales", "mean"), transactions_per_labor_hour=("transactions_per_labor_hour", "mean")).reset_index()
                st.line_chart(by_day.set_index("date")[["labor_cost", "total_sales"]])
                st.line_chart(by_day.set_index("date")[["sales_per_labor_hour", "labor_pct_of_sales", "transactions_per_labor_hour"]])
            else:
                st.caption("Daily date trend chart unavailable for weekday/hour aggregated analysis.")

    with tabs[5]:
        st.metric("Active Employee Count", int((st.session_state["retail_ops_employees"].get("employment_status", pd.Series(dtype=str)).astype(str).str.lower() == "active").sum()) if not st.session_state["retail_ops_employees"].empty else 0)
        st.metric("Turnover Rate", "0.0%")

    with tabs[6]:
        recs = []
        if labor_pct > st.session_state["retail_ops_thresholds"]["target_labor_pct_high"]:
            recs.append("Labor cost is above target while sales per labor hour is below goal. Consider reducing low-demand coverage.")
        if tx_per_hour > st.session_state["retail_ops_thresholds"]["target_transactions_per_labor_hour"]:
            recs.append("Transactions per labor hour are elevated in peak windows; review for lean staffing and add one associate in peak hours.")
        if analysis.empty:
            recs.append("Data quality: upload both schedule and sales datasets to unlock complete recommendations.")
        for rec in recs or ["No major issues detected. Continue monitoring for trend changes."]:
            st.write(f"- {rec}")
        st.session_state["retail_ops_recommendations"] = recs

    with tabs[7]:
        payload = {"summary_lines": [f"Labor cost % of sales: {labor_pct:.1f}%", f"Sales per labor hour: ${sales_per_hour:,.1f}", f"Transactions per labor hour: {tx_per_hour:,.1f}", f"Labor health status: {status}"], "recommendations": st.session_state.get("retail_ops_recommendations", [])}
        pdf_bytes = _build_retail_ops_executive_report_pdf(payload)
        st.download_button("Export Retail Ops Report", data=pdf_bytes, file_name=f"retail_ops_executive_report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf", mime="application/pdf")
