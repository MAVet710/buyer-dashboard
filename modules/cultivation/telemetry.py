"""Deterministic telemetry ingestion and bounded decision-support read models.

No adapter credentials, provider calls, equipment commands, or irrigation writes.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import Facility, new_id
from .models import CultivationRoom
from .telemetry_models import EnvironmentalObservation as Observation, EnvironmentalTarget as Target

METRICS = {
    "temperature": "C", "relative_humidity": "%", "vpd": "kPa", "co2": "ppm",
    "substrate_ec": "mS/cm", "substrate_vwc": "%", "irrigation_volume": "L", "irrigation_event": "count",
}
Metric = Literal["temperature", "relative_humidity", "vpd", "co2", "substrate_ec", "substrate_vwc", "irrigation_volume", "irrigation_event"]


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalize(metric: str, value: float, unit: str) -> tuple[float, str]:
    if not math.isfinite(value):
        raise ValueError("Measurement must be finite.")
    canonical = METRICS[metric]
    if metric == "temperature" and unit == "F":
        value = (value - 32) * 5 / 9
    elif metric == "substrate_ec" and unit == "uS/cm":
        value /= 1000
    elif metric == "irrigation_volume" and unit == "mL":
        value /= 1000
    elif unit != canonical:
        raise ValueError(f"Unsupported unit for {metric}; use {canonical}.")
    if metric == "temperature" and value < -273.15:
        raise ValueError("Temperature is below absolute zero.")
    if metric != "temperature" and value < 0:
        raise ValueError("Measurement must be nonnegative.")
    if metric in {"relative_humidity", "substrate_vwc"} and value > 100:
        raise ValueError("Percentage must be between 0 and 100.")
    if metric == "irrigation_event" and value != 1:
        raise ValueError("An irrigation event has a count of 1.")
    return round(value, 6), canonical


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    source: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=120)
    device_id: str = Field(default="", max_length=120)
    metric: Metric
    value: float = Field(ge=-1e12, le=1e12)
    unit: str = Field(max_length=16)
    quality: Literal["valid", "suspect", "invalid"] = "valid"
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at requires a timezone.")
        if value > datetime.now(timezone.utc):
            raise ValueError("observed_at cannot be in the future.")
        return utc(value)

    @model_validator(mode="after")
    def units(self):
        self.value, self.unit = normalize(self.metric, self.value, self.unit)
        return self


class TargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    metric: Metric
    minimum: float | None = None
    maximum: float | None = None
    stale_minutes: int = Field(default=60, ge=1, le=10080)

    @model_validator(mode="after")
    def ranges(self):
        for value in (self.minimum, self.maximum):
            if value is not None:
                normalize(self.metric, value, METRICS[self.metric])
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum must not exceed maximum.")
        return self


class TelemetryConflict(ValueError):
    pass


def exception_identity(organization_id, facility_id, room_id, row):
    """Versioned, unambiguous evidence identity; independent of polling time/DB UUIDs."""
    evidence = [organization_id, facility_id, room_id, row["metric"], row["source"],
                row["device_id"], sorted(row["states"]), row["observed_at"], row.get("event_id")]
    digest = hashlib.sha256(json.dumps(evidence, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return f"cultivation-telemetry:v1:{digest}"


class TelemetryService:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def room(session, organization_id, facility_id, room_id):
        row = session.scalar(select(CultivationRoom).join(Facility, Facility.id == CultivationRoom.facility_id).where(
            CultivationRoom.id == room_id, CultivationRoom.organization_id == organization_id,
            CultivationRoom.facility_id == facility_id, Facility.organization_id == organization_id))
        if row is None:
            raise LookupError("Room not found in the active facility.")
        return row

    @staticmethod
    def scope(model, organization_id, facility_id, room_id):
        return (model.organization_id == organization_id, model.facility_id == facility_id, model.room_id == room_id)

    def ingest(self, organization_id, facility_id, room_id, readings, *, actor):
        if not 1 <= len(readings) <= 500:
            raise ValueError("Submit between 1 and 500 observations.")
        # Validate all rows before opening the transaction, including direct service callers.
        payloads = [Reading.model_validate(r.model_dump() if isinstance(r, Reading) else r).model_dump() for r in readings]
        key = lambda r: (r["source"], r["event_id"], r["metric"], r["device_id"])
        unique = {}
        for row in payloads:
            previous = unique.setdefault(key(row), row)
            if previous != row:
                raise TelemetryConflict("An event identity has conflicting observations.")
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        with Session(self.engine) as session, session.begin():
            self.room(session, organization_id, facility_id, room_id)
            values = [dict(r, id=new_id(), organization_id=organization_id, facility_id=facility_id, room_id=room_id) for r in unique.values()]
            # Database uniqueness handles concurrent retries. Conflicting payloads roll back the entire batch.
            ids = session.scalars(insert(Observation).values(values).on_conflict_do_nothing(
                index_elements=["organization_id", "facility_id", "room_id", "source", "event_id", "metric", "device_id"]
            ).returning(Observation.id)).all()
            existing = session.scalars(select(Observation).where(*self.scope(Observation, organization_id, facility_id, room_id),
                tuple_(Observation.source, Observation.event_id, Observation.metric, Observation.device_id).in_(list(unique)))).all()
            for row in existing:
                identity = (row.source, row.event_id, row.metric, row.device_id)
                if identity in unique:
                    actual = {name: getattr(row, name) for name in unique[identity]}
                    actual["observed_at"] = utc(actual["observed_at"])
                    if actual != unique[identity]:
                        raise TelemetryConflict("An event identity already exists with different evidence.")
            if ids:
                record_audit_event(session, organization_id=organization_id, facility_id=facility_id,
                    entity_type="cultivation_room", entity_id=room_id, action="environment_ingested", actor=actor,
                    source="api", correlation_id=new_id(), changes={"observation_ids": ids, "sources": sorted({r["source"] for r in payloads})})
            return {"inserted": len(ids), "duplicates": len(payloads) - len(ids)}

    def set_target(self, organization_id, facility_id, room_id, payload, *, actor):
        payload = TargetInput.model_validate(payload.model_dump() if isinstance(payload, TargetInput) else payload)
        with Session(self.engine) as session, session.begin():
            # Serialize configuration changes per room, including concurrent first inserts.
            self.room(session, organization_id, facility_id, room_id)
            session.execute(select(CultivationRoom.id).where(CultivationRoom.id == room_id).with_for_update())
            row = session.scalar(select(Target).where(*self.scope(Target, organization_id, facility_id, room_id), Target.metric == payload.metric))
            before = {name: getattr(row, name) for name in TargetInput.model_fields} if row else None
            if row is None:
                row = Target(organization_id=organization_id, facility_id=facility_id, room_id=room_id)
                session.add(row)
            for name, value in payload.model_dump().items():
                setattr(row, name, value)
            record_audit_event(session, organization_id=organization_id, facility_id=facility_id, entity_type="cultivation_room",
                entity_id=room_id, action="environment_target_set", actor=actor, before=before, after=payload.model_dump())
        return payload.model_dump()

    def snapshot(self, organization_id, facility_id, room_id, *, now=None):
        now = utc(now or datetime.now(timezone.utc))
        with Session(self.engine) as session:
            room = self.room(session, organization_id, facility_id, room_id)
            targets = {r.metric: r for r in session.scalars(select(Target).where(*self.scope(Target, organization_id, facility_id, room_id)))}
            scope = self.scope(Observation, organization_id, facility_id, room_id)
            stream = [Observation.metric, Observation.source, Observation.device_id]
            ranked = select(Observation, func.row_number().over(partition_by=stream,
                order_by=[Observation.observed_at.desc(), Observation.event_id.desc()]).label("rank")).where(*scope, Observation.observed_at <= now).subquery()
            latest = session.execute(select(ranked).where(ranked.c.rank == 1).order_by(ranked.c.metric, ranked.c.source, ranked.c.device_id).limit(201)).mappings().all()
            # Aggregate in SQL; never hydrate raw history or fan out per sensor.
            stats = session.execute(select(*stream, func.count().label("count"), func.min(Observation.value).label("min"),
                func.max(Observation.value).label("max"), func.avg(Observation.value).label("average"), func.sum(Observation.value).label("total"))
                .where(*scope, tuple_(*stream).in_([(r["metric"], r["source"], r["device_id"]) for r in latest[:200]]),
                       Observation.quality == "valid", Observation.observed_at > now - timedelta(hours=24), Observation.observed_at <= now)
                .group_by(*stream).order_by(*stream).limit(201)).mappings().all()
            stats_map = {}
            for stat in stats:
                if stat["metric"].startswith("irrigation_"):
                    trend = {"kind": "event_count" if stat["metric"] == "irrigation_event" else "volume_total",
                             "count": stat["count"], "total": stat["total"]}
                else:
                    trend = {"kind": "continuous", **{key: stat[key] for key in ("count", "min", "max", "average")}}
                stats_map[(stat["metric"], stat["source"], stat["device_id"])] = trend
            rows = []
            for row in latest[:200]:
                metric = row["metric"]
                target = targets.get(metric)
                observed = utc(row["observed_at"])
                age = max(0, (now - observed).total_seconds() / 60)
                stale_after = target.stale_minutes if target else (None if metric.startswith("irrigation_") else 60)
                states = []
                if stale_after is not None and age > stale_after:
                    states.append("stale")
                if row["quality"] != "valid":
                    states.append(row["quality"])
                elif target and ((target.minimum is not None and row["value"] < target.minimum) or (target.maximum is not None and row["value"] > target.maximum)):
                    states.append("out_of_range")
                rows.append({"metric": metric, "source": row["source"], "device_id": row["device_id"], "event_id": row["event_id"], "value": row["value"],
                    "unit": row["unit"], "quality": row["quality"], "observed_at": observed.isoformat(), "states": states or ["current"],
                    "trend_24h": stats_map.get((metric, row["source"], row["device_id"])), "target": self.target_payload(target), "stale_minutes": stale_after})
            present = {r["metric"] for r in latest}
            if len(latest) <= 200:
                for metric, unit in METRICS.items():
                    if metric not in present:
                        rows.append({"metric": metric, "unit": unit, "value": None, "source": "", "device_id": "", "quality": None,
                            "observed_at": None, "states": ["missing"], "trend_24h": None, "target": self.target_payload(targets.get(metric)),
                            "stale_minutes": targets[metric].stale_minutes if metric in targets else None})
            exceptions = [r for r in rows if r["states"] != ["current"] and (r["states"] != ["missing"] or r["target"])]
            for row in exceptions:
                row["exception_id"] = exception_identity(organization_id, facility_id, room_id, row)
            return {"room_id": room.id, "room_code": room.room_code, "as_of": now.isoformat(), "readings": rows,
                "exceptions": exceptions, "truncated": len(latest) > 200, "decision_support_only": True}

    def prepare_work_item(self, organization_id, facility_id, room_id, exception_id, *, actor, now=None):
        """Resolve an explicitly selected exception to a draft, never create a task.

        Final-rebase API must authorize cultivation AND Work creation, then pass this
        server-derived evidence to the canonical Work service with atomic deduplication.
        A client-supplied snapshot is never accepted as authoritative evidence.
        """
        if not actor or not actor.strip():
            raise ValueError("An authenticated operator is required.")
        snapshot = self.snapshot(organization_id, facility_id, room_id, now=now)
        row = next((r for r in snapshot["exceptions"] if r["exception_id"] == exception_id), None)
        if row is None:
            raise TelemetryConflict("Exception is no longer current or is outside the visible summary; refresh before creating Work.")
        return {"organization_id": organization_id, "facility_id": facility_id,
                "origin_type": "cultivation_telemetry_exception", "origin_id": exception_id,
                "room_id": room_id, "requested_by": actor,
                "title": f"Review {snapshot['room_code']} {row['metric']}: {', '.join(row['states'])}",
                "evidence": dict(row), "evidence_as_of": snapshot["as_of"], "decision_support_only": True}

    @staticmethod
    def target_payload(target):
        return {"minimum": target.minimum, "maximum": target.maximum, "stale_minutes": target.stale_minutes} if target else None
