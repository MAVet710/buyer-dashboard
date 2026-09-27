"""Bounded host collection into the canonical local EdgeStore. No equipment writes."""
from copy import deepcopy
from datetime import datetime,timezone
from threading import Event,RLock,Thread,BoundedSemaphore
from time import monotonic
from uuid import uuid4
import json
from sqlalchemy import select,or_,and_
from sqlalchemy.orm import Session
from backend.app.auth import RequestContext
from modules.coman.models import AppUser,Facility,Organization
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration
from ..intelligence_models import TelemetryConnection
from ..intelligence_service import IntelligenceService
from ..gateway import configured_edge
from ..context_resolution import build_resolver
from ..edge_store import Scope
from .aranet import AranetCloud
from .things_stack import ThingsStack,normalized_uplink
from .contracts import NetworkError,stamp,tts_addresses
from .mqtt import MqttCapture

class NetworkRuntime:
    def __init__(self,engine,config,encryption_key,*,edge=None,http=None,capture_factory=None):
        self.engine,self.config=engine,config
        self.credentials=IntegrationConfigurationService(engine,encryption_key)
        self.edge=edge;self.http=http;self.capture_factory=capture_factory or MqttCapture
        self.lock=RLock();self.stop_event=Event();self.thread=None
        self.previews={};self.captures={};self.backlog={};self.states={};self.busy=set()
        self.slots=BoundedSemaphore(2)

    def start(self):
        self.thread=Thread(target=self._run,name='cultivation-networks',daemon=True);self.thread.start()
        return self

    def _run(self):
        while not self.stop_event.wait(5):
            try:self.tick()
            except Exception:
                with self.lock:
                    for state in self.states.values():state['status']='collection_unavailable'

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=5)
        with self.lock:
            for capture,_version in self.captures.values():capture.stop()
            self.captures.clear();self.previews.clear()
        return not (self.thread and self.thread.is_alive()) and not self.busy

    def control(self,identity):
        with Session(self.engine) as s:
            item=s.execute(select(TelemetryConnection,IntegrationConfiguration,AppUser).join(
                IntegrationConfiguration,IntegrationConfiguration.id==TelemetryConnection.integration_configuration_id).join(
                AppUser,AppUser.id==IntegrationConfiguration.updated_by).where(TelemetryConnection.id==identity,
                TelemetryConnection.mode=='network',TelemetryConnection.revoked_at.is_(None),
                IntegrationConfiguration.provider=='cultivation_network')).first()
            if not item:raise NetworkError('connection_disabled')
            row,config,actor=item
            if not self.config.matches(row.organization_id,row.facility_id) or (config.organization_id,config.facility_id)!=(row.organization_id,row.facility_id):
                raise NetworkError('source_scope_mismatch')
            if not actor.active or actor.role.casefold() not in {'dev','admin'} or (actor.role.casefold()!='dev' and actor.organization_id!=row.organization_id):
                raise NetworkError('authorization_failed')
            if not s.scalar(select(Organization.active).where(Organization.id==row.organization_id)):
                raise NetworkError('authorization_failed')
            context=RequestContext(actor.id,row.organization_id,row.facility_id,actor.role)
            from backend.app.permissions import require_permission
            from backend.app.auth import require_facility_capability
            require_facility_capability(context,self.engine,'cultivation')
            require_permission(context,self.engine,'cultivation.manage_connections',session=s)
            data=json.loads(config.configuration_json)
            return {'id':identity,'version':row.version,'scope':Scope(row.organization_id,row.facility_id,identity),
                'context':context,'data':data,'config_id':config.id,'ciphertext':config.encrypted_secret,
                'stale_after_seconds':row.stale_after_seconds or 600}

    def adapter(self,control):
        try:key=self.credentials.cipher.decrypt(control['ciphertext'].encode()).decode()
        except Exception:raise NetworkError('credential_unavailable') from None
        data=control['data']
        if data['adapter']=='aranet_cloud':return AranetCloud(key,data['options'],self.http)
        if data['adapter']=='things_stack':return ThingsStack(key,data['options'],self.http)
        raise NetworkError('unsupported_adapter')

    def invalidate(self,identity):
        with self.lock:
            self.previews.pop(identity,None);self.backlog.pop(identity,None)
            old=self.captures.pop(identity,None)
            if old:old[0].stop()
            self.states[identity]={'status':'waiting_for_reading','next_at':0}

    def _job(self,identity,work):
        with self.lock:
            if identity in self.busy or not self.slots.acquire(blocking=False):
                return False
            self.busy.add(identity)
        def run():
            try:work()
            except NetworkError as exc:
                with self.lock:
                    state=self.states.setdefault(identity,{})
                    state.update(status=exc.code,next_at=monotonic()+(exc.retry_after or 300))
                    if identity in self.previews:
                        self.previews[identity].update(state='failed',error=exc.code)
            except Exception:
                with self.lock:
                    self.states.setdefault(identity,{}).update(status='collection_unavailable',next_at=monotonic()+300)
                    if identity in self.previews:self.previews[identity].update(state='failed',error='connection_unavailable')
            finally:
                with self.lock:self.busy.discard(identity)
                self.slots.release()
        Thread(target=run,name='cultivation-network-read',daemon=True).start()
        return True

    def discover(self,owner,org,facility,identity,version):
        control=self.control(identity)
        if (control['scope'].organization_id,control['scope'].facility_id,control['version'])!=(org,facility,version):
            raise NetworkError('configuration_changed')
        with self.lock:
            if identity in self.busy:raise NetworkError('connection_busy')
            if len(self.previews)>=8 and identity not in self.previews:raise NetworkError('preview_limit')
            old=self.previews.get(identity)
            if old and old['owner']!=owner and old['expires']>monotonic():raise NetworkError('preview_in_use')
            preview_id=str(uuid4())
            self.previews[identity]={'id':preview_id,'owner':owner,'org':org,'facility':facility,
                'version':version,'state':'connecting','devices':[],'truncated':False,'error':None,
                'expires':monotonic()+900,'listen_until':monotonic()+600}
        def work():
            result=self.adapter(control).discover()
            with self.lock:
                preview=self.previews.get(identity)
                if preview and preview['id']==preview_id:
                    preview.update(result,state='listening' if result['adapter']=='things_stack' else 'complete')
        if not self._job(identity,work):
            with self.lock:self.previews.pop(identity,None)
            raise NetworkError('connection_busy')
        return {'id':preview_id,'state':'connecting','preview_path':f'/api/v1/cultivation-networks/{identity}/previews/{preview_id}'}

    def preview(self,owner,org,facility,identity,version,preview_id):
        with self.lock:
            result=self.previews.get(identity)
            if not result or (result['id'],result['owner'],result['org'],result['facility'],result['version'])!=(preview_id,owner,org,facility,version) or result['expires']<=monotonic():
                raise NetworkError('preview_expired_or_changed')
            return deepcopy({key:result.get(key) for key in ('id','state','devices','adapter','transport','truncated','error','history_recovery_supported')})

    def _queue(self,control,readings,unmapped=0):
        at=control['data'].get('approved_at')
        if not at:return
        prefix='aranet:' if control['data']['adapter']=='aranet_cloud' else 'tts:'
        selected={(prefix+d['source_id'],stream['source_channel'],stream['source_metric']):stream['unit']
                  for d in control['data']['devices'] for stream in d['streams']}
        cutoff=datetime.fromisoformat(at)
        rows=[]
        for row in readings:
            unit=selected.get((row['source_device_id'],row['source_channel'],row['source_metric']))
            if unit is None:
                unmapped+=1;continue
            if unit!=row['unit']:raise NetworkError('source_units_changed')
            if datetime.fromisoformat(stamp(row['observed_at']))>=cutoff:rows.append(row)
        with self.lock:
            state=self.states.setdefault(control['id'],{})
            state['last_contact_at']=datetime.now(timezone.utc).isoformat()
            state['unmapped_readings']=state.get('unmapped_readings',0)+unmapped
            if not rows:return
            pending=self.backlog.get(control['id'])
            if pending:
                state['dropped_readings']=state.get('dropped_readings',0)+len(rows)
                return
            if len(rows)>5000:raise NetworkError('reading_limit')
            self.backlog[control['id']]={'version':control['version'],'ciphertext':control['ciphertext'],'rows':rows}

    def _persist(self,control):
        identity=control['id']
        with self.lock:pending=self.backlog.get(identity)
        if not pending:return
        if pending['version']!=control['version'] or pending['ciphertext']!=control['ciphertext'] or not control['data'].get('enabled'):
            with self.lock:self.backlog.pop(identity,None)
            return
        edge=self.edge or configured_edge()
        rows=pending['rows'][:min(500,edge.max_batch)]
        with Session(self.engine) as s,s.begin():
            IntelligenceService(self.engine,control['context']).authorize(write=True,connections=True,session=s)
            connection=s.scalar(select(TelemetryConnection).where(TelemetryConnection.id==identity).with_for_update())
            config=s.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.id==control['config_id']).with_for_update())
            if connection is None or config is None or connection.version!=pending['version'] or config.encrypted_secret!=pending['ciphertext'] or connection.revoked_at:
                raise NetworkError('configuration_changed')
            data=json.loads(config.configuration_json)
            if not data.get('enabled') or config.updated_by!=control['context'].user_id:raise NetworkError('connection_disabled')
            resolver=build_resolver(s,control['scope'],max_gap_seconds=edge.max_gap_seconds)
            resolved=[resolver(control['scope'],row) for row in rows]
            result=edge.ingest(control['scope'],rows,resolved=resolved)
            if result.get('committed') is not True:raise NetworkError('storage_unavailable')
        observed=edge.diagnostics(control['scope']).get('last_valid_observed_at')
        with self.lock:
            if self.backlog.get(identity) is pending:
                pending['rows']=pending['rows'][len(rows):]
                if not pending['rows']:self.backlog.pop(identity,None)
            state=self.states.setdefault(identity,{})
            now=datetime.now(timezone.utc).isoformat()
            state.update(last_received_at=now,status='needs_review' if result['conflicts'] or result['quarantined'] or result['pending'] else 'receiving')
            if observed:state['last_observed_at']=observed
            if any(row.get('quality')!='valid' for row in rows):state['status']='needs_review'
            state['accepted_readings']=state.get('accepted_readings',0)+result['accepted']

    def health(self,identity):
        with self.lock:
            state=deepcopy(self.states.get(identity,{'status':'waiting_for_reading'}))
        state.pop('next_at',None)
        state.pop('subscription_started_at',None)
        last=state.get('last_observed_at')
        if state.get('status')=='receiving' and last:
            if (datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()>state.get('stale_after_seconds',600):
                state['status']='stale_readings'
        state['history_recovery_supported']=False
        state['qos_replay_guaranteed']=False
        return state

    def _poll(self,control):
        result=self.adapter(control).latest(control['data']['devices'])
        self._queue(control,result['readings'],result['unmapped_readings'])
        with self.lock:
            self.states.setdefault(control['id'],{})['next_at']=monotonic()+self.config.interval_seconds

    def _mqtt(self,control,preview):
        identity=control['id']
        with self.lock:entry=self.captures.get(identity)
        if entry and (entry[1]!=control['version'] or not entry[0].alive()):
            capture,_=entry;capture.stop()
            with self.lock:
                self.captures.pop(identity,None)
                if capture.failed:
                    self.states.setdefault(identity,{}).update(status=capture.error or 'connection_unavailable',next_at=monotonic()+300)
                    if preview:preview.update(state='failed',error=capture.error or 'connection_unavailable')
                    return
            entry=None
        if entry is None:
            capture=self.capture_factory(self.config,self.adapter(control).mqtt_settings()).start()
            with self.lock:
                self.captures[identity]=(capture,control['version'])
                self.states.setdefault(identity,{})['subscription_started_at']=monotonic()
        else:capture=entry[0]
        if not capture.ready:
            with self.lock:started=self.states.get(identity,{}).get('subscription_started_at',monotonic())
            if monotonic()-started>45:
                capture.stop()
                with self.lock:self.captures.pop(identity,None)
                raise NetworkError('subscription_timeout')
        collected=[]
        options=control['data']['options']
        application=options['application_id'];tenant=tts_addresses(options)[2]
        username=application+'@'+tenant
        for _ in range(20):
            if capture.queue.empty():break
            envelope=capture.queue.get_nowait()
            try:
                event=normalized_uplink(envelope['payload'],application,envelope['topic'],username)
            except (NetworkError,KeyError,TypeError):
                with self.lock:
                    state=self.states.setdefault(identity,{})
                    state['unmapped_messages']=state.get('unmapped_messages',0)+1
                continue
            with self.lock:
                if preview and self.previews.get(identity) is preview:
                    for device in preview['devices']:
                        if device['id']==event['device_id']:
                            device.update(streams=event['streams'],status='ready')
            if control['data'].get('enabled'):collected.extend(event['readings'])
        if collected:self._queue(control,collected)
        with self.lock:
            state=self.states.setdefault(identity,{})
            state['dropped_messages']=capture.dropped
            if capture.ready:state['transport_connected']=True
            if preview and preview['listen_until']<=monotonic():preview['state']='complete'

    def tick(self):
        with self.lock:
            for identity,preview in list(self.previews.items()):
                if preview['expires']<=monotonic():self.previews.pop(identity,None)
                elif preview['state']=='listening' and preview['listen_until']<=monotonic():preview['state']='complete'
        clauses=[and_(TelemetryConnection.organization_id==org,TelemetryConnection.facility_id==facility) for org,facility in self.config.scopes]
        with Session(self.engine) as s:
            identities=s.scalars(select(TelemetryConnection.id).where(TelemetryConnection.mode=='network',
                or_(*clauses)).order_by(TelemetryConnection.id).limit(self.config.max_connections+1)).all()
        if len(identities)>self.config.max_connections:raise NetworkError('host_connection_capacity')
        required=set()
        for identity in identities:
            try:
                control=self.control(identity)
                with self.lock:
                    preview=self.previews.get(identity)
                    listening=bool(preview and preview['state']=='listening' and preview['listen_until']>monotonic())
                    pending=identity in self.backlog
                    state=self.states.setdefault(identity,{'status':'waiting_for_reading','next_at':0})
                    state['stale_after_seconds']=control['stale_after_seconds']
                    wait=state.get('next_at',0)>monotonic()
                if not control['data'].get('enabled') and not listening:continue
                if pending:self._persist(control)
                if wait:continue
                if control['data']['adapter']=='things_stack':
                    required.add(identity);self._mqtt(control,preview if listening else None)
                elif control['data'].get('enabled') and not pending:
                    self._job(identity,lambda c=control:self._poll(c))
            except Exception as exc:
                with self.lock:
                    code=exc.code if isinstance(exc,NetworkError) else 'collection_unavailable'
                    self.states.setdefault(identity,{}).update(status=code,next_at=monotonic()+60)
        with self.lock:
            for identity in self.captures.keys()-required:
                self.captures.pop(identity)[0].stop()
