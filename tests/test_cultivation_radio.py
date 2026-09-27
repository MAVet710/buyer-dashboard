"""Isolated real service/EdgeStore acceptance; no RF hardware or production data."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from queue import Queue
from pathlib import Path
import hashlib
import json
import sys
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.app.auth import RequestContext
from backend.app.routers import cultivation_radio as router_module
from modules.cultivation.radio.codecs import decode_bthome, decode_wh31, RadioInputError
from modules.cultivation.radio.config import RadioConfig, Receiver, load_config, RadioConfigError
from modules.cultivation.radio.runtime import RadioRuntime
from modules.cultivation.radio.models import RadioBinding
from modules.cultivation.intelligence_models import TelemetryConnection, CultivationDevice, CultivationSensor, DeviceMapping
from modules.cultivation.edge_store import Scope
from tests.test_cultivation_intelligence_end_to_end import harness

NOW = lambda: datetime.now(timezone.utc)
BASE = '/api/v1/cultivation-radio'
ADDRESS = 'ABCDEF123456'

class Capture:
    def __init__(self, receiver):
        self.queue = Queue(maxsize=128)
        self.ready = True
        self.running = False
    def start(self): self.running = True
    def stop(self): self.running = False
    def alive(self): return self.running

@pytest.fixture
def radio(harness, monkeypatch, tmp_path):
    h = harness
    interpreter = tmp_path / 'receiver.exe'
    interpreter.write_bytes(b'not executable test fixture')
    packages = tmp_path / 'packages'
    (packages / 'bleak').mkdir(parents=True)
    (packages / 'bleak' / '__init__.py').write_text('')
    receiver = Receiver('ble', 'ble', '2.4 GHz Bluetooth LE', str(interpreter), hashlib.sha256(interpreter.read_bytes()).hexdigest(), str(packages))
    runtime = RadioRuntime(h.engine, RadioConfig(h.own.org, h.own.facility, (receiver,), 10),
                           capture_factory=Capture, edge_factory=lambda: h.edge)
    monkeypatch.setattr(router_module, 'get_radio_runtime', lambda: runtime)
    h.client.app.include_router(router_module.router, prefix='/api/v1')
    h.runtime = runtime
    h.receiver = receiver
    yield h
    runtime.stop()


def scan_candidate(h, *, payload='4002C40903BF13'):
    response = h.client.post(BASE + '/scans', json={'receiver_id': 'ble', 'authorized': True})
    assert response.status_code == 200, response.text
    scan = response.json()
    h.runtime._tick()
    frame = decode_bthome(ADDRESS, bytes.fromhex(payload), NOW())
    h.runtime.captures['ble'].queue.put(frame)
    h.runtime._tick()
    response = h.client.get(BASE + '/scans/' + scan['id'])
    assert response.status_code == 200, response.text
    return response.json()


def link(h, scan, **changes):
    body = {'scan_id': scan['id'], 'candidate_id': scan['devices'][0]['id'],
            'room_id': h.own.room, 'display_name': 'Flower sensor', 'ownership_confirmed': True}
    body.update(changes)
    return h.client.post(BASE + '/connections', json=body)


def test_public_bthome_reference():
    reading = decode_bthome(ADDRESS, bytes.fromhex('4002C40903BF13'), NOW())
    assert [(m.metric, m.value, m.unit) for m in reading.measurements] == [('temperature', 25, 'C'), ('relative_humidity', 50.55, '%')]
    assert decode_bthome(ADDRESS, bytes.fromhex('4057EA'), NOW()).measurements[0].value == -22
    assert decode_bthome(ADDRESS, bytes.fromhex('4012E204'), NOW()).measurements[0].value == 1250

@pytest.mark.parametrize('payload', ['41AABB', '2002C409', '4402C409', '4005010000', '406001'])
def test_encrypted_unknown_event_only_never_become_values(payload):
    observed = decode_bthome(ADDRESS, bytes.fromhex(payload), NOW())
    assert not observed.supported and not observed.measurements

@pytest.mark.parametrize('payload', ['4002C4', '40020000020000', '4003FFFF'])
def test_malformed_bthome_rejected(payload):
    with pytest.raises(RadioInputError):
        decode_bthome(ADDRESS, bytes.fromhex(payload), NOW())

def test_wh31_decoder_is_specific_and_not_moisture_guessing():
    row = {'model': 'AmbientWeather-WH31E', 'id': 21, 'channel': 1, 'temperature_C': 25, 'humidity': 45, 'mic': 'CRC'}
    decoded = decode_wh31(row, NOW())
    assert decoded.profile == 'ambient_wh31' and decoded.measurements[0].value == 25
    for wrong in [dict(row, model='Fineoffset-WH51'), dict(row, mic=''), dict(row, id=True), dict(row, humidity=101)]:
        with pytest.raises(RadioInputError): decode_wh31(wrong, NOW())


def test_click_select_link_new_reading_and_disconnect(radio):
    h = radio
    status = h.client.get(BASE + '/status').json()
    assert status['host_matches'] and status['can_manage']
    scan = scan_candidate(h)
    assert scan['state'] == 'scanning' and scan['devices'][0]['supported']
    with Session(h.engine) as s:
        assert s.scalar(select(func.count()).select_from(RadioBinding)) == 0
        assert s.scalar(select(func.count()).select_from(TelemetryConnection)) == 0
    response = link(h, scan)
    assert response.status_code == 200, response.text
    linked = response.json()
    assert linked['status'] == 'awaiting_reading'
    scope = Scope(h.own.org, h.own.facility, linked['connection_id'])
    assert h.edge.evidence(scope)['items'] == []
    assert link(h, scan).json()['id'] == linked['id']
    h.runtime.captures['ble'].queue.put(decode_bthome(ADDRESS, bytes.fromhex('4002C40903BF13'), NOW()))
    h.runtime._tick()
    current = h.client.get(BASE + '/connections').json()['connections'][0]
    assert current['status'] == 'receiving'
    detail = h.client.get('/api/v1/cultivation-intelligence/rooms/' + h.own.room).json()
    temperatures = [r for r in detail['edge_latest']['readings'] if r['metric'] == 'temperature']
    assert temperatures[0]['value'] == 25
    before = h.edge.diagnostics(scope)['scope_rows']
    response = h.client.post(BASE + '/connections/' + linked['id'] + '/disconnect', json={'version': linked['version']})
    assert response.status_code == 200
    h.runtime.captures['ble'].queue.put(decode_bthome(ADDRESS, bytes.fromhex('4002C80903BF13'), NOW()))
    h.runtime._tick()
    assert h.edge.diagnostics(scope)['scope_rows'] == before
    assert h.client.get(BASE + '/connections').json()['connections'][0]['status'] == 'disconnected'


def test_exact_scope_owner_and_readonly_denials(radio):
    h = radio
    scan = scan_candidate(h)
    assert link(h, scan, room_id=h.other.room).status_code == 404
    assert link(h, scan, ownership_confirmed=False).status_code == 422
    assert h.client.post(BASE + '/scans', json={'receiver_id':'ble','authorized':False}).status_code == 422
    h.state['context'] = RequestContext(h.other.user, h.other.org, h.other.facility, 'admin')
    assert h.client.get(BASE + '/status').json()['receivers'] == []
    assert h.client.get(BASE + '/scans/' + scan['id']).status_code == 403
    h.state['context'] = RequestContext(h.own.user, h.own.org, h.own.facility, 'read_only')
    assert h.client.get(BASE + '/status').json()['can_manage'] is False
    assert h.client.get(BASE + '/scans/' + scan['id']).status_code == 403
    assert link(h, scan).status_code == 403


def test_encrypted_candidate_not_linkable_and_expiry(radio):
    h = radio
    scan = scan_candidate(h, payload='41AABB')
    assert scan['devices'][0]['reason'] == 'encrypted_requires_supported_pairing'
    assert link(h, scan).status_code == 409
    h.runtime.scan['expiry'] = 0
    assert h.client.get(BASE + '/scans/' + scan['id']).status_code == 409
    assert not h.runtime.candidates


def test_singleton_scan_and_cancellation(radio):
    h = radio
    scan = scan_candidate(h)
    assert h.client.post(BASE+'/scans', json={'receiver_id':'ble','authorized':True}).status_code == 409
    assert h.client.post(BASE+'/scans/'+scan['id']+'/stop', json={}).json()['state'] == 'stopped'
    h.runtime._tick()
    assert not h.runtime.captures


def test_config_does_not_accept_request_like_paths_or_unknown_settings(tmp_path):
    assert load_config('') is None
    p = tmp_path/'config.json'
    for value in [{'enabled':True,'secret':'no'}, {'enabled':1}, {'enabled':False,'other':'no'}]:
        p.write_text(json.dumps(value))
        with pytest.raises(RadioConfigError):load_config(str(p))
    p.write_text('{"enabled":false,"enabled":false}')
    with pytest.raises(RadioConfigError):load_config(str(p))
    p.write_text('{"enabled":false}')
    assert load_config(str(p)) is None


def test_postcommit_response_loss_replays_same_evidence(radio):
    h = radio
    scan = scan_candidate(h)
    linked = link(h, scan).json()
    real_ingest = h.edge.ingest
    calls = []
    def lose_first(*args, **kwargs):
        result = real_ingest(*args, **kwargs)
        calls.append(result)
        if len(calls) == 1: raise OSError('synthetic response loss')
        return result
    h.edge.ingest = lose_first
    h.runtime.captures['ble'].queue.put(decode_bthome(ADDRESS, bytes.fromhex('4002C40903BF13'), NOW()))
    h.runtime._tick()
    assert linked['id'] in h.runtime.backlog
    h.runtime._tick()
    assert linked['id'] not in h.runtime.backlog
    assert calls[0]['accepted'] == 2 and calls[1]['duplicates'] == 2
    assert h.runtime.binding_status(linked['id'])['status'] == 'receiving'


def test_packet_repeat_does_not_manufacture_new_sample(radio):
    h = radio
    scan = scan_candidate(h)
    linked = link(h, scan).json()
    frame = decode_bthome(ADDRESS, bytes.fromhex('40000102C40903BF13'), NOW())
    h.runtime.captures['ble'].queue.put(frame)
    h.runtime._tick()
    scope = Scope(h.own.org, h.own.facility, linked['connection_id'])
    before = h.edge.diagnostics(scope)['scope_rows']
    h.runtime.last_sample[linked['id']] = -1000
    h.runtime.captures['ble'].queue.put(frame)
    h.runtime._tick()
    assert h.edge.diagnostics(scope)['scope_rows'] == before


def test_same_facility_other_user_cannot_take_scan(radio):
    h = radio
    scan = scan_candidate(h)
    from modules.coman.models import AppUser
    from uuid import uuid4
    uid = str(uuid4())
    with Session(h.engine) as s, s.begin():
        s.add(AppUser(id=uid, organization_id=h.own.org, username=uid, normalized_username=uid,
                      password_hash='test-only', role='admin'))
    h.state['context'] = RequestContext(uid, h.own.org, h.own.facility, 'admin')
    assert h.client.get(BASE + '/scans/' + scan['id']).status_code == 404
    assert link(h, scan).status_code == 404


def test_known_decoder_arguments_never_enable_general_capture(radio):
    from modules.cultivation.radio.transport import command
    from dataclasses import replace
    r = replace(radio.receiver, id='rtl433', kind='rtl433', packages='', frequency=915000000)
    args = command(r)
    assert args[1:] == ['-c','0','-d','0','-f','915000000','-R','0','-R','113','-F','json','-M','utc']
    assert '-S' not in args and '-w' not in args


def test_startup_does_not_capture_without_a_scan_or_approved_binding(radio):
    radio.runtime._tick()
    assert not radio.runtime.captures
    assert not radio.runtime.candidates
    with Session(radio.engine) as session:
        assert session.scalar(select(func.count()).select_from(RadioBinding)) == 0


def test_revoked_canonical_connection_stops_future_radio_evidence(radio):
    h = radio
    linked = link(h, scan_candidate(h)).json()
    scope = Scope(h.own.org, h.own.facility, linked['connection_id'])
    with Session(h.engine) as session, session.begin():
        row = session.get(TelemetryConnection, linked['connection_id'])
        row.status = 'revoked'
        row.revoked_at = NOW()
    # End discovery so the receiver has no remaining authorized purpose.
    h.runtime.scan['deadline'] = 0
    h.runtime._tick()
    assert not h.runtime.captures
    assert h.edge.evidence(scope)['items'] == []


def test_unverified_receiver_cannot_report_successful_empty_scan(radio):
    h = radio
    started = h.client.post(BASE+'/scans', json={'receiver_id':'ble','authorized':True}).json()
    h.runtime._tick()
    h.runtime.captures['ble'].ready = False
    h.runtime.scan['state'] = 'starting'
    h.runtime.scan['deadline'] = 0
    h.runtime._tick()
    result = h.client.get(BASE+'/scans/'+started['id']).json()
    assert result['state'] == 'failed'
    assert result['error_code'] == 'receiver_not_confirmed'


def test_subghz_discovery_window_covers_minute_scale_reports(radio):
    from dataclasses import replace
    from time import monotonic
    h = radio
    receiver = replace(h.receiver, id='rtl433', kind='rtl433', packages='', frequency=915000000)
    h.runtime.config = replace(h.runtime.config, receivers=(receiver,))
    response = h.client.post(BASE+'/scans', json={'receiver_id':'rtl433','authorized':True})
    assert response.status_code == 200
    assert 80 < h.runtime.scan['deadline'] - monotonic() <= 90
    assert h.runtime.scan['expiry'] - monotonic() <= 255


def test_backend_error_does_not_disclose_local_paths_or_raw_frames(radio):
    h = radio
    h.receiver = Receiver('ble','ble','Bluetooth','C:/private/missing.exe','0'*64)
    from dataclasses import replace
    h.runtime.config = replace(h.runtime.config, receivers=(h.receiver,))
    response = h.client.post(BASE+'/scans', json={'receiver_id':'ble','authorized':True})
    assert response.status_code == 503
    assert 'private' not in response.text and 'missing.exe' not in response.text


def test_unknown_metadata_never_becomes_supported_bthome_measurement():
    event = decode_bthome(ADDRESS, bytes.fromhex('4002C40960FF'), NOW(), name='<b>untrusted</b>')
    assert not event.supported and not event.measurements
    assert '<' not in event.name and '>' not in event.name


def test_new_administrator_reapproves_without_rewriting_original_creator(radio):
    from modules.coman.models import AppUser
    from uuid import uuid4
    h = radio
    linked = link(h, scan_candidate(h)).json()
    assert h.client.post(BASE+'/connections/'+linked['id']+'/disconnect', json={'version':1}).status_code == 200
    replacement = str(uuid4())
    with Session(h.engine) as session, session.begin():
        session.get(AppUser, h.own.user).active = False
        session.add(AppUser(id=replacement, organization_id=h.own.org, username=replacement,
            normalized_username=replacement, password_hash='unusable-test', role='admin', active=True))
    h.runtime.scan['deadline'] = 0
    h.state['context'] = RequestContext(replacement, h.own.org, h.own.facility, 'admin')
    reapproved = link(h, scan_candidate(h))
    assert reapproved.status_code == 200 and reapproved.json()['id'] == linked['id']
    with Session(h.engine) as session:
        row = session.get(RadioBinding, linked['id'])
        assert row.created_by == h.own.user and row.authorized_by == replacement
    h.runtime.captures['ble'].queue.put(decode_bthome(ADDRESS, bytes.fromhex('4002C40903BF13'), NOW()))
    h.runtime._tick()
    assert h.runtime.binding_status(linked['id'])['status'] == 'receiving'
