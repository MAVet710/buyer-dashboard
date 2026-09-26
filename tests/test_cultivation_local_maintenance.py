"""Real local central SQLite + canonical EdgeStore; no network or production data."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_cultivation_intelligence_foundation import setup, configure, AT
from modules.coman.models import Facility, Organization
from modules.cultivation.collector import FileCollector
from modules.cultivation.adapters.normalized import NormalizedExportAdapter
from modules.cultivation.edge_store import EdgeStore, Scope
from modules.cultivation.ingress import IngressGrantService
from modules.cultivation.ingress_models import CultivationIngressGrant
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.operational_moats.models import ServiceAccount
from modules.cultivation.local_maintenance import MaintenanceConfig, MaintenanceController
from backend.app.services.cultivation_maintenance_runtime import start_maintenance, stop_maintenance


@pytest.fixture
def local(setup):
    engine, service = setup
    connection, device, payload = configure(service)
    config = MaintenanceConfig(enabled=True, organization_id='o1', facility_id='f1',
                               connection_ids=(connection['id'],), database_path=str(service.edge().path))
    return engine, service, config, json.loads(payload['content'])[0]


def tick(controller):
    # Simulate expiration of the runtime backoff without sleeping in tests.
    controller._retry_at = 0
    return controller.tick()


def scope(config):
    return Scope(config.organization_id, config.facility_id, config.connection_ids[0])


def test_offline_file_capture_recovery_historical_mapping_and_replay(local, tmp_path):
    engine, service, config, raw = local
    folder = tmp_path/'input'; folder.mkdir()
    ready = folder/'reading.ready.json'; ready.write_text(json.dumps([raw]), encoding='utf-8')
    adapter = NormalizedExportAdapter(columns={k:k for k in raw}, metric_mappings=[
        dict(source_channel='air', source_metric='temp', metric='temperature', unit='F')])
    collector = FileCollector(service.edge(), scope(config), folder, adapter)
    def outage(*args):
        raise OperationalError('SELECT', {}, Exception('private outage detail'))
    event.listen(engine, 'before_cursor_execute', outage)
    assert collector.run(once=True)['committed_files'] == 1
    controller = MaintenanceController(engine, config)
    assert tick(controller)['error_code'] == 'maintenance_unavailable'
    assert service.edge().evidence(scope(config))['items'][0]['state'] == 'pending'
    event.remove(engine, 'before_cursor_execute', outage)
    statements = []
    def record(conn, cursor, statement, *args): statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    result = tick(controller)
    assert result['resolved'] == 1 and result['state'] == 'completed'
    stored = service.edge().evidence(scope(config))['items'][0]
    assert stored['snapshot']['room_id'] == 'r1'
    assert stored['canonical']['value'] == 25
    assert not any(q.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in statements)
    assert collector.run(once=True)['skipped'] == 1
    assert service.edge().ingest(scope(config), [raw])['duplicates'] == 1
    assert ready.exists()
    assert service.edge().transport_status(scope(config))['last_committed_at'] is None


@pytest.mark.parametrize('denial', ['facility', 'organization', 'capability', 'foreign', 'revoked', 'missing'])
def test_validation_before_any_filesystem_write(local, tmp_path, denial):
    engine, service, config, raw = local
    target = tmp_path/'never.db'
    config = replace(config, database_path=str(target))
    with Session(engine) as session, session.begin():
        if denial == 'facility': session.get(Facility, 'f1').active = False
        if denial == 'organization': session.get(Organization, 'o1').active = False
        if denial == 'capability': session.get(Facility, 'f1').cultivation_enabled = False
        if denial == 'revoked': session.get(TelemetryConnection, config.connection_ids[0]).revoked_at = AT
    if denial == 'foreign': config = replace(config, facility_id='f2')
    if denial == 'missing': config = replace(config, connection_ids=('missing',))
    assert tick(MaintenanceController(engine, config))['state'] == 'stopped'
    assert not target.exists() and not Path(str(target)+'-wal').exists()


@pytest.mark.parametrize('denial', ['none', 'expired', 'revoked', 'inactive', 'wildcard'])
def test_push_requires_live_grant_each_iteration(local, tmp_path, denial):
    engine, service, config, raw = local
    connection = service.create_connection(dict(provider='json', label='Push maintenance', mode='push'))
    config = replace(config, connection_ids=(connection['id'],), database_path=str(tmp_path/'push.db'))
    if denial != 'none':
        issued = IngressGrantService(engine, service.context).issue_grant(connection['id'], dict(
            version=1, label='Fixture', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        controller = MaintenanceController(engine, config)
        assert tick(controller)['state'] == 'completed'  # Trusted host needs no token.
        before = Path(config.database_path).read_bytes()
        with Session(engine) as session, session.begin():
            grant = session.get(CultivationIngressGrant, issued['grant']['id'])
            account = session.get(ServiceAccount, issued['grant']['service_account_id'])
            if denial == 'expired': grant.expires_at = AT
            if denial == 'revoked': grant.revoked_at = AT
            if denial == 'inactive': account.active = False
            if denial == 'wildcard': account.scopes_json = '["*"]'
        assert tick(controller)['state'] == 'stopped'
        assert Path(config.database_path).read_bytes() == before
    else:
        assert tick(MaintenanceController(engine, config))['state'] == 'stopped'
        assert not Path(config.database_path).exists()


def test_old_new_dirty_fairness_and_connection_round_robin(local):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [dict(raw, event_id=str(i), observed_at=(AT+timedelta(hours=i)).isoformat()) for i in range(10)])
    controller = MaintenanceController(engine, config)
    for _ in range(12): assert tick(controller)['state'] == 'completed'
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM buckets WHERE scope=?', (sc.key,)).fetchone()[0] >= 10
    store.ingest(sc, [dict(raw, event_id='late', value=78)])
    assert tick(controller)['rebuilt'] >= 1
    other = service.create_connection(dict(provider='json', label='Other'))
    other_scope = Scope('o1', 'f1', other['id'])
    store.ingest(other_scope, [dict(raw, event_id='other')])
    controller = MaintenanceController(engine, replace(config, connection_ids=(*config.connection_ids, other['id'])))
    tick(controller); tick(controller)
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM local_cultivation_maintenance').fetchone()[0] == 2


def test_archive_then_explicit_retention_protects_unresolved_dispute(local, tmp_path):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [raw, dict(raw, event_id='pending', source_device_id='unknown', observed_at=(AT+timedelta(days=1)).isoformat()),
                      dict(raw, event_id='bad', quality='bad', observed_at=(AT+timedelta(days=2)).isoformat()),
                      dict(raw, event_id='disputed', observed_at=(AT+timedelta(days=3)).isoformat())])
    store.ingest(sc, [dict(raw, event_id='disputed', value=79, observed_at=(AT+timedelta(days=3)).isoformat())])
    with store._db(write=True) as db: db.execute('UPDATE evidence SET received=?', (AT.timestamp(),))
    archive = tmp_path/'archive'; archive.mkdir()
    controller = MaintenanceController(engine, replace(config, archive_directory=str(archive)))
    for _ in range(10): tick(controller)
    with store._db() as db: assert db.execute('SELECT COUNT(*) FROM evidence WHERE raw IS NULL').fetchone()[0] == 0
    controller = MaintenanceController(engine, replace(config, archive_directory=str(archive), retention_days=1))
    tick(controller)
    with store._db() as db:
        rows = db.execute('SELECT state,raw FROM evidence').fetchall()
    assert sum(r['state'] == 'archived' for r in rows) == 1
    assert all(r['raw'] is not None for r in rows if r['state'] != 'archived')
    assert list(archive.rglob('*.json'))


@pytest.mark.parametrize('failure', ['full', 'locked', 'rollup_limit'])
def test_bounded_storage_failure_no_ack_or_partial_rollup(local, tmp_path, failure):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [raw, dict(raw, event_id='two')])
    options = (('busy_timeout_ms', 50),)
    if failure == 'full': options += (('max_scope_rows', 1),)
    if failure == 'rollup_limit': options += (('max_rollup_rows', 1),)
    archive = tmp_path/'archive'; archive.mkdir()
    controller = MaintenanceController(engine, replace(config, edge_options=options, archive_directory=str(archive)))
    lock = sqlite3.connect(store.path, isolation_level=None)
    if failure == 'locked': lock.execute('BEGIN IMMEDIATE')
    started = time.monotonic()
    result = tick(controller)
    lock.close()
    assert time.monotonic()-started < 5
    assert result['state'] == 'backoff' and result['acknowledged'] == 0
    assert not list(archive.rglob('*.json'))
    assert controller.tick() == result
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM buckets').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM evidence WHERE raw IS NOT NULL').fetchone()[0] == 2


def test_restart_cursor_in_real_process(local):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [dict(raw, event_id=str(i), observed_at=(AT+timedelta(hours=i)).isoformat()) for i in range(5)])
    controller = MaintenanceController(engine, config)
    tick(controller)
    with store._db() as db: before = db.execute('SELECT discovery FROM local_cultivation_maintenance').fetchone()[0]
    # Child uses actual store and cursor selection; no central/network connection is needed to inspect progress.
    code = '''import sys
sys.path.insert(0, sys.argv[1])
from modules.cultivation.local_maintenance import MaintenanceController, MaintenanceConfig
from modules.cultivation.edge_store import EdgeStore, Scope
c = MaintenanceController(None, MaintenanceConfig())
c._candidates(EdgeStore(sys.argv[2]), Scope('o1','f1',sys.argv[3]))
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(Path(__file__).resolve().parents[1]), str(store.path), sc.connection_id],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    with store._db() as db: after = db.execute('SELECT discovery FROM local_cultivation_maintenance').fetchone()[0]
    assert after == before+3600


def test_disabled_and_singleton_runtime(local, tmp_path):
    engine, service, config, raw = local
    before = {t.ident for t in threading.enumerate()}
    disabled = MaintenanceConfig(database_path=str(tmp_path/'disabled.db'))
    assert start_maintenance(engine, disabled) is None
    assert MaintenanceController(engine, disabled).tick()['state'] == 'disabled'
    assert {t.ident for t in threading.enumerate()} == before
    assert not (tmp_path/'disabled.db').exists()
    runtime = start_maintenance(engine, config)
    try:
        assert start_maintenance(engine, config) is runtime
        with pytest.raises(ValueError): start_maintenance(engine, replace(config, interval_seconds=60))
    finally:
        assert stop_maintenance(5)


def test_retry_limit_and_fixed_context_query_count(local):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [dict(raw, event_id=str(i)) for i in range(120)])
    statements = []
    def record(conn, cursor, statement, *args): statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    controller = MaintenanceController(engine, config)
    assert tick(controller)['resolved'] == 100
    count = len(statements); statements.clear()
    assert tick(controller)['resolved'] == 20
    assert len(statements) == count == 12  # BEGIN + busy timeout + 2 scope + 8 context queries.


def test_retention_without_ack_keeps_raw_and_allowlist_never_scans_other_connections(local):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    other = service.create_connection(dict(provider='json', label='Not host approved'))
    other_scope = Scope('o1', 'f1', other['id'])
    store.ingest(sc, [raw]); store.ingest(other_scope, [raw])
    with store._db(write=True) as db: db.execute('UPDATE evidence SET received=?', (AT.timestamp(),))
    controller = MaintenanceController(engine, replace(config, retention_days=1))
    for _ in range(4): assert tick(controller)['purged'] == 0
    assert store.evidence(sc)['items'][0]['raw'] is not None
    assert store.evidence(other_scope)['items'][0]['state'] == 'pending'
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM local_cultivation_maintenance').fetchone()[0] == 1


def test_blocked_dirty_hour_does_not_starve_new_unbuilt_hour(local):
    engine, service, config, raw = local
    store = service.edge(); sc = scope(config)
    store.ingest(sc, [raw])
    controller = MaintenanceController(engine, config)
    for _ in range(3): tick(controller)
    store.ingest(sc, [dict(raw, event_id='late'), dict(raw, event_id='new', observed_at=(AT+timedelta(days=5)).isoformat())])
    controller = MaintenanceController(engine, replace(config, edge_options=(('max_rollup_rows', 1),)))
    for _ in range(6): tick(controller)
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM buckets WHERE start>=? AND dirty=0',
                          ((AT+timedelta(days=5)).timestamp(),)).fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM buckets WHERE dirty=1').fetchone()[0] > 0


def test_each_iteration_revalidates_file_connection(local):
    engine, service, config, raw = local
    controller = MaintenanceController(engine, config)
    assert tick(controller)['state'] == 'completed'
    with Session(engine) as session, session.begin():
        session.get(TelemetryConnection, config.connection_ids[0]).status = 'revoked'
    before = service.edge().path.read_bytes()
    assert tick(controller)['state'] == 'stopped'
    assert service.edge().path.read_bytes() == before


@pytest.mark.parametrize('changes', [dict(connection_ids=()), dict(interval_seconds=1),
    dict(enabled='false'), dict(edge_options=(['max_batch', 100],)),
    dict(database_path='relative.db'), dict(retention_days=0), dict(connection_ids=['mutable']),
    dict(edge_options=(('busy_timeout_ms', 6000),)), dict(edge_options=(('bucket_seconds', 60),))])
def test_invalid_host_configuration_fails_without_files(local, changes):
    _, _, config, _ = local
    with pytest.raises(ValueError): replace(config, **changes)
