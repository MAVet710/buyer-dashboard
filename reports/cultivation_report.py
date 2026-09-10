from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    ReportMetric,
    ReportPalette,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import display_frame, first_present, frame, numeric_mean, numeric_sum, resolve_column


CULTIVATION_PALETTE = ReportPalette(
    accent="#68B36B",
    accent_soft="#EAF6E8",
    accent_dark="#285A2B",
    division="CULTIVATION OPS",
)

REPORT_TITLES = {
    "overview": (
        "Cultivation Operations Executive Report",
        "Plant population, rooms, harvest performance, yield, cost, and near-term grow risk.",
    ),
    "plants": (
        "Cultivation Plant Inventory Report",
        "Current plant population by tag, strain, phase, room, mother, and harvest timing.",
    ),
    "harvests": (
        "Cultivation Harvest Yield & Cost Report",
        "Harvest weights, dry yield, waste, labor, COGS, and cost-per-dry-gram performance.",
    ),
    "rooms": (
        "Cultivation Room Capacity Report",
        "Room population, capacity utilization, phase alignment, cost, and next harvest timing.",
    ),
}


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _plants_display(plants: pd.DataFrame) -> pd.DataFrame:
    return display_frame(
        plants,
        [
            ("Plant Tag", ["plant tag", "plant_tag"]),
            ("Strain", ["strain", "strain name", "strain_name"]),
            ("Phase", ["phase"]),
            ("Room", ["room", "room code", "room_code"]),
            ("Mother", ["mother", "mother plant tag", "mother_plant_tag"]),
            ("Planted", ["planted", "planted at", "planted_at"]),
            ("Est. Harvest", ["estimated harvest", "estimated harvest date", "estimated_harvest_date"]),
        ],
    )


def _rooms_display(rooms: pd.DataFrame) -> pd.DataFrame:
    return display_frame(
        rooms,
        [
            ("Room", ["room", "room code", "room_code"]),
            ("Name", ["name", "display name", "display_name"]),
            ("Phase", ["phase"]),
            ("Plants", ["active plants", "active_plants"]),
            ("Capacity", ["plant capacity", "plant_capacity"]),
            ("Utilization %", ["utilization pct", "utilization_pct"]),
            ("Remaining", ["capacity remaining", "capacity_remaining"]),
            ("Phase Mismatch", ["phase mismatch count", "phase_mismatch_count"]),
            ("Next Harvest", ["next estimated harvest", "next_estimated_harvest"]),
            ("Room Cost", ["total cost usd", "total_cost_usd"]),
        ],
    )


def _harvests_display(harvests: pd.DataFrame) -> pd.DataFrame:
    return display_frame(
        harvests,
        [
            ("Harvest", ["harvest", "harvest code", "harvest_code"]),
            ("Strain", ["strain", "strain name", "strain_name"]),
            ("Room", ["room", "room code", "room_code"]),
            ("Status", ["status"]),
            ("Plants", ["plant count", "plant_count"]),
            ("Wet Weight g", ["wet weight", "wet_weight"]),
            ("Dry Weight g", ["dry weight", "dry_weight"]),
            ("Waste Weight g", ["waste weight", "waste_weight"]),
            ("Dry Yield %", ["dry yield pct", "dry_yield_pct"]),
            ("Labor Hours", ["labor hours", "labor_hours"]),
            ("Total COGS", ["total cogs usd", "total_cogs_usd"]),
            ("Cost / Dry g", ["cost per dry unit", "cost_per_dry_unit"]),
        ],
    )


def _phase_chart(plants: pd.DataFrame) -> list[tuple[str, float, str]]:
    column = resolve_column(plants, "phase")
    if column is None:
        return []
    counts = plants[column].fillna("Unknown").astype(str).value_counts()
    return [(phase.title(), float(count), f"{int(count):,} plants") for phase, count in counts.items()]


def _room_chart(rooms: pd.DataFrame) -> list[tuple[str, float, str]]:
    name_col = resolve_column(rooms, "display_name", "room_code")
    utilization_col = resolve_column(rooms, "utilization_pct")
    if name_col is None or utilization_col is None:
        return []
    values = pd.to_numeric(rooms[utilization_col], errors="coerce").fillna(0)
    return [
        (str(rooms.iloc[index][name_col]), float(value), f"{float(value):,.1f}% utilized")
        for index, value in enumerate(values.head(12))
    ]


def _harvest_chart(harvests: pd.DataFrame) -> list[tuple[str, float, str]]:
    name_col = resolve_column(harvests, "harvest_code")
    yield_col = resolve_column(harvests, "dry_yield_pct")
    if name_col is None or yield_col is None:
        return []
    values = pd.to_numeric(harvests[yield_col], errors="coerce").fillna(0)
    return [
        (str(harvests.iloc[index][name_col]), float(value), f"{float(value):,.1f}% dry yield")
        for index, value in enumerate(values.head(12))
    ]


def _build_cultivation_executive_report_pdf(payload: dict, view: str = "overview") -> bytes:
    payload = payload or {}
    if view not in REPORT_TITLES:
        raise ValueError("Unsupported cultivation report view.")

    summary = payload.get("summary") or {}
    kpis = payload.get("kpis") or {}
    plants = frame(payload.get("plants"))
    rooms = frame(payload.get("rooms"))
    harvests = frame(payload.get("harvests"))
    plants_display = _plants_display(plants)
    rooms_display = _rooms_display(rooms)
    harvests_display = _harvests_display(harvests)

    active_plants = _integer(first_present(kpis, ["active_plants"], len(plants)))
    flowering_plants = _integer(first_present(kpis, ["flowering_plants"], 0))
    due_14_days = _integer(first_present(kpis, ["harvest_due_14_days"], 0))
    overdue = _integer(first_present(kpis, ["harvest_overdue"], 0))
    active_rooms = _integer(first_present(kpis, ["active_rooms"], len(rooms)))
    room_capacity = _integer(first_present(kpis, ["room_capacity"], numeric_sum(rooms, "plant_capacity")))
    over_capacity_rooms = _integer(first_present(kpis, ["over_capacity_rooms"], 0))
    phase_mismatches = _integer(first_present(kpis, ["phase_mismatch_count"], numeric_sum(rooms, "phase_mismatch_count")))
    open_harvests = _integer(first_present(kpis, ["open_harvests"], 0))
    completed_harvests = _integer(first_present(kpis, ["completed_harvests"], 0))
    wet_weight = _number(first_present(kpis, ["total_wet_weight_g"], numeric_sum(harvests, "wet_weight")))
    dry_weight = _number(first_present(kpis, ["total_dry_weight_g"], numeric_sum(harvests, "dry_weight")))
    waste_weight = _number(first_present(kpis, ["total_waste_weight_g"], numeric_sum(harvests, "waste_weight")))
    average_yield = _number(first_present(kpis, ["avg_dry_yield_pct"], numeric_mean(harvests, "dry_yield_pct")))
    total_cogs = _number(first_present(kpis, ["total_cogs_usd"], numeric_sum(harvests, "total_cogs_usd")))
    cost_per_dry_g = _number(first_present(kpis, ["cost_per_dry_g"], total_cogs / dry_weight if dry_weight > 0 else 0))
    total_strains = _integer(first_present(kpis, ["strain_count"], 0))

    findings: list[str] = []
    if plants.empty and rooms.empty and harvests.empty:
        findings.append("No cultivation plant, room, or harvest records are available for this facility.")
    if overdue:
        findings.append(f"{overdue} active plants are past their estimated harvest date.")
    if over_capacity_rooms:
        findings.append(f"{over_capacity_rooms} cultivation rooms are over configured plant capacity.")
    if phase_mismatches:
        findings.append(f"{phase_mismatches} active plants are in rooms configured for a different phase.")
    if open_harvests and wet_weight <= 0:
        findings.append("Open harvests exist but no wet harvest weight has been recorded in the report set.")
    if not findings:
        findings.append("No material cultivation capacity, timing, or harvest exceptions were detected.")

    recommendations: list[str] = []
    if overdue:
        recommendations.append("Review overdue flowering plants and either update the harvest estimate or move them into an active harvest.")
    if over_capacity_rooms:
        recommendations.append("Rebalance plants out of over-capacity rooms before the next plant movement or transplant cycle.")
    if phase_mismatches:
        recommendations.append("Resolve room-phase mismatches so environmental targets and plant-stage assumptions stay aligned.")
    if completed_harvests and dry_weight <= 0:
        recommendations.append("Record dry closeout weights before using yield or cost-per-dry-gram metrics for decisions.")
    if not recommendations:
        recommendations.append("Maintain room-capacity discipline and review estimated harvest dates, weights, yield, and cost at each harvest closeout.")

    title, subtitle = REPORT_TITLES[view]
    if view == "plants":
        metrics = [
            ReportMetric("Active Plants", f"{active_plants:,}", "Clone through flowering"),
            ReportMetric("Flowering", f"{flowering_plants:,}", "Current flowering population"),
            ReportMetric("Due in 14 Days", f"{due_14_days:,}", "Estimated harvest window"),
            ReportMetric("Overdue", f"{overdue:,}", "Past estimated harvest date"),
            ReportMetric("Strains", f"{total_strains:,}", "Active genetic names"),
            ReportMetric("Active Rooms", f"{active_rooms:,}", "Configured grow rooms"),
        ]
        chart_title = "Plant Population by Phase"
        chart_items = _phase_chart(plants)
        sections = [ReportSection("Plant Inventory", plants_display, "Plant-level grow inventory for the current facility.", max_rows=120)]
        brief = f"{active_plants:,} active plants span {total_strains:,} strains and {active_rooms:,} active rooms; {flowering_plants:,} are flowering and {due_14_days:,} are estimated for harvest within 14 days."
    elif view == "harvests":
        metrics = [
            ReportMetric("Open Harvests", f"{open_harvests:,}", "Planned, active, or drying"),
            ReportMetric("Completed", f"{completed_harvests:,}", "Closed harvests"),
            ReportMetric("Wet Weight", f"{wet_weight:,.0f} g", "Recorded harvest input"),
            ReportMetric("Dry Weight", f"{dry_weight:,.0f} g", "Recovered dry material"),
            ReportMetric("Waste", f"{waste_weight:,.0f} g", "Recorded harvest waste"),
            ReportMetric("Avg Dry Yield", f"{average_yield:,.1f}%", "Across weighted harvests"),
            ReportMetric("Cultivation COGS", f"${total_cogs:,.2f}", "Harvest-linked recorded cost"),
            ReportMetric("Cost / Dry g", f"${cost_per_dry_g:,.4f}", "Across recorded dry weight"),
        ]
        chart_title = "Dry Yield by Harvest"
        chart_items = _harvest_chart(harvests)
        sections = [ReportSection("Harvest Yield & Cost", harvests_display, "Yield, waste, labor, and cost performance by harvest.", max_rows=100)]
        brief = f"{completed_harvests:,} completed harvests produced {dry_weight:,.0f} g dry material at {average_yield:,.1f}% average dry yield with ${total_cogs:,.2f} in recorded harvest COGS."
    elif view == "rooms":
        utilization = active_plants / room_capacity * 100 if room_capacity else 0.0
        metrics = [
            ReportMetric("Active Rooms", f"{active_rooms:,}", "Configured grow rooms"),
            ReportMetric("Active Plants", f"{active_plants:,}", "Current room population"),
            ReportMetric("Plant Capacity", f"{room_capacity:,}", "Configured active capacity"),
            ReportMetric("Utilization", f"{utilization:,.1f}%", "Plants / configured capacity"),
            ReportMetric("Over Capacity", f"{over_capacity_rooms:,}", "Rooms above capacity"),
            ReportMetric("Phase Mismatches", f"{phase_mismatches:,}", "Plants outside room phase"),
        ]
        chart_title = "Room Capacity Utilization"
        chart_items = _room_chart(rooms)
        sections = [ReportSection("Room Capacity & Utilization", rooms_display, "Room occupancy, phase alignment, cost, and upcoming harvest pressure.", max_rows=80)]
        brief = f"{active_plants:,} active plants occupy {active_rooms:,} rooms against {room_capacity:,} configured plant slots ({utilization:,.1f}% utilization)."
    else:
        metrics = [
            ReportMetric("Active Plants", f"{active_plants:,}", f"{flowering_plants:,} flowering"),
            ReportMetric("Harvest Due", f"{due_14_days:,}", "Next 14 days"),
            ReportMetric("Active Rooms", f"{active_rooms:,}", f"{over_capacity_rooms:,} over capacity"),
            ReportMetric("Open Harvests", f"{open_harvests:,}", f"{completed_harvests:,} completed"),
            ReportMetric("Dry Weight", f"{dry_weight:,.0f} g", "Recorded harvest output"),
            ReportMetric("Avg Dry Yield", f"{average_yield:,.1f}%", "Across weighted harvests"),
            ReportMetric("Cultivation COGS", f"${total_cogs:,.2f}", "Recorded harvest cost"),
            ReportMetric("Cost / Dry g", f"${cost_per_dry_g:,.4f}", "Recorded harvest cost efficiency"),
        ]
        chart_title = "Plant Population by Phase"
        chart_items = _phase_chart(plants)
        sections = [
            ReportSection("Plant Inventory", plants_display, "Plant-level grow inventory and expected harvest timing.", max_rows=100),
            ReportSection("Room Capacity & Utilization", rooms_display, "Occupancy, phase alignment, cost, and upcoming harvest pressure.", max_rows=80),
            ReportSection("Harvest Yield & Cost", harvests_display, "Weights, yield, waste, labor, and cost by harvest.", max_rows=100),
        ]
        brief = f"{active_plants:,} active plants across {active_rooms:,} rooms support {open_harvests:,} open harvests. Recorded harvest output is {dry_weight:,.0f} g dry at {average_yield:,.1f}% average yield and ${cost_per_dry_g:,.4f} per dry gram."

    spec = ExecutiveReportSpec(
        title=title,
        subtitle=subtitle,
        palette=CULTIVATION_PALETTE,
        organization=str(summary.get("organization") or "Current cultivation operation"),
        facility=str(summary.get("facility") or summary.get("facility_context") or "Current cultivation facility"),
        reporting_period=str(summary.get("reporting_period") or "Current cultivation records"),
        metrics=metrics,
        executive_brief=brief,
        findings=findings,
        recommendations=recommendations,
        chart_title=chart_title,
        chart_items=chart_items,
        sections=sections,
    )
    return build_executive_pdf(spec)
