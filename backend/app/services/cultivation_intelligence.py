from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant, CultivationRoom
from modules.operational_moats.models import CultivationHarvest


PIPELINE_PHASE_LEAD_DAYS = {"vegetative": 0, "seedling": 14, "clone": 28}
FORECAST_DAYS = 84


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


class CultivationIntelligenceService:
    """Deterministic cultivation forecast built from local operational facts.

    Finished Harvest 360 actuals establish dry-yield-per-plant baselines. Current
    flowering estimates project future dry supply. Configured flowering-room
    turnover then consumes the clone/seedling/vegetative pipeline in date order
    so nursery shortages are not hidden by double-counting the same plants.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def snapshot(self, organization_id: str, facility_id: str, *, as_of: date | None = None) -> dict[str, Any]:
        today = as_of or date.today()
        horizon = today + timedelta(days=FORECAST_DAYS)
        with Session(self.engine) as session:
            plants = list(session.scalars(select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
            )))
            rooms = list(session.scalars(select(CultivationRoom).where(
                CultivationRoom.organization_id == organization_id,
                CultivationRoom.facility_id == facility_id,
                CultivationRoom.active.is_(True),
            )))
            harvests = list(session.scalars(select(CultivationHarvest).where(
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            )))
            links = list(session.scalars(select(CultivationHarvestPlant).where(
                CultivationHarvestPlant.organization_id == organization_id,
                CultivationHarvestPlant.facility_id == facility_id,
            )))

        link_counts = Counter(row.harvest_id for row in links)
        yield_model = self._yield_model(harvests, link_counts)
        supply = self._supply_forecast(plants, yield_model, today=today, horizon=horizon)
        nursery = self._nursery_forecast(plants, rooms, today=today, horizon=horizon)
        shortages = [row for row in nursery if row["shortage_plants"] > 0]
        projected_dry = sum(float(row.get("estimated_dry_weight") or 0) for row in supply)
        rooms_at_risk = len({row["room_code"] for row in shortages})
        return {
            "as_of": today.isoformat(),
            "horizon_end": horizon.isoformat(),
            "forecast_days": FORECAST_DAYS,
            "metrics": {
                "historical_harvest_samples": yield_model["sample_count"],
                "projected_dry_weight": round(projected_dry, 2),
                "projected_dry_unit": "g",
                "nursery_shortage_plants": sum(row["shortage_plants"] for row in shortages),
                "rooms_at_pipeline_risk": rooms_at_risk,
            },
            "yield_model": yield_model,
            "supply_forecast": supply,
            "nursery_forecast": nursery,
            "exceptions": shortages,
            "production_handoff": [
                {
                    "week": row["week"],
                    "strain": row["strain"],
                    "forecast_dry_weight": row["estimated_dry_weight"],
                    "unit": "g",
                    "confidence": row["confidence"],
                    "source": "cultivation_forecast",
                }
                for row in supply
            ],
            "policy": {
                "deterministic_only": True,
                "provider_write": False,
                "creates_purchase_orders": False,
                "message": "Cultivation forecasts are decision support. They do not move plants, create production runs, create POs, or submit regulatory changes.",
            },
        }

    @staticmethod
    def _yield_model(harvests: list[CultivationHarvest], link_counts: Counter) -> dict[str, Any]:
        by_strain: dict[str, list[float]] = defaultdict(list)
        all_samples: list[float] = []
        for harvest in harvests:
            count = int(link_counts.get(harvest.id, int(harvest.plant_count or 0)))
            dry = float(harvest.dry_weight_g or 0)
            if harvest.status != "completed" or count <= 0 or dry <= 0:
                continue
            dry_per_plant = dry / count
            all_samples.append(dry_per_plant)
            strain = str(harvest.strain or "").strip()
            if strain and strain.casefold() != "mixed":
                by_strain[strain.casefold()].append(dry_per_plant)
        overall = mean(all_samples) if all_samples else None
        strains = {
            key: {"sample_count": len(values), "dry_weight_per_plant": round(mean(values), 2)}
            for key, values in sorted(by_strain.items())
        }
        return {
            "sample_count": len(all_samples),
            "overall_dry_weight_per_plant": round(overall, 2) if overall is not None else None,
            "unit": "g",
            "strains": strains,
            "method": "completed Harvest 360 dry weight divided by assigned plant count",
        }

    @staticmethod
    def _supply_forecast(plants: list[CultivationPlant], yield_model: dict[str, Any], *, today: date, horizon: date) -> list[dict[str, Any]]:
        grouped: dict[tuple[date, str], dict[str, Any]] = {}
        strain_model = yield_model.get("strains") or {}
        overall = yield_model.get("overall_dry_weight_per_plant")
        for plant in plants:
            if plant.phase != "flowering" or not plant.estimated_harvest_date:
                continue
            if plant.estimated_harvest_date < today or plant.estimated_harvest_date > horizon:
                continue
            week = _monday(plant.estimated_harvest_date)
            strain = str(plant.strain_name or "Unknown").strip() or "Unknown"
            key = (week, strain)
            row = grouped.setdefault(key, {
                "week": week.isoformat(), "strain": strain, "plants": 0,
                "estimated_dry_weight": 0.0, "plants_without_yield_baseline": 0,
                "confidence": "low",
            })
            row["plants"] += 1
            specific = strain_model.get(strain.casefold())
            baseline = specific.get("dry_weight_per_plant") if isinstance(specific, dict) else overall
            if baseline is None:
                row["plants_without_yield_baseline"] += 1
            else:
                row["estimated_dry_weight"] += float(baseline)
                row["confidence"] = "high" if isinstance(specific, dict) and int(specific.get("sample_count") or 0) >= 3 else "medium"
        output = list(grouped.values())
        for row in output:
            row["estimated_dry_weight"] = round(float(row["estimated_dry_weight"]), 2)
            if row["plants_without_yield_baseline"]:
                row["confidence"] = "low"
        return sorted(output, key=lambda row: (row["week"], row["strain"].casefold()))

    @classmethod
    def _nursery_forecast(cls, plants: list[CultivationPlant], rooms: list[CultivationRoom], *, today: date, horizon: date) -> list[dict[str, Any]]:
        pipeline: dict[str, Counter] = defaultdict(Counter)
        flowering_by_room: dict[str, list[CultivationPlant]] = defaultdict(list)
        for plant in plants:
            strain = str(plant.strain_name or "Unknown").strip() or "Unknown"
            if plant.phase in PIPELINE_PHASE_LEAD_DAYS:
                pipeline[strain.casefold()][plant.phase] += 1
            elif plant.phase == "flowering":
                flowering_by_room[plant.room_code].append(plant)

        events: list[dict[str, Any]] = []
        for room in rooms:
            if room.phase and room.phase != "flowering":
                continue
            current = flowering_by_room.get(room.room_code, [])
            strain_counts = Counter((str(plant.strain_name or "Unknown").strip() or "Unknown") for plant in current)
            dominant = strain_counts.most_common(1)[0][0] if strain_counts else "Unknown"
            estimated_dates = [plant.estimated_harvest_date for plant in current if plant.estimated_harvest_date and plant.estimated_harvest_date >= today]
            first_turn = min(estimated_dates) if estimated_dates else today + timedelta(days=max(1, int(room.target_cycle_days or 56)))
            capacity = int(room.plant_capacity or 0) or len(current)
            if capacity <= 0:
                continue
            cycle = max(1, int(room.target_cycle_days or 56))
            turn = first_turn
            while turn <= horizon:
                events.append({
                    "turnover_date": turn,
                    "room_code": room.room_code,
                    "room_name": room.display_name or room.room_code,
                    "strain": dominant,
                    "required_transplants": capacity,
                    "cycle_days": cycle,
                })
                turn += timedelta(days=cycle)

        remaining = {strain: Counter(counts) for strain, counts in pipeline.items()}
        rows: list[dict[str, Any]] = []
        for event in sorted(events, key=lambda row: (row["turnover_date"], row["room_code"])):
            days_away = max(0, (event["turnover_date"] - today).days)
            strain_key = event["strain"].casefold()
            pool = remaining.setdefault(strain_key, Counter())
            eligible = {phase: int(pool.get(phase, 0)) for phase, lead in PIPELINE_PHASE_LEAD_DAYS.items() if days_away >= lead}
            needed = int(event["required_transplants"])
            allocated = 0
            allocation: dict[str, int] = {}
            for phase in ("vegetative", "seedling", "clone"):
                available = int(eligible.get(phase, 0))
                take = min(max(0, needed - allocated), available)
                if take:
                    allocation[phase] = take
                    pool[phase] -= take
                    allocated += take
            shortage = max(0, needed - allocated)
            rows.append({
                "turnover_date": event["turnover_date"].isoformat(),
                "week": _monday(event["turnover_date"]).isoformat(),
                "room_code": event["room_code"],
                "room_name": event["room_name"],
                "strain": event["strain"],
                "required_transplants": needed,
                "pipeline_available_at_turnover": sum(eligible.values()),
                "allocated_from_pipeline": allocated,
                "allocation": allocation,
                "shortage_plants": shortage,
                "status": "shortage" if shortage else "covered",
                "days_away": days_away,
            })
        return rows
