from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import CrewAvailability, Facility, FacilityMachine, MachineModel, ProductionOrder
from modules.production_erp.scheduling import ProductionScheduleService
from services.agent_registry import AgentProfile

from .datasets import DatasetAccessContext


ACTION_ROLES = {"dev", "admin", "planner", "supervisor"}
MATERIAL_STAGING_WARNING = "material_unreserved"
HELD_STATUSES = {"on_hold", "hold", "held"}
CLOSED_STATUSES = {"complete", "completed", "cancelled", "canceled"}

ActionHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ActionToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ActionHandler
    mutates: bool = True

    def provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AgentActionRegistry:
    """Server-owned, role-gated operational actions for Doobie Agent.

    Read tools remain separate from operational actions. Organization, facility,
    user and capability scope come only from trusted request context. The model
    cannot choose tenant scope, bypass warnings, or manufacture approval.
    """

    def __init__(self, *, profile: AgentProfile, access: DatasetAccessContext, question: str) -> None:
        self.profile = profile
        self.access = access
        self.question = str(question or "").strip()
        self._tools: dict[str, ActionToolSpec] = {}
        self._mutated = False
        self._results: list[dict[str, Any]] = []
        if (
            profile.key == "coman"
            and access.operation_type == "production"
            and "production" in access.capabilities
            and access.engine is not None
            and str(access.role or "").casefold() in ACTION_ROLES
        ):
            self._register_production_actions()

    def _register(self, spec: ActionToolSpec) -> None:
        self._tools[spec.name] = spec

    def _register_production_actions(self) -> None:
        self._register(
            ActionToolSpec(
                name="production_schedule_week",
                description=(
                    "Build a deterministic production week from current production orders using BOM standards, available inventory, "
                    "existing reservations, crew, active machines, current calendar placements, QA state and due dates. Commit only "
                    "fully ready placements. If material exists but is not staged, return the exact candidate lots and require a human-"
                    "selected destination work location before any reservation or Metrc package move. Never guess the work location, "
                    "silently reserve material, or auto-accept warnings/blockers."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "week_start": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD facility-local date, or internal token next_week.",
                        },
                        "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 5},
                        "max_runs": {"type": "integer", "minimum": 1, "maximum": 20, "default": 12},
                        "commit": {
                            "type": "boolean",
                            "default": False,
                            "description": "Commit only fully ready placements. Staging-dependent placements remain proposed.",
                        },
                    },
                },
                handler=self._production_schedule_week,
            )
        )

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.provider_schema() for spec in self._tools.values()]

    @property
    def mutation_performed(self) -> bool:
        return self._mutated

    @property
    def results(self) -> list[dict[str, Any]]:
        return list(self._results)

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        spec = self._tools.get(str(name or ""))
        if spec is None:
            return {"error": "action_unavailable", "tool": name}
        try:
            result = spec.handler(dict(arguments or {}))
        except Exception as exc:
            result = {
                "error": "action_failed",
                "tool": name,
                "detail": str(exc)[:500] or exc.__class__.__name__,
                "mutation_performed": False,
            }
        result.setdefault("tool", spec.name)
        if bool(result.get("mutation_performed")):
            self._mutated = True
        self._results.append(result)
        return result

    def deterministic_request(self) -> tuple[str, dict[str, Any]] | None:
        if "production_schedule_week" not in self._tools:
            return None
        text_value = self.question.casefold()
        has_period = any(token in text_value for token in ("week", "weekly", "five day", "5 day", "next 5"))
        has_schedule_target = any(token in text_value for token in ("calendar", "schedule", "scheduling"))
        has_production = any(token in text_value for token in ("production", "run", "runs", "jobs", "co-man", "coman"))
        has_plan_language = any(token in text_value for token in ("plan", "scheme", "production plan", "production scheme", "run plan"))
        explicit_mutation = self._explicit_mutation_intent(text_value)
        if not (has_schedule_target and has_production and (has_period or has_plan_language or explicit_mutation)):
            return None
        arguments: dict[str, Any] = {
            "commit": explicit_mutation,
            "days": 5,
            "max_runs": 12,
        }
        if "next week" in text_value or "next week's" in text_value or "next weeks" in text_value:
            arguments["week_start"] = "next_week"
        return "production_schedule_week", arguments

    @staticmethod
    def _explicit_mutation_intent(text_value: str) -> bool:
        return any(
            phrase in text_value
            for phrase in (
                "schedule it",
                "schedule the",
                "schedule a",
                "schedule production",
                "schedule my production",
                "put it on the calendar",
                "put them on the calendar",
                "put the plan on the calendar",
                "add it to the calendar",
                "add them to the calendar",
                "map out",
                "map the",
                "place it on",
                "place them on",
                "commit",
                "apply the plan",
                "apply it to the calendar",
                "build the calendar",
                "build out",
                "build a production plan",
                "build a production scheme",
                "build a production schedule",
                "build the production plan",
                "build the production scheme",
                "build the production schedule",
                "create a production plan",
                "create a production scheme",
                "create a production schedule",
                "create the production plan",
                "create the production scheme",
                "create the production schedule",
                "make a production plan",
                "make a production scheme",
                "make a production schedule",
                "make the production plan",
                "make the production scheme",
                "make the production schedule",
                "populate the calendar",
                "implement the plan",
                "implement the schedule",
            )
        )

    def _production_schedule_week(self, args: dict[str, Any]) -> dict[str, Any]:
        commit = bool(args.get("commit", False))
        if commit and not self._explicit_mutation_intent(self.question.casefold()):
            return {
                "error": "confirmation_required",
                "message": "The user did not explicitly ask Doobie Agent to change the production calendar.",
                "mutation_performed": False,
            }
        return ProductionWeekActionPlanner(self.access).plan(
            week_start=str(args.get("week_start") or ""),
            days=max(1, min(int(args.get("days") or 5), 7)),
            max_runs=max(1, min(int(args.get("max_runs") or 12), 20)),
            commit=commit,
            reason="Doobie Agent weekly production plan",
        )

    @staticmethod
    def format_result(result: dict[str, Any]) -> str:
        if result.get("error"):
            return str(result.get("message") or result.get("detail") or "The requested Agent action could not be completed.")
        placements = list(result.get("placements") or [])
        staging = [row for row in placements if row.get("requires_human_input")]
        committed = int(result.get("committed_count") or 0)
        start = str(result.get("week_start") or "")
        end = str(result.get("week_end") or "")
        if committed:
            opening = f"I scheduled {committed} fully ready production run{'s' if committed != 1 else ''} for {start} through {end}."
        elif placements:
            opening = f"I built a {len(placements)}-run production plan for {start} through {end}."
        else:
            opening = f"I could not place any additional production runs safely for {start} through {end}."
        details: list[str] = []
        for row in placements[:6]:
            state = "scheduled" if row.get("committed") else "needs work location" if row.get("requires_human_input") else "planned"
            details.append(
                f"{row.get('order_number')}: {row.get('scheduled_start_at')} → {row.get('scheduled_end_at')}"
                f" · {row.get('machine_name') or 'no machine'} · {row.get('planned_people', 0)} people · {state}"
            )
        input_text = ""
        if staging:
            input_text = (
                f" {len(staging)} run{'s' if len(staging) != 1 else ''} have inventory available but need staging. "
                "Choose the destination work location before Doobie reserves those lots or prepares the corresponding Metrc package move."
            )
        blocked = int(result.get("blocked_count") or 0)
        blocked_text = f" {blocked} additional run{'s' if blocked != 1 else ''} remain blocked." if blocked else ""
        return " ".join([opening, *details]) + input_text + blocked_text


class ProductionWeekActionPlanner:
    """Deterministic production-week planner using canonical schedule preflight.

    A material_unreserved warning proves material exists but does not prove physical
    staging. Those runs may receive a proposed slot, but this planner never reserves them
    and never commits them until a human selects the destination work location and the
    separate Metrc package_move workflow completes provider readback.
    """

    def __init__(self, access: DatasetAccessContext) -> None:
        if access.engine is None:
            raise ValueError("Production scheduling actions require a live application database.")
        self.access = access
        self.engine = access.engine
        self.schedule = ProductionScheduleService(self.engine)

    def plan(self, *, week_start: str, days: int, max_runs: int, commit: bool, reason: str) -> dict[str, Any]:
        tz = self._facility_timezone()
        now_local = datetime.now(tz)
        start_day = self._resolve_start_day(week_start, tz, today=now_local.date())
        work_days = self._business_days(start_day, days)
        current = self.schedule.list_current(self.access.organization_id, self.access.facility_id)
        scheduled_order_ids = {str(row.get("production_order_id") or "") for row in current}
        orders = self._candidate_orders(scheduled_order_ids)[:max_runs]
        machines = self._machines()
        crew = self._crew(work_days)
        simulated = [self._normalize_placement(row, tz) for row in current]
        placements: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []

        for order in orders:
            try:
                snapshot = self.schedule.erp.order_360(self.access.organization_id, self.access.facility_id, order.id)
            except ValueError as exc:
                blocked.append(self._blocked(order, "order_unavailable", str(exc)))
                continue
            variance = snapshot.get("variance") or {}
            duration = float(variance.get("expected_cycle_hours") or 0.0)
            if duration <= 0:
                blocked.append(self._blocked(order, "missing_cycle_standard", "No BOM standard cycle time is configured."))
                continue
            expected_labor = float(variance.get("expected_labor_hours") or 0.0)
            resource_category = str(variance.get("resource_category") or "").strip()
            expected_machine = float(variance.get("expected_machine_hours") or 0.0)
            machine_candidates = self._machine_candidates(machines, resource_category, expected_machine)
            if resource_category and not machine_candidates:
                blocked.append(self._blocked(order, "machine_unavailable", f"No active machine matches {resource_category}."))
                continue

            preview, slot = self._find_slot(
                order=order,
                duration_hours=duration,
                expected_labor_hours=expected_labor,
                machine_candidates=machine_candidates,
                work_days=work_days,
                crew=crew,
                simulated=simulated,
                reason=reason,
                now_local=now_local,
            )
            if preview is None or slot is None:
                blocked.append(self._blocked(order, "no_safe_slot", "No safe material/capacity/QA slot was found in the requested week."))
                continue

            actionable = [row for row in preview.get("warnings") or [] if row.get("severity") != "info"]
            staging_only = bool(actionable) and all(row.get("code") == MATERIAL_STAGING_WARNING for row in actionable)
            proposed = preview["proposed"]
            row = {
                "order_id": order.id,
                "order_number": order.order_number,
                "product_name": order.product_name,
                "scheduled_start_at": proposed["scheduled_start_at"].isoformat(),
                "scheduled_end_at": proposed["scheduled_end_at"].isoformat(),
                "machine_id": proposed.get("machine_id"),
                "machine_name": proposed.get("machine_name") or "",
                "planned_people": int(proposed.get("planned_people") or 0),
                "preview_key": preview["preview_key"],
                "warnings": list(preview.get("warnings") or []),
                "requires_human_input": staging_only,
                "required_input": "destination_work_location" if staging_only else "",
                "staging_lots": self._staging_lots(snapshot) if staging_only else [],
                "committed": False,
            }
            placements.append(row)
            simulated.append(
                {
                    "start": slot["start"],
                    "end": slot["end"],
                    "machine_id": slot.get("machine_id"),
                    "planned_people": slot["planned_people"],
                }
            )

        commit_errors: list[dict[str, Any]] = []
        if commit:
            for row in placements:
                if row["requires_human_input"]:
                    continue
                try:
                    committed = self.schedule.commit(
                        organization_id=self.access.organization_id,
                        facility_id=self.access.facility_id,
                        order_id=row["order_id"],
                        scheduled_start_at=datetime.fromisoformat(row["scheduled_start_at"]),
                        scheduled_end_at=datetime.fromisoformat(row["scheduled_end_at"]),
                        machine_id=row.get("machine_id") or None,
                        planned_people=int(row["planned_people"]),
                        reason=reason,
                        preview_key=row["preview_key"],
                        accept_warnings=False,
                        actor=self.access.user_id,
                    )
                    row["committed"] = True
                    row["placement_id"] = committed.get("id")
                except ValueError as exc:
                    commit_errors.append(
                        {
                            "order_id": row["order_id"],
                            "order_number": row["order_number"],
                            "message": str(exc),
                        }
                    )

        committed_count = sum(bool(row.get("committed")) for row in placements)
        human_input_count = sum(bool(row.get("requires_human_input")) for row in placements)
        return {
            "action": "production_schedule_week",
            "week_start": start_day.isoformat(),
            "week_end": work_days[-1].isoformat(),
            "days": [value.isoformat() for value in work_days],
            "requested_commit": commit,
            "mutation_performed": committed_count > 0,
            "planned_count": len(placements),
            "committed_count": committed_count,
            "human_input_required_count": human_input_count,
            "blocked_count": len(blocked),
            "placements": placements,
            "blocked": blocked,
            "commit_errors": commit_errors,
            "staging_policy": (
                "Available-but-unreserved material is never reserved by the weekly planner. A human must select the destination work "
                "location first; reservation and the Metrc package_move then run through their own governed workflow and provider readback."
            ),
        }

    def _staging_lots(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        requirements = snapshot.get("requirements") or []
        if not requirements:
            return []
        lots = self.schedule.repo.list_inventory_lots(self.access.organization_id, self.access.facility_id)
        reservations = self.schedule.repo.list_material_reservations(self.access.organization_id, self.access.facility_id)
        balances = {
            lot.id: float(self.schedule.repo.inventory_balance(self.access.organization_id, lot.id))
            for lot in lots
        }
        reserved_by_lot: dict[str, float] = {}
        for reservation in reservations:
            if reservation.status == "reserved":
                reserved_by_lot[reservation.lot_id] = (
                    reserved_by_lot.get(reservation.lot_id, 0.0) + float(reservation.quantity or 0.0)
                )
        rows: list[dict[str, Any]] = []
        for requirement in requirements:
            remaining = float(requirement.get("quantity") or 0.0)
            product_id = str(requirement.get("product_id") or "")
            candidates = [
                lot for lot in lots
                if lot.product_id == product_id and lot.status in {"available", "released"}
            ]
            candidates.sort(key=lambda lot: (lot.received_at is None, str(lot.received_at or ""), str(lot.created_at or "")))
            for lot in candidates:
                available = max(0.0, balances.get(lot.id, 0.0) - reserved_by_lot.get(lot.id, 0.0))
                take = min(remaining, available)
                if take <= 0:
                    continue
                rows.append(
                    {
                        "lot_id": lot.id,
                        "lot_code": lot.lot_code,
                        "package_id": lot.compliance_package_id or lot.lot_code,
                        "product_id": product_id,
                        "product_name": requirement.get("product_name"),
                        "quantity_to_stage": round(take, 6),
                        "unit": requirement.get("unit"),
                        "current_location": lot.location_code,
                    }
                )
                remaining -= take
                if remaining <= 1e-9:
                    break
        return rows

    def _facility_timezone(self) -> ZoneInfo:
        with Session(self.engine) as session:
            facility = session.get(Facility, self.access.facility_id)
        try:
            return ZoneInfo(str(getattr(facility, "timezone_name", "") or "America/New_York"))
        except Exception:
            return ZoneInfo("America/New_York")

    @classmethod
    def _resolve_start_day(cls, raw: str, tz: ZoneInfo, *, today: date | None = None) -> date:
        local_today = today or datetime.now(tz).date()
        normalized = raw.strip().casefold()
        if normalized == "next_week":
            return cls._next_week_start(local_today)
        if raw.strip():
            try:
                candidate = date.fromisoformat(raw.strip())
            except ValueError as exc:
                raise ValueError("week_start must be YYYY-MM-DD.") from exc
            if candidate < local_today:
                candidate = local_today
        else:
            candidate = local_today
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def _next_week_start(today: date) -> date:
        return today + timedelta(days=(7 - today.weekday()))

    @staticmethod
    def _business_days(start: date, count: int) -> list[date]:
        output: list[date] = []
        cursor = start
        while len(output) < count:
            if cursor.weekday() < 5:
                output.append(cursor)
            cursor += timedelta(days=1)
        return output

    def _candidate_orders(self, scheduled_order_ids: set[str]) -> list[ProductionOrder]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ProductionOrder).where(
                    ProductionOrder.organization_id == self.access.organization_id,
                    ProductionOrder.facility_id == self.access.facility_id,
                )
            ).all()
        active = []
        for row in rows:
            status = str(row.status or "").casefold()
            if row.id in scheduled_order_ids or status in CLOSED_STATUSES or status in HELD_STATUSES:
                continue
            active.append(row)
        priority_rank = {"urgent": 0, "high": 1, "normal": 2, "medium": 2, "low": 3}
        return sorted(
            active,
            key=lambda row: (
                priority_rank.get(str(row.priority or "normal").casefold(), 2),
                row.due_at is None,
                str(row.due_at or "9999-12-31"),
                str(row.created_at or ""),
            ),
        )

    def _machines(self) -> list[tuple[FacilityMachine, MachineModel]]:
        with Session(self.engine) as session:
            return list(
                session.execute(
                    select(FacilityMachine, MachineModel)
                    .join(MachineModel, MachineModel.id == FacilityMachine.machine_model_id)
                    .where(
                        FacilityMachine.organization_id == self.access.organization_id,
                        FacilityMachine.facility_id == self.access.facility_id,
                        FacilityMachine.active.is_(True),
                    )
                    .order_by(FacilityMachine.display_name.asc())
                ).all()
            )

    def _crew(self, work_days: list[date]) -> dict[date, dict[str, float]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(CrewAvailability).where(
                    CrewAvailability.organization_id == self.access.organization_id,
                    CrewAvailability.facility_id == self.access.facility_id,
                    CrewAvailability.work_date.in_(work_days),
                )
            ).all()
        output: dict[date, dict[str, float]] = {}
        for row in rows:
            people = float(row.available_people or 0)
            hours = float(row.shift_hours or 0)
            score = people * hours
            current = output.get(row.work_date)
            if current is None or score > current["person_hours"]:
                output[row.work_date] = {
                    "available_people": people,
                    "shift_hours": hours,
                    "person_hours": score,
                }
        return output

    def _machine_candidates(
        self,
        machines: list[tuple[FacilityMachine, MachineModel]],
        resource_category: str,
        expected_machine_hours: float,
    ) -> list[tuple[FacilityMachine | None, MachineModel | None]]:
        if resource_category:
            return [
                pair for pair in machines
                if ProductionScheduleService._category_matches(resource_category, str(pair[1].category or ""))
            ]
        if expected_machine_hours > 0 and machines:
            return list(machines)
        return [(None, None)]

    def _find_slot(
        self,
        *,
        order: ProductionOrder,
        duration_hours: float,
        expected_labor_hours: float,
        machine_candidates: list[tuple[FacilityMachine | None, MachineModel | None]],
        work_days: list[date],
        crew: dict[date, dict[str, float]],
        simulated: list[dict[str, Any]],
        reason: str,
        now_local: datetime,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        tz = self._facility_timezone()
        for work_day in work_days:
            crew_day = crew.get(work_day)
            for machine, _model in machine_candidates:
                planned_people = self._planned_people(expected_labor_hours, duration_hours, machine)
                if planned_people > 0:
                    if not crew_day or crew_day["available_people"] < planned_people:
                        continue
                    shift_hours = max(0.5, float(crew_day["shift_hours"] or 0))
                else:
                    shift_hours = float(crew_day["shift_hours"] if crew_day else 8.0)
                day_start = datetime.combine(work_day, time(hour=8), tzinfo=tz)
                day_end = day_start + timedelta(hours=shift_hours)
                cursor = day_start
                if work_day == now_local.date() and cursor <= now_local:
                    cursor = self._ceil_to_half_hour(now_local)
                duration = timedelta(hours=duration_hours)
                while cursor + duration <= day_end:
                    if cursor <= now_local:
                        cursor += timedelta(minutes=30)
                        continue
                    end = cursor + duration
                    machine_id = machine.id if machine is not None else None
                    if self._machine_conflict(simulated, machine_id, cursor, end):
                        cursor += timedelta(minutes=30)
                        continue
                    if self._crew_conflict(simulated, crew_day, planned_people, cursor, end):
                        cursor += timedelta(minutes=30)
                        continue
                    preview = self.schedule.preview(
                        organization_id=self.access.organization_id,
                        facility_id=self.access.facility_id,
                        order_id=order.id,
                        scheduled_start_at=cursor,
                        scheduled_end_at=end,
                        machine_id=machine_id,
                        planned_people=planned_people,
                        reason=reason,
                    )
                    actionable = [row for row in preview.get("warnings") or [] if row.get("severity") != "info"]
                    safe = not actionable or all(row.get("code") == MATERIAL_STAGING_WARNING for row in actionable)
                    if int(preview.get("blocker_count") or 0) == 0 and safe:
                        return preview, {
                            "start": cursor,
                            "end": end,
                            "machine_id": machine_id,
                            "planned_people": planned_people,
                        }
                    cursor += timedelta(minutes=30)
        return None, None

    @staticmethod
    def _ceil_to_half_hour(value: datetime) -> datetime:
        rounded = value.replace(second=0, microsecond=0)
        if rounded.minute == 0:
            return rounded + timedelta(minutes=30)
        if rounded.minute <= 30:
            return rounded.replace(minute=30) + timedelta(microseconds=1)
        return (rounded + timedelta(hours=1)).replace(minute=0) + timedelta(microseconds=1)

    @staticmethod
    def _planned_people(expected_labor: float, duration: float, machine: FacilityMachine | None) -> int:
        standard_people = math.ceil(expected_labor / duration) if expected_labor > 0 and duration > 0 else 0
        preferred = int(machine.preferred_crew_size or 0) if machine is not None else 0
        return max(standard_people, preferred)

    @staticmethod
    def _normalize_placement(row: dict[str, Any], tz: ZoneInfo) -> dict[str, Any]:
        def local(value: Any) -> datetime:
            dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt.astimezone(tz)

        return {
            "start": local(row["scheduled_start_at"]),
            "end": local(row["scheduled_end_at"]),
            "machine_id": row.get("machine_id"),
            "planned_people": int(row.get("planned_people") or 0),
        }

    @staticmethod
    def _overlap(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
        return start < other_end and end > other_start

    @classmethod
    def _machine_conflict(
        cls,
        placements: list[dict[str, Any]],
        machine_id: str | None,
        start: datetime,
        end: datetime,
    ) -> bool:
        if not machine_id:
            return False
        return any(
            row.get("machine_id") == machine_id and cls._overlap(start, end, row["start"], row["end"])
            for row in placements
        )

    @classmethod
    def _crew_conflict(
        cls,
        placements: list[dict[str, Any]],
        crew_day: dict[str, float] | None,
        planned_people: int,
        start: datetime,
        end: datetime,
    ) -> bool:
        if planned_people <= 0:
            return False
        available = int((crew_day or {}).get("available_people") or 0)
        if available <= 0:
            return True
        concurrent = sum(
            int(row.get("planned_people") or 0)
            for row in placements
            if cls._overlap(start, end, row["start"], row["end"])
        )
        return concurrent + planned_people > available

    @staticmethod
    def _blocked(order: ProductionOrder, code: str, message: str) -> dict[str, Any]:
        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "product_name": order.product_name,
            "code": code,
            "message": message,
        }
