"""Explicit reviewed historical edge evidence -> canonical Work, never raw replay."""
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import urlencode, quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.permissions import require_permission, permission_snapshot
from backend.app.schemas.work import WorkCreate
from backend.app.services.work import WorkService
from modules.coman.audit import record_audit_event
from modules.coman.models import WorkItem, AppUser
from .gateway import TelemetryGatewayService, WindowInput, configured_edge
from .intelligence_models import (TelemetryConnection, CultivationDevice, CultivationSensor,
    DeviceMapping, CropCycle, CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget)
from .models import CultivationRoom
from .telemetry import TelemetryConflict, utc

ENTITY = 'cultivation_edge_exception'
MAX_ITEMS = 200


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def return_route(room, exception, start, end):
    return '/cultivation?' + urlencode({'room': room, 'edge_exception': exception,
        'start': start.isoformat(), 'end': end.isoformat()}, quote_via=quote)


class EdgeWorkService(TelemetryGatewayService):
    def edge(self):
        if self._edge is None:
            self._edge = configured_edge(self._path, read_only=True)
        return self._edge

    def _revisions(self, start, end):
        """Bounded metadata only. Dirty buckets must not silently vanish from summary.

        Adapter to the existing local schema, owned by EdgeStore. No raw reads,
        recalculation, ack or local writes occur here.
        """
        edge = self.edge()
        with edge._db() as db:
            rows = db.execute("SELECT key,revision,dirty,scope,start,COALESCE(json_extract(payload,'$.calculation_version'),0) AS calculation_version FROM buckets WHERE org=? AND facility=? "
                'AND start>=? AND start<? ORDER BY key LIMIT ?',
                (self.org, self.facility, start.timestamp(), end.timestamp(), edge.max_query_rows + 1)).fetchall()
        if len(rows) > edge.max_query_rows or any(r['dirty'] or r['calculation_version'] < 3 for r in rows):
            return None
        return [dict(key=r['key'], revision=r['revision'], scope=r['scope'], start=r['start']) for r in rows]

    def _contexts(self, session, streams):
        """Fixed batched scoped queries, independent of sensor count."""
        specs = [(TelemetryConnection, 'connection_id'), (CultivationDevice, 'device_id'),
            (CultivationSensor, 'sensor_id'), (DeviceMapping, 'mapping_revision'),
            (CropCycle, 'cycle_id'), (CultivationRecipe, 'recipe_revision'),
            (CultivationRecipeStage, 'stage_id')]
        result = {}
        for model, field in specs:
            ids = {entry['snapshot'].get(field) for entry in streams} - {None}
            result[field] = {row.id: row for row in session.scalars(select(model).where(
                *self.scope(model), model.id.in_(ids)).limit(MAX_ITEMS + 1))}
        result['targets'] = {(row.stage_id, row.metric): row for row in session.scalars(
            select(CultivationRecipeTarget).where(*self.scope(CultivationRecipeTarget),
                CultivationRecipeTarget.stage_id.in_(result['stage_id'])).limit(5001))}
        if len(result['targets']) > 5000:
            return None
        return result

    def _valid_context(self, room, entry, context):
        snap = entry['snapshot']
        try:
            connection, device, sensor, mapping, cycle, recipe, stage = (
                context[key][snap[key]] for key in ('connection_id', 'device_id', 'sensor_id',
                    'mapping_revision', 'cycle_id', 'recipe_revision', 'stage_id'))
            target = context['targets'][stage.id, entry['metric']]
        except KeyError:
            return False
        return (snap.get('organization_id') == self.org and snap.get('facility_id') == self.facility
            and snap.get('room_id') == room and mapping.room_id == room
            and mapping.device_id == device.id and sensor.device_id == device.id
            and device.connection_id == connection.id and cycle.recipe_id == recipe.id
            and stage.recipe_id == recipe.id and recipe.status == 'approved' and recipe.approved_at
            and sensor.metric == entry['metric'] == snap.get('metric')
            and entry['stream'] == [device.source_device_id, sensor.source_channel]
            and target.minimum == snap.get('target_min') and target.maximum == snap.get('target_max')
            and target.threshold_seconds == snap.get('threshold_seconds')
            and target.unit == entry['unit'])

    def _candidates(self, session, room, start, end):
        before = self._revisions(start, end)
        if before is None:
            return [], True
        summary = self._summary(room, start, end)
        if summary['truncated'] or before != self._revisions(start, end):
            return [], True
        contexts = self._contexts(session, summary['streams'])
        if contexts is None:
            return [], True
        revision_hash = digest(before)
        revisions_by_connection = {}
        for revision in before:
            connection = json.loads(revision['scope'])['connection_id']
            revisions_by_connection.setdefault(connection, []).append(revision)
        items = []
        as_of = datetime.now(timezone.utc).isoformat()
        for stream in summary['streams']:
            if not self._valid_context(room, stream, contexts):
                continue
            snap = stream['snapshot']
            threshold = snap.get('threshold_seconds')
            if not threshold or threshold <= 0 or (snap.get('target_min') is None and snap.get('target_max') is None):
                continue
            recipe = contexts['recipe_revision'][snap['recipe_revision']]
            for deviation in stream['deviations']:
                began = datetime.fromisoformat(deviation['start'])
                ended = datetime.fromisoformat(deviation['end'])
                seconds = (ended - began).total_seconds()
                if (deviation['direction'] not in ('above', 'below') or seconds < threshold
                    or seconds != deviation['seconds'] or began < start or ended > end
                    or utc(recipe.approved_at) > began
                    or not any(a <= began.timestamp() and b >= ended.timestamp()
                        for a, b in stream['attribution_intervals'])):
                    continue
                proof = [[r['key'], r['revision']] for r in revisions_by_connection.get(snap['connection_id'], [])
                    if r['start'] < ended.timestamp()
                    and r['start'] + self.edge().bucket_seconds > began.timestamp()]
                if not proof:
                    continue
                sensor = contexts['sensor_id'][snap['sensor_id']]
                identity = {'snapshot': snap, 'source': stream['stream'], 'unit': stream['unit'],
                    'source_metric': sensor.source_metric, 'source_unit': sensor.source_unit,
                    'bucket_revisions': proof,
                    'direction': deviation['direction'], 'start': deviation['start'], 'end': deviation['end']}
                exception = digest(identity)
                item = dict(exception_id=exception, metric=stream['metric'], unit=stream['unit'],
                    connection_id=snap['connection_id'], sensor_id=snap['sensor_id'],
                    cycle_id=snap['cycle_id'], recipe_revision=snap['recipe_revision'],
                    direction=deviation['direction'], started_at=deviation['start'], ended_at=deviation['end'],
                    duration_seconds=seconds, threshold_seconds=threshold, work_item_id=None,
                    return_route=return_route(room, exception, start, end))
                evidence = dict(identity, exception_id=exception, room_id=room,
                    duration_seconds=seconds, threshold_seconds=threshold,
                    evidence_as_of=as_of, rollup_revision=revision_hash,
                    window={'start': start.isoformat(), 'end': end.isoformat()},
                    decision_support_only=True, local_cloud_atomic=False)
                if len(encoded(evidence).encode()) > 16000:
                    return [], True
                items.append((item, evidence))
                if len(items) > MAX_ITEMS:
                    return [], True
        return sorted(items, key=lambda pair: pair[0]['exception_id']), False

    def _work(self, session, identities):
        # Include completed Work. Grouped minimum is unnecessary: ordered results
        # preserve the earliest canonical item in case legacy duplicates exist.
        rows = session.execute(select(WorkItem.entity_id, WorkItem.id).where(
            *self.scope(WorkItem), WorkItem.entity_type == ENTITY,
            WorkItem.entity_id.in_(identities)).order_by(WorkItem.created_at, WorkItem.id).limit(1001)).all()
        if len(rows) > 1000:
            raise TelemetryConflict('Work lookup exceeds capacity; refresh after administrator review.')
        result = {}
        for exception, identity in rows:
            result.setdefault(exception, identity)
        return result

    def deviations(self, room_id, payload):
        p = WindowInput.model_validate(payload)
        with Session(self.engine) as session:
            self.authorize(session=session)
            self.get(session, CultivationRoom, room_id)  # Before any local filesystem access.
            start, end = self._window(p.start, p.end)
            candidates, truncated = self._candidates(session, room_id, start, end)
            links = self._work(session, [item['exception_id'] for item, _ in candidates])
            # Read-only capability mirrors the POST boundary without taking a
            # write reservation or treating a role label as sufficient authority.
            from backend.app.routers.plants import WRITE_ROLES
            effective = permission_snapshot(self.context, self.engine, session=session)['effective']
            actor = session.get(AppUser, self.context.user_id)
            can_create = bool(actor and actor.active
                and (actor.organization_id == self.org or self.context.role.casefold() == 'dev')
                and self.context.role.casefold() in WRITE_ROLES
                and effective['cultivation.manage_intelligence'] and effective['work.create'])
            return {'can_create_work': can_create, 'items': [dict(item, work_item_id=links.get(item['exception_id'])) for item, _ in candidates],
                'window': {'start': start.isoformat(), 'end': end.isoformat()}, 'truncated': truncated}

    def create_work(self, room_id, exception_id, payload):
        p = WindowInput.model_validate(payload)
        with Session(self.engine) as session, session.begin():
            self.authorize(write=True, session=session)
            require_permission(self.context, self.engine, 'work.create', session=session)
            self.get(session, CultivationRoom, room_id, lock=True)
            start, end = self._window(p.start, p.end)
            candidates, truncated = self._candidates(session, room_id, start, end)
            selected = next((pair for pair in candidates if pair[0]['exception_id'] == exception_id), None)
            if truncated or selected is None:
                raise TelemetryConflict('Deviation evidence changed or is unavailable; refresh the selected window.')
            item, evidence = selected
            existing = self._work(session, [exception_id]).get(exception_id)
            # Last local observation before central mutation. This is deliberately
            # not presented as a distributed transaction or a lock on the collector.
            revisions = self._revisions(start, end)
            if revisions is None or digest(revisions) != evidence['rollup_revision']:
                raise TelemetryConflict('Deviation evidence changed; refresh the selected window.')
            if existing:
                return dict(work_item_id=existing, existing=True, return_route=item['return_route'])
            work = WorkService(self.engine, self.context).create(WorkCreate(
                title=f"Review {item['metric']} {item['direction']} approved target",
                description='Review the selected historical room deviation and document the operational response.',
                entity_type=ENTITY, entity_id=exception_id, workspace='Cultivation',
                route=item['return_route'], evidence=encoded(evidence)), session=session)
            record_audit_event(session, organization_id=self.org, facility_id=self.facility,
                entity_type='cultivation_room', entity_id=room_id, action='edge_deviation_work_created',
                actor=self.context.user_id, source='api', correlation_id=work['id'],
                changes={'exception_id': exception_id, 'work_item_id': work['id'],
                    'evidence_as_of': evidence['evidence_as_of'], 'rollup_revision': evidence['rollup_revision']})
            return dict(work_item_id=work['id'], existing=False, return_route=item['return_route'])
