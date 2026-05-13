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


def _normalize_data(employees, schedule, sales, thresholds):
    employees = employees.copy() if isinstance(employees, pd.DataFrame) else pd.DataFrame(columns=EMPLOYEE_COLUMNS)
    schedule = schedule.copy() if isinstance(schedule, pd.DataFrame) else pd.DataFrame(columns=SCHEDULE_COLUMNS)
    sales = sales.copy() if isinstance(sales, pd.DataFrame) else pd.DataFrame(columns=SALES_COLUMNS)

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
        sales["hour"] = _safe_numeric_series(sales, "hour", -1)
        sales["total_sales"] = _safe_numeric_series(sales, "total_sales", 0)
        sales["transactions"] = _safe_numeric_series(sales, "transactions", 0)
        sales["day_of_week"] = sales["date"].dt.day_name()

    if schedule.empty or sales.empty:
        return schedule, sales, pd.DataFrame()

    group_cols = ["date"] + (["hour_block"] if "hour_block" in schedule.columns and "hour" in sales.columns else [])
    labor_agg = schedule.groupby(group_cols, dropna=False).agg(labor_hours=("scheduled_hours", "sum"), labor_cost=("labor_cost", "sum")).reset_index()
    sales_group_cols = ["date"] + (["hour"] if "hour" in sales.columns and "hour_block" in group_cols else [])
    sales_agg = sales.groupby(sales_group_cols, dropna=False).agg(total_sales=("total_sales", "sum"), transactions=("transactions", "sum")).reset_index()
    analysis = labor_agg.merge(sales_agg, on="date", how="outer")

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
        if float(thresholds["target_labor_pct_low"]) <= row["labor_pct_of_sales"] <= float(thresholds["target_labor_pct_high"]):
            return "Balanced"
        return "Balanced"

    analysis["schedule_status"] = analysis.apply(_status, axis=1)
    return schedule, sales, analysis


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
            st.session_state["retail_ops_sales"] = _read_upload(up)
        st.session_state["retail_ops_sales"] = st.data_editor(st.session_state["retail_ops_sales"], use_container_width=True, num_rows="dynamic")

    with st.expander("Threshold Settings", expanded=False):
        for k in defaults:
            st.session_state["retail_ops_thresholds"][k] = st.number_input(k, value=float(st.session_state["retail_ops_thresholds"].get(k, defaults[k])), key=f"retail_thr_{k}")

    schedule, sales, analysis = _normalize_data(st.session_state["retail_ops_employees"], st.session_state["retail_ops_schedule"], st.session_state["retail_ops_sales"], st.session_state["retail_ops_thresholds"])
    st.session_state["retail_ops_analysis"] = analysis

    total_labor_cost = _safe_numeric_sum(schedule, "labor_cost")
    total_labor_hours = _safe_numeric_sum(schedule, "scheduled_hours")
    total_sales = _safe_numeric_sum(sales, "total_sales")
    total_transactions = _safe_numeric_sum(sales, "transactions")
    sales_per_hour = total_sales / total_labor_hours if total_labor_hours else 0.0
    tx_per_hour = total_transactions / total_labor_hours if total_labor_hours else 0.0
    labor_pct = (total_labor_cost / total_sales * 100) if total_sales else 0.0

    status = "Data Incomplete" if analysis.empty else ("Heavy" if labor_pct > 20 else "Lean" if labor_pct < 10 and tx_per_hour > st.session_state["retail_ops_thresholds"]["target_transactions_per_labor_hour"] else "Balanced")

    with tabs[0]:
        cols = st.columns(4)
        metrics = [
            ("Total Labor Cost", f"${total_labor_cost:,.0f}"), ("Total Labor Hours", f"{total_labor_hours:,.1f}"),
            ("Labor Cost per Hour", f"${(total_labor_cost/total_labor_hours if total_labor_hours else 0):,.2f}"), ("Labor % of Sales", f"{labor_pct:.1f}%"),
            ("Sales per Labor Hour", f"${sales_per_hour:,.1f}"), ("Transactions per Labor Hour", f"{tx_per_hour:,.1f}"),
            ("Avg Hourly Wage", f"${_safe_numeric_mean(schedule, 'hourly_wage'):,.2f}"), ("Scheduled Employees", str(schedule.get("employee_name", pd.Series(dtype=str)).nunique() if not schedule.empty else 0)),
            ("Lean Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Lean").sum()))), ("Heavy Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Heavy").sum()))),
            ("Balanced Hours Count", str(int((analysis.get("schedule_status", pd.Series(dtype=str)) == "Balanced").sum()))), ("Retention Risk Score", "0"),
        ]
        for i, m in enumerate(metrics):
            cols[i % 4].metric(m[0], m[1])
        st.info(f"Labor Health Status: **{status}**")

    with tabs[4]:
        if analysis.empty:
            st.warning("Upload schedule and sales data to run lean vs heavy analysis.")
        else:
            st.dataframe(analysis, use_container_width=True)
            by_day = analysis.groupby(analysis["date"].dt.date).agg(labor_cost=("labor_cost", "sum"), total_sales=("total_sales", "sum"), sales_per_labor_hour=("sales_per_labor_hour", "mean"), labor_pct_of_sales=("labor_pct_of_sales", "mean"), transactions_per_labor_hour=("transactions_per_labor_hour", "mean")).reset_index()
            st.line_chart(by_day.set_index("date")[["labor_cost", "total_sales"]])
            st.line_chart(by_day.set_index("date")[["sales_per_labor_hour", "labor_pct_of_sales", "transactions_per_labor_hour"]])

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
