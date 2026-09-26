"""Bounded dispatch planning and delivery evidence, with no fulfillment writes."""
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import CommercialOrder, TradePartner, utc_now
from modules.commercial_finance.models import CommercialShipment
from .models import DispatchRun, DispatchStop
from .schemas import RunInput, StopInput, Outcome

TRANSITIONS = {
    "planned": ["loaded"], "loaded": ["en_route"], "en_route": ["arrived"],
    "arrived": ["delivered", "partial", "rejected"],
    "partial": ["returned"], "rejected": ["returned"], "delivered": [], "returned": [],
}
TERMINAL = {"delivered", "partial", "rejected", "returned"}


def values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def run_status(stops):
    states = {stop.status for stop in stops}
    if not states or states == {"planned"}:
        return "planned"
    if states <= TERMINAL:
        return next(iter(states)) if len(states) == 1 else "partial"
    for state in ("arrived", "en_route", "loaded"):
        if state in states:
            return state
    return "en_route"


def distance(a, b):
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin(radians(b.longitude-a.longitude)/2)**2
    return 2 * asin(sqrt(min(1, max(0, h))))


class LogisticsService:
    def __init__(self, engine, organization_id, facility_id, actor):
        self.engine, self.org, self.facility, self.actor = engine, organization_id, facility_id, actor

    def _run(self, session, run_id, version=None, *, lock=False):
        query = select(DispatchRun).where(DispatchRun.id == run_id, DispatchRun.organization_id == self.org, DispatchRun.facility_id == self.facility)
        if version is not None:
            query = query.with_for_update()
        run = session.scalar(query)
        if run is None:
            raise LookupError("Dispatch run was not found in the active facility.")
        if version is not None and run.version != version:
            raise ValueError("Dispatch changed. Refresh before saving again.")
        return run

    @staticmethod
    def _stops(session, run):
        return list(session.scalars(select(DispatchStop).where(DispatchStop.run_id == run.id).order_by(DispatchStop.sequence, DispatchStop.id)))

    def _audit(self, session, run, action, before, after):
        audit_correlation = "dispatch" + ":" + run.id
        record_audit_event(session, organization_id=self.org, facility_id=self.facility, entity_type="dispatch_run", entity_id=run.id, action=action, actor=self.actor, source="api", correlation_id=audit_correlation, before=before, after=after)

    def create(self, payload: RunInput):
        with Session(self.engine) as session, session.begin():
            run = DispatchRun(organization_id=self.org, facility_id=self.facility, created_by=self.actor, **payload.model_dump())
            session.add(run)
            session.flush()
            self._audit(session, run, "dispatch_created", {}, values(run))
            return values(run)

    def board(self, service_date, offset=0):
        with Session(self.engine) as session:
            runs = list(session.scalars(select(DispatchRun).where(DispatchRun.organization_id == self.org, DispatchRun.facility_id == self.facility, DispatchRun.service_date == service_date).order_by(DispatchRun.created_at, DispatchRun.id).offset(offset).limit(101)))
            rows = session.execute(select(DispatchStop.run_id, DispatchStop.status).where(DispatchStop.run_id.in_([run.id for run in runs[:100]]))).all() if runs else []
            grouped = {}
            for row in rows:
                grouped.setdefault(row.run_id, []).append(row)
            return {"runs": [{**values(run), "status": run_status(grouped.get(run.id, [])), "stop_count": len(grouped.get(run.id, []))} for run in runs[:100]], "has_more": len(runs) > 100}

    def candidates(self, offset=0):
        with Session(self.engine) as session:
            rows = session.execute(select(CommercialShipment, CommercialOrder, TradePartner).join(CommercialOrder, CommercialOrder.id == CommercialShipment.commercial_order_id).join(TradePartner, TradePartner.id == CommercialOrder.partner_id).where(
                CommercialShipment.organization_id == self.org, CommercialShipment.facility_id == self.facility,
                CommercialOrder.organization_id == self.org, CommercialOrder.facility_id == self.facility,
                TradePartner.organization_id == self.org, CommercialOrder.order_type == "sales", CommercialOrder.status != "cancelled",
                CommercialShipment.status.not_in(["cancelled", "delivered"]),
                ~select(DispatchStop.id).where(DispatchStop.shipment_id == CommercialShipment.id).exists(),
            ).order_by(CommercialShipment.created_at, CommercialShipment.id).offset(offset).limit(201)).all()
            return {"shipments": [{"id": s.id, "shipment_number": s.shipment_number, "manifest_reference": s.manifest_reference, "order_id": o.id, "order_number": o.order_number, "partner_id": p.id, "partner_name": p.name, "contact_snapshot": " / ".join(filter(None, [p.contact_name, p.contact_phone, p.contact_email]))} for s, o, p in rows[:200]], "has_more": len(rows) > 200}

    def detail(self, run_id):
        with Session(self.engine) as session:
            run = self._run(session, run_id)
            rows = session.execute(select(DispatchStop, CommercialShipment, CommercialOrder).join(CommercialShipment, CommercialShipment.id == DispatchStop.shipment_id).join(CommercialOrder, CommercialOrder.id == CommercialShipment.commercial_order_id).where(DispatchStop.run_id == run.id, CommercialShipment.organization_id == self.org, CommercialShipment.facility_id == self.facility, CommercialOrder.organization_id == self.org, CommercialOrder.facility_id == self.facility).order_by(DispatchStop.sequence, DispatchStop.id)).all()
            return {**values(run), "status": run_status([s for s, _, _ in rows]), "stops": [{**values(s), "shipment_number": shipment.shipment_number, "manifest_reference": shipment.manifest_reference, "commercial_order_id": order.id, "order_number": order.order_number, "partner_id": order.partner_id, "allowed_statuses": TRANSITIONS[s.status]} for s, shipment, order in rows]}

    def create_reconciliation_work(self, run_id, stop_id, version, work):
        """Explicit Work handoff; the run lock serializes creation and stop changes."""
        from backend.app.schemas.work import WorkCreate
        from backend.app.services.work import require_write
        from backend.app.permissions import require_permission
        context = work.context
        if (context.organization_id, context.facility_id, context.user_id) != (self.org, self.facility, self.actor):
            raise ValueError("Work context must match the active dispatch scope.")
        require_write(context)
        require_permission(context, self.engine, "wholesale.manage_dispatch")
        require_permission(context, self.engine, "work.create")
        with Session(self.engine) as session, session.begin():
            run = self._run(session, run_id, lock=True)
            stop = session.scalar(select(DispatchStop).where(DispatchStop.run_id == run.id, DispatchStop.id == stop_id).with_for_update())
            if stop is None:
                raise LookupError("Stop was not found in this dispatch run.")
            if stop.status not in {"partial", "rejected", "returned"}:
                raise ValueError("Reconciliation work requires an exception stop.")
            if stop.work_item_id:
                from modules.coman.models import WorkItem
                item = session.scalar(select(WorkItem).where(WorkItem.id == stop.work_item_id,
                    WorkItem.organization_id == self.org, WorkItem.facility_id == self.facility,
                    WorkItem.entity_type == "wholesale_dispatch_stop", WorkItem.entity_id == stop.id))
                if item is None:
                    raise ValueError("Linked Work is outside this stop's scope. Refresh and reconcile the link.")
                return {"work_item_id": item.id, "version": run.version, "message": "Reconciliation work already exists."}
            if run.version != version:
                raise ValueError("Dispatch changed. Refresh before saving again.")
            before = values(stop)
            item = work.create(WorkCreate(title=f"Reconcile {stop.status} dispatch stop",
                description=stop.outcome_notes, workspace="Wholesale", entity_type="wholesale_dispatch_stop",
                entity_id=stop.id, route=f"/wholesale?tab=fulfillment&dispatch={run.id}&stop={stop.id}"), session=session, correlation_id=f"dispatch:{run.id}")
            stop.work_item_id = item["id"]
            run.version += 1
            session.flush()
            self._audit(session, run, "dispatch_reconciliation_work_created", before, values(stop))
            return {"work_item_id": item["id"], "version": run.version, "message": "Reconciliation work created."}

    def mutate(self, run_id, version, action, payload=None, stop_id=None):
        with Session(self.engine) as session, session.begin():
            run = self._run(session, run_id, version)
            stops = self._stops(session, run)
            before = {"run": values(run), "stops": [values(s) for s in stops]}
            stop = next((s for s in stops if s.id == stop_id), None)
            if stop_id and not stop:
                raise LookupError("Stop was not found in this dispatch run.")
            message = "Saved."
            if action in {"add", "reorder", "plan", "edit", "remove"} and any(s.status != "planned" for s in stops):
                raise ValueError("Planning is locked after loading begins.")
            if action == "edit":
                for key, value in RunInput.model_validate(payload).model_dump().items():
                    setattr(run, key, value)
            elif action == "add":
                data = StopInput.model_validate(payload)
                if len(stops) >= 100:
                    raise ValueError("A dispatch run supports at most 100 stops.")
                shipment = session.scalar(select(CommercialShipment).where(CommercialShipment.id == data.shipment_id, CommercialShipment.organization_id == self.org, CommercialShipment.facility_id == self.facility).with_for_update())
                order = session.get(CommercialOrder, shipment.commercial_order_id) if shipment else None
                partner = session.get(TradePartner, order.partner_id) if order else None
                if not shipment or not order or not partner or order.organization_id != self.org or order.facility_id != self.facility or partner.organization_id != self.org:
                    raise ValueError("Shipment and customer must belong to the active facility and organization.")
                if order.order_type != "sales" or order.status == "cancelled" or shipment.status in {"cancelled", "delivered"}:
                    raise ValueError("Shipment is not available for dispatch.")
                if session.scalar(select(DispatchStop.id).where(DispatchStop.shipment_id == shipment.id)):
                    raise ValueError("Shipment already belongs to a dispatch stop.")
                fields = data.model_dump()
                fields["contact_snapshot"] = data.contact_snapshot or " / ".join(filter(None, [partner.contact_name, partner.contact_phone, partner.contact_email]))
                stop = DispatchStop(run_id=run.id, sequence=len(stops)+1, partner_name_snapshot=partner.name, **fields)
                session.add(stop)
                stops.append(stop)
            elif action in {"reorder", "plan"}:
                if action == "plan":
                    if any(s.latitude is None or s.longitude is None for s in stops):
                        return {"message": "Coordinates missing. Stop order is unchanged; reorder manually.", "version": run.version}
                    # Keep the first stop as the explicit starting anchor. Stable ties use ID.
                    ordered, remaining = stops[:1], stops[1:]
                    while remaining:
                        nearest = min(remaining, key=lambda s: (distance(ordered[-1], s), s.id))
                        ordered.append(nearest)
                        remaining.remove(nearest)
                    ids = [s.id for s in ordered]
                    message = "Nearest-neighbor order from the first stop. Check windows and road conditions manually."
                else:
                    ids = payload
                if len(ids) != len(stops) or set(ids) != {s.id for s in stops}:
                    raise ValueError("Reorder must include every stop exactly once.")
                by_id = {s.id: s for s in stops}
                for index, sid in enumerate(ids, 1):
                    by_id[sid].sequence = index
            elif action == "remove":
                session.delete(stop)
                stops.remove(stop)
                for index, remaining in enumerate(stops, 1):
                    remaining.sequence = index
            elif action == "status":
                data = Outcome.model_validate({**payload, "version": version})
                if data.status == stop.status:
                    # Retry is harmless and cannot overwrite previously recorded evidence.
                    return {"message": "Status already recorded.", "version": run.version}
                if data.status not in TRANSITIONS[stop.status]:
                    raise ValueError("Invalid delivery status transition.")
                if data.status == "en_route":
                    shipment = session.scalar(select(CommercialShipment).where(CommercialShipment.id == stop.shipment_id).with_for_update())
                    if shipment.status not in {"manifested", "shipped"} or not shipment.manifest_reference.strip():
                        raise ValueError("Record the governed shipment manifest before departure.")
                if data.status in {"partial", "rejected", "returned"} and not data.outcome_notes:
                    raise ValueError("Delivery exceptions require notes for reconciliation.")
                if data.status in {"delivered", "partial"}:
                    if not data.recipient_name:
                        raise ValueError("Recipient name is required for proof of delivery.")
                    delivered = data.delivered_at or utc_now()
                    if delivered > datetime.now(timezone.utc):
                        raise ValueError("Delivery timestamp cannot be in the future.")
                    stop.recipient_name, stop.delivered_at = data.recipient_name, delivered
                    stop.acknowledgment_name = data.acknowledgment_name
                    stop.acknowledged_at = utc_now() if data.acknowledgment_name else None
                elif data.delivered_at or data.recipient_name or data.acknowledgment_name:
                    raise ValueError("Proof of delivery belongs only to delivered or partial outcomes.")
                stop.status = data.status
                # Preserve original partial-delivery evidence when the remainder is returned.
                if data.outcome_notes:
                    stop.outcome_notes = "\n".join(filter(None, [stop.outcome_notes, f"{data.status}: {data.outcome_notes}"]))
            else:
                raise ValueError("Unknown dispatch action.")
            run.version += 1
            session.flush()
            self._audit(session, run, f"dispatch_{action}", before, {"run": values(run), "stops": [values(s) for s in stops]})
            return {"message": message, "version": run.version}
