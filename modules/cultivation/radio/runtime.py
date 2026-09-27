"""Bounded host-local radio collection. Discovery previews never become history."""
from datetime import datetime, timezone, timedelta
from queue import Empty
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4
import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session
from modules.coman.models import AppUser, Facility, Organization
from ..intelligence_models import TelemetryConnection, CultivationDevice
from ..context_resolution import build_resolver
from ..edge_store import Scope
from ..gateway import configured_edge
from ..telemetry import utc
from .models import RadioBinding
from .transport import NativeCapture

class RadioStateError(ValueError):
    pass

def now_utc():
    return datetime.now(timezone.utc)

class RadioRuntime:
    def __init__(self, engine, config, *, capture_factory=NativeCapture, edge_factory=configured_edge):
        self.engine, self.config = engine, config
        self.capture_factory, self.edge_factory = capture_factory, edge_factory
        self.lock = RLock()
        self.stop_event = Event()
        self.thread = None
        self.captures = {}
        self.receiver_errors = {}
        self.scan = None
        self.candidates = {}
        self.delivery = {}
        self.retry_at = {}
        self.error_code = None
        self.last_sample = {}
        self.last_packet = {}
        self.backlog = {}
        self.overflow = 0

    def matches(self, org, facility):
        return self.config and self.config.organization_id == org and self.config.facility_id == facility

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return self
            self.stop_event.clear()
            self.thread = Thread(target=self._run, name='cultivation-radio', daemon=True)
            self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=8)
        return not (self.thread and self.thread.is_alive())

    def start_scan(self, owner, receiver_id):
        with self.lock:
            receivers = {r.id: r for r in self.config.receivers}
            if receiver_id not in receivers:
                raise RadioStateError('receiver_not_configured')
            receivers[receiver_id].verify()
            if self.scan and self.scan['deadline'] > monotonic() and self.scan['state'] in ('starting', 'scanning'):
                raise RadioStateError('scan_already_running')
            self.candidates.clear()
            # Sub-GHz climate sensors often report only once a minute. A short
            # BLE discovery window is not a suitable acquisition promise for them.
            duration = 90 if receivers[receiver_id].kind == 'rtl433' else 15
            self.scan = {'id': str(uuid4()), 'owner': owner, 'receiver_id': receiver_id,
                         'state': 'starting', 'deadline': monotonic() + duration,
                         'expiry': monotonic() + duration + 165,
                         'expires_at': (now_utc() + timedelta(seconds=duration + 165)).isoformat(),
                         'error_code': None}
            return self.scan_view(owner, self.scan['id'])

    def _owned_scan(self, owner, identity):
        if not self.scan or self.scan['id'] != identity or self.scan['owner'] != owner:
            raise LookupError('scan_not_found')
        if self.scan['expiry'] < monotonic():
            self.candidates.clear()
            raise RadioStateError('scan_expired')
        return self.scan

    def scan_view(self, owner, identity):
        with self.lock:
            scan = self._owned_scan(owner, identity)
            return {k: scan[k] for k in ('id', 'receiver_id', 'state', 'expires_at', 'error_code')} | {
                'devices': [self.candidate_view(key, row) for key, row in self.candidates.items()],
                'truncated': len(self.candidates) >= 64,
            }

    def stop_scan(self, owner, identity):
        with self.lock:
            scan = self._owned_scan(owner, identity)
            scan['deadline'], scan['state'] = 0, 'stopped'
            return self.scan_view(owner, identity)

    @staticmethod
    def candidate_view(key, item):
        event = item['event']
        return {'id': key, 'name': event.name, 'profile_id': event.profile, 'supported': event.supported,
                'reason': event.reason, 'device_hint': event.address[-6:], 'rssi_dbm': event.rssi,
                'last_seen_at': event.received_at.isoformat(), 'trust': 'unauthenticated_broadcast',
                'measurements': [{'metric': m.metric, 'value': m.value, 'unit': m.unit,
                                  'timestamp_basis': 'receiver_time'} for m in event.measurements]}

    def candidate(self, owner, scan_id, candidate_id):
        with self.lock:
            scan = self._owned_scan(owner, scan_id)
            item = self.candidates.get(candidate_id)
            if not item or (now_utc() - item['event'].received_at).total_seconds() > 90:
                raise RadioStateError('candidate_stale_scan_again')
            if not item['event'].supported:
                raise RadioStateError('candidate_not_supported')
            return scan['receiver_id'], item['event']

    def binding_status(self, identity):
        with self.lock:
            result = dict(self.delivery.get(identity, {'status': 'awaiting_reading', 'last_received_at': None}))
            if self.error_code:
                result['status'] = 'receiver_unavailable'
            return result

    def _bindings(self):
        with Session(self.engine) as session:
            rows = session.execute(select(RadioBinding, CultivationDevice.source_device_id).join(
                TelemetryConnection, (TelemetryConnection.id == RadioBinding.connection_id) &
                (TelemetryConnection.organization_id == RadioBinding.organization_id) &
                (TelemetryConnection.facility_id == RadioBinding.facility_id)).join(
                CultivationDevice, (CultivationDevice.id == RadioBinding.device_id) &
                (CultivationDevice.connection_id == RadioBinding.connection_id)).join(
                Facility, (Facility.id == RadioBinding.facility_id) &
                (Facility.organization_id == RadioBinding.organization_id)).join(
                Organization, Organization.id == RadioBinding.organization_id).join(
                AppUser, AppUser.id == RadioBinding.authorized_by).where(
                RadioBinding.organization_id == self.config.organization_id,
                RadioBinding.facility_id == self.config.facility_id, RadioBinding.active.is_(True),
                Organization.active.is_(True), Facility.active.is_(True), Facility.cultivation_enabled.is_(True),
                CultivationDevice.active.is_(True), AppUser.active.is_(True),
                TelemetryConnection.status == 'configured', TelemetryConnection.revoked_at.is_(None),
            ).limit(33)).all()
            if len(rows) > 32:
                raise RadioStateError('radio_binding_capacity')
            return [(b, source) for b, source in rows]

    def _record(self, receiver, event, bindings):
        with self.lock:
            scan = self.scan
            if scan and scan['receiver_id'] == receiver and scan['deadline'] > monotonic() and scan['state'] in ('starting', 'scanning'):
                key = hashlib.sha256((scan['id'] + '|' + event.profile + '|' + event.address).encode()).hexdigest()[:32]
                if key in self.candidates or len(self.candidates) < 64:
                    self.candidates[key] = {'event': event}
            if not event.supported:
                return
            for binding, source_id in bindings:
                if (binding.receiver_id, binding.profile_id, binding.source_address) != (receiver, event.profile, event.address):
                    continue
                if event.received_at < utc(binding.enabled_at):
                    continue
                signature = (event.packet_id, tuple((m.channel, m.value, m.unit) for m in event.measurements))
                if event.packet_id is not None and self.last_packet.get(binding.id) == signature:
                    continue
                if binding.id in self.backlog:
                    self.overflow += 1
                    continue
                if monotonic() - self.last_sample.get(binding.id, -1e9) < self.config.sample_seconds:
                    continue
                self.last_sample[binding.id] = monotonic()
                self.last_packet[binding.id] = signature
                event_id = 'radio:' + uuid4().hex
                self.backlog[binding.id] = [dict(event_id=event_id, source_device_id=source_id,
                    source_channel=m.channel, source_metric=m.metric, value=m.value, unit=m.unit,
                    observed_at=event.received_at.isoformat(), quality='valid') for m in event.measurements]

    def _flush(self, bindings):
        live = {b.id: b for b, _ in bindings}
        for identity in list(self.backlog):
            binding = live.get(identity)
            if binding is None:
                self.backlog.pop(identity, None)
                self.delivery[identity] = {'status': 'disabled', 'last_received_at': None}
                continue
            readings = self.backlog[identity]
            scope = Scope(self.config.organization_id, self.config.facility_id, binding.connection_id)
            try:
                store = self.edge_factory()
                with Session(self.engine) as session:
                    current = session.get(RadioBinding, identity)
                    if (not current or not current.active or current.version != binding.version
                            or any(datetime.fromisoformat(row['observed_at']) < utc(current.enabled_at) for row in readings)):
                        self.backlog.pop(identity, None)
                        continue
                    resolver = build_resolver(session, scope, max_gap_seconds=store.max_gap_seconds)
                    resolved = [resolver(scope, row) for row in readings]
                result = store.ingest(scope, readings, resolved=resolved)
                if not result.get('committed'):
                    raise RadioStateError('local_commit_not_confirmed')
                usable = bool(result['accepted'])
                if not usable and result['duplicates'] == len(readings) and all(resolved):
                    last = store.diagnostics(scope).get('last_valid_observed_at')
                    usable = bool(last and datetime.fromisoformat(last.replace('Z', '+00:00')) >= datetime.fromisoformat(readings[0]['observed_at']))
                with self.lock:
                    self.delivery[identity] = {'status': 'receiving' if usable else 'needs_review',
                        'last_received_at': readings[0]['observed_at'], 'timestamp_basis': 'receiver_time',
                        'trust': 'unauthenticated_broadcast'}
                    self.backlog.pop(identity, None)
            except Exception:
                with self.lock:
                    self.delivery[identity] = {'status': 'storage_or_mapping_unavailable', 'last_received_at': None}
                # Retry the same bounded batch. Radio loss before commit is not recoverable.

    def _tick(self):
        try:
            bindings = self._bindings()
            self.error_code = None
        except Exception:
            self.error_code = 'authorization_unavailable'
            bindings = []
        required = {b.receiver_id for b, _ in bindings}
        with self.lock:
            if self.error_code is None:
                active_ids = {b.id for b, _ in bindings}
                for identity in self.delivery.keys() - active_ids:
                    previous = self.delivery[identity]
                    self.delivery[identity] = {'status': 'disabled', 'last_received_at': previous.get('last_received_at')}
            if self.scan:
                if monotonic() > self.scan['expiry']:
                    self.candidates.clear()
                if self.scan['deadline'] > monotonic() and self.error_code is None:
                    required.add(self.scan['receiver_id'])
                elif self.scan['state'] in ('starting', 'scanning'):
                    self.scan['state'] = 'complete' if self.scan['state'] == 'scanning' and self.error_code is None else 'failed'
                    if self.scan['state'] == 'failed':
                        self.scan['error_code'] = self.error_code or 'receiver_not_confirmed'
            for rid in list(self.captures):
                if rid not in required:
                    self.captures.pop(rid).stop()
            for receiver in self.config.receivers:
                rid = receiver.id
                if rid not in required:
                    continue
                capture = self.captures.get(rid)
                if capture is None and monotonic() >= self.retry_at.get(rid, 0):
                    try:
                        capture = self.capture_factory(receiver)
                        capture.start()
                        self.captures[rid] = capture
                        self.receiver_errors.pop(rid, None)
                    except Exception:
                        capture = None
                        self.retry_at[rid] = monotonic() + 30
                if capture is None:
                    self.receiver_errors[rid] = 'receiver_unavailable'
                    if self.scan and self.scan['receiver_id'] == rid:
                        self.scan.update(state='failed', error_code='receiver_unavailable', deadline=0)
                    continue
                if not capture.alive():
                    self.receiver_errors[rid] = 'receiver_unavailable'
                    capture.stop()
                    self.captures.pop(rid, None)
                    self.retry_at[rid] = monotonic() + 30
                    if self.scan and self.scan['receiver_id'] == rid:
                        self.scan.update(state='failed', error_code='receiver_unavailable', deadline=0)
                    continue
                if capture.ready and self.scan and self.scan['receiver_id'] == rid and self.scan['state'] == 'starting':
                    self.scan['state'] = 'scanning'
                for _ in range(128):
                    try:
                        event = capture.queue.get_nowait()
                    except Empty:
                        break
                    self._record(rid, event, bindings)
        if self.error_code is None:
            self._flush(bindings)
        with self.lock:
            for binding, _ in bindings:
                if binding.receiver_id in self.receiver_errors:
                    previous = self.delivery.get(binding.id, {})
                    self.delivery[binding.id] = {'status': 'receiver_unavailable', 'last_received_at': previous.get('last_received_at')}

    def _run(self):
        try:
            while not self.stop_event.is_set():
                self._tick()
                self.stop_event.wait(2)
        except Exception:
            self.error_code = 'radio_runtime_failed'
        finally:
            with self.lock:
                for capture in self.captures.values():
                    capture.stop()
                self.captures.clear()
