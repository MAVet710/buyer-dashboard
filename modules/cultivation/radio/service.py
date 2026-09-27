"""Explicit human selection creates canonical device links, never radio guesses."""
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from ..intelligence_service import IntelligenceService
from ..intelligence_models import TelemetryConnection, CultivationDevice, CultivationSensor, DeviceMapping, EnvironmentalZone
from ..models import CultivationRoom
from ..telemetry import utc
from .models import RadioBinding
from .runtime import RadioStateError

class RadioService(IntelligenceService):
    def __init__(self, engine, context, runtime):
        super().__init__(engine, context)
        self.runtime = runtime

    def host(self):
        if not self.runtime or not self.runtime.matches(self.org, self.facility):
            raise HTTPException(403, 'Radio discovery is not enabled for this facility host.')
        return self.runtime

    def manage(self, session=None):
        self.authorize(write=True, connections=True, session=session)
        return self.host()

    def status(self):
        self.authorize()
        match = bool(self.runtime and self.runtime.matches(self.org, self.facility))
        can_manage = False
        if match:
            try:
                self.authorize(write=True, connections=True)
                can_manage = True
            except HTTPException:
                pass
        return {'enabled': match, 'host_matches': match, 'can_manage': can_manage,
                'receivers': [{'id': r.id, 'kind': r.kind, 'band_label': r.band,
                               'available': r.id not in self.runtime.receiver_errors,
                               'reason': self.runtime.receiver_errors.get(r.id, 'Configured. Start a scan to verify reception.')}
                              for r in self.runtime.config.receivers] if match else [],
                'limitations': ['Discovery runs at the configured facility PC, not your phone.',
                    'Radio names and signal strength do not prove ownership or identity.',
                    'No encrypted decoding, equipment commands or general Wi-Fi capture.',
                    'A physical receiver and supported sensors must be present.'],
                'runtime_error': self.runtime.error_code if match else None}

    def start_scan(self, payload):
        with Session(self.engine) as session, session.begin():
            runtime = self.manage(session)
        return runtime.start_scan(self.context.user_id, payload.receiver_id)

    def scan(self, identity, stop=False):
        runtime = self.manage()
        return runtime.stop_scan(self.context.user_id, identity) if stop else runtime.scan_view(self.context.user_id, identity)

    def connect(self, payload):
        with Session(self.engine) as session, session.begin():
            runtime = self.manage(session)
            receiver, candidate = runtime.candidate(self.context.user_id, payload.scan_id, payload.candidate_id)
            room = self.get(session, CultivationRoom, payload.room_id)
            if not room.active:
                raise ValueError('Room is inactive.')
            if payload.zone_id:
                zone = self.get(session, EnvironmentalZone, payload.zone_id)
                if zone.room_id != room.id or not zone.active:
                    raise ValueError('Select an active zone in this room.')
            old = session.scalar(select(RadioBinding).where(*self.scope(RadioBinding),
                RadioBinding.receiver_id == receiver, RadioBinding.source_address == candidate.address).with_for_update())
            at = datetime.now(timezone.utc)
            if old:
                connection = self.get(session, TelemetryConnection, old.connection_id)
                if connection.status != 'configured' or connection.revoked_at:
                    raise RadioStateError('connection_revoked')
                device = self.get(session, CultivationDevice, old.device_id)
                if not device.active or old.profile_id != candidate.profile:
                    raise RadioStateError('source_identity_changed')
                mapping = session.scalar(select(DeviceMapping).where(*self.scope(DeviceMapping),
                    DeviceMapping.device_id == old.device_id).order_by(DeviceMapping.effective_at.desc()).limit(1))
                if old.active:
                    if mapping is None or mapping.room_id != room.id or mapping.zone_id != payload.zone_id:
                        raise RadioStateError('already_linked_review_room_mapping')
                    return self.payload(old, device, mapping)
                total = session.scalar(select(func.count()).select_from(RadioBinding).where(*self.scope(RadioBinding), RadioBinding.active.is_(True)))
                if total >= 32:
                    raise RadioStateError('radio_binding_capacity')
                old.active, old.enabled_at, old.version = True, at, old.version + 1
                old.authorized_by = self.context.user_id
                binding = old
            else:
                total = session.scalar(select(func.count()).select_from(RadioBinding).where(*self.scope(RadioBinding), RadioBinding.active.is_(True)))
                if total >= 32:
                    raise RadioStateError('radio_binding_capacity')
                # The existing file lane is host-local evidence. The radio binding
                # separately governs acquisition and never creates an HTTP token.
                connection = self.new(TelemetryConnection, provider='json', mode='file',
                    label='Radio ' + payload.display_name + ' ' + payload.candidate_id[:8],
                    created_by=self.context.user_id, status='configured', version=1)
                session.add(connection)
                session.flush()
                device = self.new(CultivationDevice, connection_id=connection.id,
                    source_device_id='radio:' + candidate.profile + ':' + candidate.address,
                    display_name=payload.display_name, active=True, version=1)
                session.add(device)
                session.flush()
                for m in candidate.measurements:
                    session.add(self.new(CultivationSensor, device_id=device.id, source_channel=m.channel,
                        source_metric=m.metric, source_unit=m.unit, metric=m.metric, unit=m.unit))
                binding = self.new(RadioBinding, receiver_id=receiver, source_address=candidate.address,
                    profile_id=candidate.profile, connection_id=connection.id, device_id=device.id,
                    created_by=self.context.user_id, authorized_by=self.context.user_id, created_at=at, enabled_at=at, active=True, version=1)
                session.add(binding)
            mapping = self.new(DeviceMapping, device_id=device.id, room_id=room.id, zone_id=payload.zone_id,
                               effective_at=at, created_by=self.context.user_id)
            session.add(mapping)
            session.flush()
            self.audit(session, binding, 'radio_source_approved', {'profile': candidate.profile,
                'room_id': room.id, 'zone_id': payload.zone_id, 'timestamp_basis': 'receiver_time',
                'trust': 'unauthenticated_broadcast', 'ownership_confirmed': True})
            return self.payload(binding, device, mapping)

    def payload(self, binding, device, mapping):
        state = self.runtime.binding_status(binding.id) if self.runtime else {'status': 'receiver_unavailable', 'last_received_at': None}
        if not binding.active:
            state = {'status': 'disconnected', 'last_received_at': state.get('last_received_at')}
        elif state.get('last_received_at') and datetime.fromisoformat(state['last_received_at']) < utc(binding.enabled_at):
            state = {'status': 'awaiting_reading', 'last_received_at': None}
        elif state.get('last_received_at') and state.get('status') == 'receiving':
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(state['last_received_at'])).total_seconds()
            if age > 300:
                state['status'] = 'stale'
        room_id = mapping.room_id if mapping else None
        return {'id': binding.id, 'name': device.display_name, 'connection_id': binding.connection_id,
                'device_id': binding.device_id, 'room_id': room_id, 'zone_id': mapping.zone_id if mapping else None,
                'profile_id': binding.profile_id, 'version': binding.version, **state,
                'timestamp_basis': 'receiver_time', 'trust': 'unauthenticated_broadcast',
                'return_route': '/cultivation?room=' + room_id if room_id else '/cultivation'}

    def connections(self):
        self.authorize()
        self.host()
        with Session(self.engine) as session:
            rows = session.execute(select(RadioBinding, CultivationDevice).join(CultivationDevice,
                CultivationDevice.id == RadioBinding.device_id).where(*self.scope(RadioBinding)).limit(33)).all()
            ids = [b.device_id for b, _ in rows[:32]]
            mappings = session.scalars(select(DeviceMapping).where(*self.scope(DeviceMapping),
                DeviceMapping.device_id.in_(ids)).order_by(DeviceMapping.effective_at.desc()).limit(3201)).all()
            if len(mappings) > 3200:
                raise RadioStateError('mapping_capacity')
            latest = {}
            for m in mappings:
                latest.setdefault(m.device_id, m)
            return {'connections': [self.payload(b, d, latest.get(b.device_id)) for b, d in rows[:32]], 'truncated': len(rows) > 32}

    def disconnect(self, identity, version):
        with Session(self.engine) as session, session.begin():
            self.manage(session)
            binding = self.get(session, RadioBinding, identity, lock=True)
            self.bump(session, binding, version)
            binding.active = False
            self.audit(session, binding, 'radio_source_disconnected', {'evidence_preserved': True})
            return {'id': binding.id, 'version': binding.version, 'status': 'disconnected'}
