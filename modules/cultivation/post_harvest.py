from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Engine, ForeignKey, Index, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from modules.coman.models import Base, TimestampMixin, new_id, utc_now
from modules.operational_moats.models import CultivationHarvest


POST_HARVEST_STAGES = (
    "harvested",
    "drying",
    "bucking",
    "trimming",
    "curing",
    "testing_hold",
    "ready",
)
POST_HARVEST_WEIGHT_TYPES = (
    "wip",
    "finished_flower",
    "trim",
    "biomass",
    "waste",
)
_STAGE_ORDER = {value: index for index, value in enumerate(POST_HARVEST_STAGES)}


class CultivationPostHarvestBatch(TimestampMixin, Base):
    __tablename__ = "cultivation_post_harvest_batches"
    __table_args__ = (
        UniqueConstraint("harvest_id", name="uq_cultivation_post_harvest_harvest"),
        CheckConstraint(
            "stage in ('harvested','drying','bucking','trimming','curing','testing_hold','ready')",
            name="ck_cultivation_post_harvest_stage",
        ),
        Index("ix_cultivation_post_harvest_facility_stage", "facility_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    harvest_id: Mapped[str] = mapped_column(ForeignKey("cultivation_harvests.id", ondelete="CASCADE"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="harvested")
    location_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CultivationPostHarvestWeightEvent(Base):
    __tablename__ = "cultivation_post_harvest_weight_events"
    __table_args__ = (
        CheckConstraint(
            "weight_type in ('wip','finished_flower','trim','biomass','waste')",
            name="ck_cultivation_post_harvest_weight_type",
        ),
        CheckConstraint("quantity_g >= 0", name="ck_cultivation_post_harvest_weight_nonnegative"),
        Index("ix_cultivation_post_harvest_weight_batch_time", "batch_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("cultivation_post_harvest_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    weight_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_g: Mapped[float] = mapped_column(nullable=False)
    container_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    correction_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CultivationPostHarvestEvent(Base):
    __tablename__ = "cultivation_post_harvest_events"
    __table_args__ = (Index("ix_cultivation_post_harvest_event_batch_time", "batch_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("cultivation_post_harvest_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    to_value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PostHarvestService:
    """Facility-scoped post-harvest work queue with append-only weight truth.

    This is an operational workflow only. It does not issue Metrc mutations and it
    does not create inventory lots. Harvest -> inventory remains owned by the
    guarded harvest allocation workflow.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def sync_open_harvests(self, organization_id: str, facility_id: str, *, actor: str) -> list[dict]:
        """Idempotently materialize post-harvest work for active/drying harvests."""
        with self.sessions.begin() as session:
            harvests = list(
                session.scalars(
                    select(CultivationHarvest).where(
                        CultivationHarvest.organization_id == organization_id,
                        CultivationHarvest.facility_id == facility_id,
                        CultivationHarvest.status.in_(("active", "drying")),
                    )
                )
            )
            harvest_ids = [row.id for row in harvests]
            existing = {
                row.harvest_id: row
                for row in session.scalars(
                    select(CultivationPostHarvestBatch).where(
                        CultivationPostHarvestBatch.organization_id == organization_id,
                        CultivationPostHarvestBatch.facility_id == facility_id,
                        CultivationPostHarvestBatch.harvest_id.in_(harvest_ids or ["__none__"]),
                    )
                )
            }
            for harvest in harvests:
                target = "drying" if harvest.status == "drying" else "harvested"
                batch = existing.get(harvest.id)
                if batch is None:
                    batch = CultivationPostHarvestBatch(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        harvest_id=harvest.id,
                        stage=target,
                        created_by=actor,
                    )
                    session.add(batch)
                    session.flush()
                    session.add(
                        CultivationPostHarvestEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            batch_id=batch.id,
                            event_type="created",
                            to_value=target,
                            note="Post-harvest work created from the open cultivation harvest.",
                            actor=actor,
                        )
                    )
                elif batch.stage == "harvested" and target == "drying":
                    batch.stage = "drying"
                    session.add(
                        CultivationPostHarvestEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            batch_id=batch.id,
                            event_type="stage_changed",
                            from_value="harvested",
                            to_value="drying",
                            note="Cultivation harvest entered drying.",
                            actor=actor,
                        )
                    )
        return self.list_batches(organization_id, facility_id)

    def list_batches(self, organization_id: str, facility_id: str) -> list[dict]:
        with self.sessions() as session:
            batches = list(
                session.scalars(
                    select(CultivationPostHarvestBatch).where(
                        CultivationPostHarvestBatch.organization_id == organization_id,
                        CultivationPostHarvestBatch.facility_id == facility_id,
                    ).order_by(CultivationPostHarvestBatch.updated_at.desc(), CultivationPostHarvestBatch.id)
                )
            )
            return self._payloads(session, batches)

    def detail(self, organization_id: str, facility_id: str, batch_id: str) -> dict:
        with self.sessions() as session:
            batch = self._require_batch(session, organization_id, facility_id, batch_id)
            return self._payloads(session, [batch], include_history=True)[0]

    def transition(
        self,
        organization_id: str,
        facility_id: str,
        batch_id: str,
        *,
        stage: str,
        actor: str,
        location_code: str = "",
        notes: str = "",
    ) -> dict:
        target = stage.strip().casefold()
        if target not in _STAGE_ORDER:
            raise ValueError("Unsupported post-harvest stage.")
        with self.sessions.begin() as session:
            batch = self._require_batch(session, organization_id, facility_id, batch_id)
            current = batch.stage
            if _STAGE_ORDER[target] < _STAGE_ORDER[current]:
                raise ValueError("Post-harvest stages are forward-only. Reopening a locked stage requires a governed correction workflow.")
            if target == "ready" and current != "ready":
                latest = self._latest_weights(session, batch.id)
                output_total = sum(latest.get(key, 0.0) for key in ("finished_flower", "trim", "biomass", "waste"))
                if output_total <= 0:
                    raise ValueError("Record physical post-harvest output weights before marking this batch ready.")
            if target != current:
                batch.stage = target
                if target == "ready":
                    batch.completed_at = batch.completed_at or utc_now()
                session.add(
                    CultivationPostHarvestEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        batch_id=batch.id,
                        event_type="stage_changed",
                        from_value=current,
                        to_value=target,
                        note=notes.strip(),
                        actor=actor,
                    )
                )
            if location_code.strip() and location_code.strip() != batch.location_code:
                prior_location = batch.location_code
                batch.location_code = location_code.strip()
                session.add(
                    CultivationPostHarvestEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        batch_id=batch.id,
                        event_type="location_changed",
                        from_value=prior_location,
                        to_value=batch.location_code,
                        note=notes.strip(),
                        actor=actor,
                    )
                )
            if notes.strip():
                batch.notes = notes.strip()
        return self.detail(organization_id, facility_id, batch_id)

    def record_weights(
        self,
        organization_id: str,
        facility_id: str,
        batch_id: str,
        *,
        measurements: list[dict],
        actor: str,
        correction_reason: str = "",
        allow_locked_correction: bool = False,
    ) -> dict:
        if not measurements:
            raise ValueError("Enter at least one post-harvest weight.")
        reason = correction_reason.strip()
        with self.sessions.begin() as session:
            batch = self._require_batch(session, organization_id, facility_id, batch_id)
            if batch.stage == "ready" and not allow_locked_correction:
                raise ValueError("This post-harvest batch is locked. A lead or manager must record a governed correction.")
            if batch.stage == "ready" and not reason:
                raise ValueError("A correction reason is required when changing weights after the batch is ready.")
            for measurement in measurements:
                kind = str(measurement.get("weight_type") or "").strip().casefold()
                if kind not in POST_HARVEST_WEIGHT_TYPES:
                    raise ValueError("Unsupported post-harvest weight type.")
                try:
                    quantity = float(measurement.get("quantity_g"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("Post-harvest weights must be numeric grams.") from exc
                if quantity < 0:
                    raise ValueError("Post-harvest weights cannot be negative.")
                session.add(
                    CultivationPostHarvestWeightEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        batch_id=batch.id,
                        stage=batch.stage,
                        weight_type=kind,
                        quantity_g=quantity,
                        container_code=str(measurement.get("container_code") or "").strip(),
                        note=str(measurement.get("note") or "").strip(),
                        correction_reason=reason,
                        actor=actor,
                    )
                )
            session.add(
                CultivationPostHarvestEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    batch_id=batch.id,
                    event_type="weights_recorded" if not reason else "weights_corrected",
                    to_value=",".join(str(row.get("weight_type") or "") for row in measurements),
                    note=reason,
                    actor=actor,
                )
            )
        return self.detail(organization_id, facility_id, batch_id)

    @staticmethod
    def _require_batch(session, organization_id: str, facility_id: str, batch_id: str) -> CultivationPostHarvestBatch:
        batch = session.get(CultivationPostHarvestBatch, batch_id)
        if not batch or batch.organization_id != organization_id or batch.facility_id != facility_id:
            raise ValueError("Post-harvest batch was not found in the active facility.")
        return batch

    @staticmethod
    def _latest_weights(session, batch_id: str) -> dict[str, float]:
        rows = list(
            session.scalars(
                select(CultivationPostHarvestWeightEvent)
                .where(CultivationPostHarvestWeightEvent.batch_id == batch_id)
                .order_by(CultivationPostHarvestWeightEvent.occurred_at, CultivationPostHarvestWeightEvent.id)
            )
        )
        latest: dict[str, float] = {}
        for row in rows:
            latest[row.weight_type] = float(row.quantity_g or 0)
        return latest

    def _payloads(self, session, batches: list[CultivationPostHarvestBatch], *, include_history: bool = False) -> list[dict]:
        if not batches:
            return []
        batch_ids = [row.id for row in batches]
        harvest_ids = [row.harvest_id for row in batches]
        harvests = {
            row.id: row
            for row in session.scalars(select(CultivationHarvest).where(CultivationHarvest.id.in_(harvest_ids)))
        }
        weights_by_batch: dict[str, list[CultivationPostHarvestWeightEvent]] = defaultdict(list)
        for row in session.scalars(
            select(CultivationPostHarvestWeightEvent)
            .where(CultivationPostHarvestWeightEvent.batch_id.in_(batch_ids))
            .order_by(CultivationPostHarvestWeightEvent.occurred_at, CultivationPostHarvestWeightEvent.id)
        ):
            weights_by_batch[row.batch_id].append(row)
        events_by_batch: dict[str, list[CultivationPostHarvestEvent]] = defaultdict(list)
        if include_history:
            for row in session.scalars(
                select(CultivationPostHarvestEvent)
                .where(CultivationPostHarvestEvent.batch_id.in_(batch_ids))
                .order_by(CultivationPostHarvestEvent.occurred_at, CultivationPostHarvestEvent.id)
            ):
                events_by_batch[row.batch_id].append(row)

        payloads: list[dict] = []
        for batch in batches:
            harvest = harvests.get(batch.harvest_id)
            weight_rows = weights_by_batch.get(batch.id, [])
            latest: dict[str, float] = {}
            for row in weight_rows:
                latest[row.weight_type] = float(row.quantity_g or 0)
            wet = float(getattr(harvest, "wet_weight_g", 0) or 0)
            dry = float(getattr(harvest, "dry_weight_g", 0) or 0)
            starting = dry if batch.stage in {"bucking", "trimming", "curing", "testing_hold", "ready"} and dry > 0 else wet
            accounted = sum(latest.get(key, 0.0) for key in ("finished_flower", "trim", "biomass", "waste"))
            explicit_wip = latest.get("wip")
            remaining = explicit_wip if explicit_wip is not None else max(0.0, (dry if dry > 0 else starting) - accounted)
            attention = ""
            if batch.stage in {"harvested", "drying"} and wet <= 0:
                attention = "Record the harvested wet weight."
            elif batch.stage in {"bucking", "trimming", "curing", "testing_hold", "ready"} and dry <= 0:
                attention = "Record the dry weight before reconciling post-harvest output."
            elif dry > 0 and accounted - dry > 1e-6:
                attention = f"Recorded outputs exceed dry weight by {accounted - dry:,.2f} g."

            payload = {
                "id": batch.id,
                "harvest_id": batch.harvest_id,
                "harvest_code": getattr(harvest, "harvest_code", ""),
                "strain_name": getattr(harvest, "strain", ""),
                "source_room": getattr(harvest, "room", ""),
                "harvest_status": getattr(harvest, "status", ""),
                "stage": batch.stage,
                "location_code": batch.location_code,
                "notes": batch.notes,
                "started_at": batch.started_at.isoformat() if batch.started_at else None,
                "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                "wet_weight_g": wet,
                "dry_weight_g": dry,
                "starting_weight_g": starting,
                "current_weights": {key: round(latest.get(key, 0.0), 4) for key in POST_HARVEST_WEIGHT_TYPES},
                "accounted_output_g": round(accounted, 4),
                "remaining_wip_g": round(float(remaining or 0), 4),
                "weight_event_count": len(weight_rows),
                "needs_attention": bool(attention),
                "attention_reason": attention,
            }
            if include_history:
                payload["weight_history"] = [
                    {
                        "id": row.id,
                        "stage": row.stage,
                        "weight_type": row.weight_type,
                        "quantity_g": float(row.quantity_g or 0),
                        "container_code": row.container_code,
                        "note": row.note,
                        "correction_reason": row.correction_reason,
                        "actor": row.actor,
                        "occurred_at": row.occurred_at.isoformat(),
                    }
                    for row in reversed(weight_rows[-50:])
                ]
                payload["audit_history"] = [
                    {
                        "id": row.id,
                        "event_type": row.event_type,
                        "from_value": row.from_value,
                        "to_value": row.to_value,
                        "note": row.note,
                        "actor": row.actor,
                        "occurred_at": row.occurred_at.isoformat(),
                    }
                    for row in reversed(events_by_batch.get(batch.id, [])[-50:])
                ]
            payloads.append(payload)
        return payloads
