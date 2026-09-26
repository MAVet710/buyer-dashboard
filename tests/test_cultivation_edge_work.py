"""Real persisted rollups and canonical Work; no happy-path domain substitutions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers.cultivation_edge_work import router
from backend.app.schemas.work import WorkUpdate
from backend.app.services.work import WorkService
from modules.coman.models import WorkItem, AuditEvent, AppUser, Facility
from modules.coman.permissions import AppUserPermissionOverride
from modules.cultivation.edge_work import EdgeWorkService, ENTITY, return_route
from modules.cultivation.edge_store import Scope
from modules.cultivation.gateway import TelemetryGatewayService
from modules.cultivation.intelligence_models import CultivationRecipeTarget
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


@pytest.fixture
def bridge(historical_context):
    h = historical_context
    # Historical fixture assembled before acquisition, with explicit duration policy.
    with Session(h.engine) as s, s.begin():
        target = s.scalar(select(CultivationRecipeTarget).where(CultivationRecipeTarget.stage_id == h.history.stage))
        target.threshold_seconds = 240
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_engine] = lambda: h.engine
    app.dependency_overrides[get_request_context] = lambda: h.state['context']
    h.api = TestClient(app)
    h.window = {'start': h.history.start.isoformat(), 'end': h.history.end.isoformat()}
    h.path = f'/api/v1/cultivation-intelligence/rooms/{h.own.room}/deviations'
    h.scope = Scope(h.own.org, h.own.facility, h.history.connection)
    yield h
    h.api.close()


def acquire(h, events=None, rollup=True):
    x = h.history
    events = events or [('first', 0, 77), ('second', 300, 77)]
    rows = [dict(event_id=name, source_device_id='fixture', source_channel='temp',
        source_metric='vendor_temp', value=value, unit='F', quality='valid',
        observed_at=(x.start + timedelta(seconds=seconds)).isoformat()) for name, seconds, value in events]
    gateway = TelemetryGatewayService(h.engine, h.state['context'], edge=h.edge)
    with Session(h.engine) as session:
        resolver = gateway._resolver(session, x.connection)
        result = h.edge.ingest(h.scope, rows, resolved=[resolver(h.scope, row) for row in rows])
    assert result['accepted'] == len(rows)
    if rollup:
        h.edge.rollup(h.scope, x.start, x.end)


def listing(h):
    response = h.api.get(h.path, params=h.window)
    assert response.status_code == 200, response.text
    return response.json()


def create(h, identity, **kwargs):
    return h.api.post(h.path + '/' + identity + '/work', json=kwargs or h.window)


def counts(h):
    with Session(h.engine) as s:
        return s.scalar(select(func.count()).select_from(WorkItem)), s.scalar(select(func.count()).select_from(AuditEvent))


def test_historical_canonical_work_completed_reuse_and_exact_route(bridge):
    h = bridge
    acquire(h)
    before = counts(h)
    item, = listing(h)['items']
    assert counts(h) == before  # Summary never creates Work or audits.
    assert item['duration_seconds'] == 600 and item['threshold_seconds'] == 240
    assert item['direction'] == 'above' and item['work_item_id'] is None
    expected = return_route(h.own.room, item['exception_id'], h.history.start, h.history.end)
    assert item['return_route'] == expected
    assert parse_qs(urlsplit(expected).query) == dict(room=[h.own.room], edge_exception=[item['exception_id']],
        start=[h.window['start']], end=[h.window['end']])
    response = create(h, item['exception_id'])
    assert response.status_code == 200, response.text
    result = response.json()
    assert counts(h) == (before[0] + 1, before[1] + 2)
    assert result == dict(work_item_id=result['work_item_id'], existing=False, return_route=expected)
    work = WorkService(h.engine, h.state['context'])
    persisted = work.get(result['work_item_id'])
    evidence = json.loads(persisted['evidence'])
    assert persisted['entity_type'] == ENTITY and persisted['route'] == expected
    assert evidence['snapshot']['recipe_revision'] == h.history.recipe
    assert evidence['evidence_as_of'] and evidence['rollup_revision'] and evidence['local_cloud_atomic'] is False
    work.update(persisted['id'], WorkUpdate(version=persisted['version'], status='completed'))
    assert create(h, item['exception_id']).json() == dict(result, existing=True)
    assert listing(h)['items'][0]['work_item_id'] == persisted['id']
    assert counts(h)[0] == 1


@pytest.mark.parametrize('case', ['missing', 'spoof', 'foreign', 'readonly', 'inactive', 'capability', 'cultivation_deny', 'work_deny'])
def test_authorization_and_unknown_ids(bridge, case):
    h = bridge
    acquire(h)
    item = listing(h)['items'][0]
    identity = item['exception_id']
    expected = 403
    if case in ('missing', 'spoof'):
        identity = 'nonexistent' if case == 'missing' else 'a' * 64
        expected = 409
    elif case == 'foreign':
        h.state['context'] = RequestContext(h.other.user, h.other.org, h.other.facility, 'admin')
        expected = 404
    elif case == 'readonly':
        h.state['context'] = RequestContext(h.own.user, h.own.org, h.own.facility, 'read_only')
    else:
        with Session(h.engine) as s, s.begin():
            if case == 'inactive':
                s.get(AppUser, h.own.user).active = False
            elif case == 'capability':
                s.get(Facility, h.own.facility).cultivation_enabled = False
            else:
                s.add(AppUserPermissionOverride(user_id=h.own.user, organization_id=h.own.org,
                    facility_id=h.own.facility, permission='work.create' if case == 'work_deny' else 'cultivation.manage_intelligence',
                    effect='deny', created_by=h.own.user, updated_by=h.own.user))
    assert create(h, identity).status_code == expected
    assert counts(h)[0] == 0


def test_existing_work_still_requires_permission(bridge):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    assert create(h, identity).status_code == 200
    with Session(h.engine) as s, s.begin():
        s.add(AppUserPermissionOverride(user_id=h.own.user, organization_id=h.own.org, facility_id=h.own.facility,
            permission='work.create', effect='deny', created_by=h.own.user, updated_by=h.own.user))
    assert create(h, identity).status_code == 403


@pytest.mark.parametrize('mode', ['no_threshold', 'gap', 'opposite', 'no_rollup', 'no_cycle'])
def test_unqualified_evidence_never_becomes_work(bridge, mode):
    h = bridge
    if mode == 'no_threshold':
        with Session(h.engine) as s, s.begin():
            s.scalar(select(CultivationRecipeTarget).where(CultivationRecipeTarget.stage_id == h.history.stage)).threshold_seconds = None
    if mode == 'no_cycle':
        from modules.cultivation.intelligence_models import CropCycleRoom
        with Session(h.engine) as s, s.begin():
            s.scalar(select(CropCycleRoom).where(CropCycleRoom.cycle_id == h.history.cycle)).exited_at = h.history.start
    events = [('first', 0, 77), ('normal', 100, 72), ('second', 900, 77), ('stop', 1000, 72)] if mode == 'gap' else (
        [('first', 0, 77), ('below', 120, 60), ('stop', 240, 72)] if mode == 'opposite' else None)
    acquire(h, events, rollup=mode != 'no_rollup')
    assert listing(h)['items'] == []
    assert create(h, 'a' * 64).status_code == 409


def test_dirty_and_changed_revisions_invalidate_selection(bridge):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    acquire(h, [('late', 100, 78)], rollup=False)
    assert listing(h) == dict(items=[], window=h.window, truncated=True, can_create_work=True)
    assert create(h, identity).status_code == 409
    h.edge.rollup(h.scope, h.history.start, h.history.end)
    new = listing(h)['items'][0]
    assert new['duration_seconds'] == 600  # Even unchanged duration requires review of changed evidence.
    assert new['exception_id'] != identity
    assert create(h, identity).status_code == 409


def test_atomic_central_audit_failure(bridge, monkeypatch):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    before = counts(h)
    def fail(*args, **kwargs):
        raise RuntimeError('injected central audit failure')
    monkeypatch.setattr('modules.cultivation.edge_work.record_audit_event', fail)
    with pytest.raises(RuntimeError, match='injected'):
        create(h, identity)
    assert counts(h) == before


def test_concurrent_clicks_serialize_on_canonical_sqlite(bridge):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    def click(_):
        return EdgeWorkService(h.engine, h.state['context'], edge=h.edge).create_work(h.own.room, identity, h.window)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(click, range(3)))
    assert len({r['work_item_id'] for r in results}) == 1
    assert sum(not r['existing'] for r in results) == 1
    assert counts(h)[0] == 1


@pytest.mark.parametrize('body', [dict(start='2026-01-01T00:00:00', end='2026-01-01T01:00:00'),
    dict(start='2026-01-01T00:00:00+01:00', end='2026-01-01T01:00:00+01:00'),
    dict(start='2026-01-01T00:00:01Z', end='2026-01-01T01:00:00Z'),
    dict(start='2026-01-01T00:00:00Z', end='2026-04-01T00:00:00Z')])
def test_invalid_windows(bridge, body):
    assert bridge.api.get(bridge.path, params=body).status_code == 422
    assert create(bridge, 'a' * 64, **body).status_code == 422


def test_exact_input_and_scope_before_local_access(bridge, monkeypatch):
    h = bridge
    assert h.api.get(h.path, params=dict(h.window, snapshot='forged')).status_code == 422
    assert create(h, 'a' * 64, **dict(h.window, value=99)).status_code == 422
    monkeypatch.setenv('CULTIVATION_EDGE_PATH', 'Z:/unavailable/not-authorized.sqlite')
    h.state['context'] = RequestContext(h.other.user, h.other.org, h.other.facility, 'admin')
    assert h.api.get(h.path, params=h.window).status_code == 404
    assert create(h, 'a' * 64).status_code == 404


def test_get_uses_one_batched_work_lookup(bridge):
    h = bridge
    acquire(h)
    statements = []
    def record(conn, cursor, statement, *args):
        if 'work_items' in statement.lower() and statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(h.engine, 'before_cursor_execute', record)
    try:
        listing(h)
    finally:
        event.remove(h.engine, 'before_cursor_execute', record)
    assert len(statements) == 1


def test_local_late_arrival_between_selection_and_create_fails_closed(bridge):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    changed = []
    def arrive(conn, cursor, statement, *args):
        if not changed and 'work_items' in statement.lower() and statement.lstrip().upper().startswith('SELECT'):
            changed.append(True)
            acquire(h, [('racing-arrival', 100, 78)], rollup=False)
    event.listen(h.engine, 'before_cursor_execute', arrive)
    try:
        assert create(h, identity).status_code == 409
    finally:
        event.remove(h.engine, 'before_cursor_execute', arrive)
    assert changed and counts(h)[0] == 0


def test_truncated_query_offers_no_action(bridge, monkeypatch):
    h = bridge
    acquire(h)
    identity = listing(h)['items'][0]['exception_id']
    h.edge.rollup(h.scope, h.history.end, h.history.end + timedelta(hours=1))
    h.window['end'] = (h.history.end + timedelta(hours=1)).isoformat()
    monkeypatch.setenv('CULTIVATION_EDGE_MAX_QUERY_ROWS', '1')
    assert listing(h) == dict(items=[], window=h.window, truncated=True, can_create_work=True)
    assert create(h, identity).status_code == 409


@pytest.mark.parametrize('restriction', ['none', 'readonly', 'inactive', 'work_deny', 'cultivation_deny'])
def test_list_reports_effective_work_capability_without_mutation(bridge, restriction):
    h = bridge
    acquire(h)
    if restriction == 'readonly':
        h.state['context'] = RequestContext(h.own.user, h.own.org, h.own.facility, 'read_only')
    elif restriction != 'none':
        with Session(h.engine) as session, session.begin():
            if restriction == 'inactive':
                session.get(AppUser, h.own.user).active = False
            else:
                session.add(AppUserPermissionOverride(user_id=h.own.user, organization_id=h.own.org,
                    facility_id=h.own.facility,
                    permission='work.create' if restriction == 'work_deny' else 'cultivation.manage_intelligence',
                    effect='deny', created_by=h.own.user, updated_by=h.own.user))
    before = counts(h)
    result = listing(h)
    assert result['can_create_work'] is (restriction == 'none')
    assert result['items'] and counts(h) == before
    if restriction != 'none':
        assert create(h, result['items'][0]['exception_id']).status_code == 403
        assert counts(h) == before
