"""Authorized bounded imports into the single local edge evidence store.

No live provider transport, raw cloud drain, equipment commands or second spool.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from .adapters.normalized import NormalizedExportAdapter
from .edge_store import EdgeStore, Scope
from .intelligence_models import TelemetryConnection, CultivationDevice, DeviceMapping
from .intelligence_service import IntelligenceService, Input, connection_payload
from .telemetry import TelemetryConflict, utc
from .metrics import canonical_metric
from typing import Literal

class ImportMapping(Input):
    source_channel: str = Field(min_length=1,max_length=120)
    source_metric: str = Field(min_length=1,max_length=120)
    metric: str = Field(min_length=1,max_length=64)
    unit: str = Field(min_length=1,max_length=32)

class ImportPreview(Input):
    format: Literal['json','csv']
    content: str = Field(max_length=1048576)
    mappings: list[ImportMapping] = Field(max_length=500)

class ImportCommit(ImportPreview):
    digest: str = Field(min_length=64,max_length=64,pattern='^[a-f0-9]+$')

class DrainInput(Input):
    limit: int = Field(default=100,ge=1,le=500)

class WindowInput(Input):
    start: datetime
    end: datetime
    @field_validator('start','end')
    @classmethod
    def utc_time(cls,value):
        if value.tzinfo is None or value.utcoffset()!=timedelta(0):raise ValueError('Window timestamps require UTC.')
        return value
    @model_validator(mode='after')
    def ordered(self):
        if self.end<=self.start:raise ValueError('End must follow start.')
        return self

class RetentionInput(DrainInput):
    before: datetime
    execute: bool = False
    @field_validator('before')
    @classmethod
    def cutoff(cls,value):
        if value.tzinfo is None or value.utcoffset()!=timedelta(0) or value>datetime.now(timezone.utc):raise ValueError('Retention cutoff must be a past UTC timestamp.')
        return value


def _stream_id(connection_id,device_id,channel):
    return hashlib.sha256(json.dumps([connection_id,device_id,channel],separators=(',',':')).encode()).hexdigest()

def configured_edge(path=None, *, read_only=False):
    path=path if path is not None else os.environ.get('CULTIVATION_EDGE_PATH','')
    if not path:
        raise HTTPException(503,'Local cultivation evidence storage is not configured.')
    options={}
    # Host configuration only. Browsers cannot select files or quotas.
    for name,ceiling in {'max_scope_rows':1000000,'max_scope_bytes':1073741824,'max_disk_bytes':4294967296,'max_batch':500,'max_query_rows':100000,'max_gap_seconds':86400,'bucket_seconds':86400,'max_window_seconds':2678400}.items():
        raw=os.environ.get('CULTIVATION_EDGE_'+name.upper())
        if raw is not None:
            try:value=int(raw)
            except ValueError:raise HTTPException(503,'Invalid local evidence limit configuration.') from None
            if not 1<=value<=ceiling:raise HTTPException(503,'Invalid local evidence limit configuration.')
            options[name]=value
    return EdgeStore(path,read_only=read_only,**options)

class TelemetryGatewayService(IntelligenceService):
    def __init__(self,engine,context,*,edge=None,path=None,archive_dir=None):
        super().__init__(engine,context)
        self._edge=edge
        self._path=path if path is not None else os.environ.get('CULTIVATION_EDGE_PATH','')
        self._archive_dir=archive_dir if archive_dir is not None else os.environ.get('CULTIVATION_EDGE_ARCHIVE_DIR','')

    def edge(self):
        if self._edge is None:self._edge=configured_edge(self._path)
        return self._edge

    def _scope(self,identity):return Scope(self.org,self.facility,identity)

    def _resolver(self,s,connection_id):
        from .context_resolution import build_resolver
        gap=self._edge.max_gap_seconds if self._edge else int(os.environ.get('CULTIVATION_EDGE_MAX_GAP_SECONDS','300'))
        return build_resolver(s,self._scope(connection_id),max_gap_seconds=gap)

    def _parse(self,p):
        if len(p.content.encode('utf-8'))>1048576:raise ValueError('Export byte limit exceeded.')
        mappings=[m.model_dump() for m in p.mappings]
        for mapping in mappings:mapping['metric']=canonical_metric(mapping['metric'])
        # This browser format uses fixed explicit columns. Vendor exports must be
        # translated to this documented schema rather than guessed by field names.
        columns={k:k for k in NormalizedExportAdapter.required | NormalizedExportAdapter.optional}
        return NormalizedExportAdapter(columns=columns,metric_mappings=mappings,max_bytes=1048576,max_rows=500).parse(p.content,format=p.format)

    def _context_fingerprint(self,identity,resolved):
        return hashlib.sha256(json.dumps({'scope':[self.org,self.facility,identity],'resolved':resolved},sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def _digest(self,identity,version,p,context_fingerprint):
        # A changed configuration requires a new preview. Edge event identities
        # remain stable and preserve the first snapshots when replay is committed.
        payload={'scope':[self.org,self.facility,identity],'version':version,'context_fingerprint':context_fingerprint,**p.model_dump(exclude={'digest'})}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def preview(self,identity,payload):
        p=ImportPreview.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            connection=self.connection(s,identity) # authorization precedes adapter construction/parse
            parsed=self._parse(p);resolver=self._resolver(s,identity);scope=self._scope(identity)
            unknown=[];conflicts=[];resolved=[]
            for index,(raw,hint) in enumerate(zip(parsed['readings'],parsed['mapping_hints'])):
                snapshot=resolver(scope,raw) if hint else None
                resolved.append(snapshot)
                if not hint or not snapshot:unknown.append(index)
                elif snapshot['metric']!=hint['metric']:conflicts.append(index)
            from .preview_samples import sample_rows
            samples=sample_rows(s,self,parsed['readings'],parsed['mapping_hints'],resolved)
            fingerprint=self._context_fingerprint(identity,resolved)
            return {'digest':self._digest(identity,connection.version,p,fingerprint),'context_fingerprint':fingerprint,'rows':len(parsed['readings']),'unknown_channels':unknown,'conflicts':conflicts,'can_commit':not conflicts,'identity_conflict_check':'at_commit','sample_rows':samples,'samples_truncated':len(parsed['readings'])>20}

    def import_content(self,identity,payload):
        p=ImportCommit.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            connection=self.connection(s,identity)
            parsed=self._parse(p);resolver=self._resolver(s,identity);scope=self._scope(identity);resolved=[]
            for raw,hint in zip(parsed['readings'],parsed['mapping_hints']):
                snapshot=resolver(scope,raw) if hint else None
                if snapshot and snapshot['metric']!=hint['metric']:raise TelemetryConflict('Import metric mapping conflicts with registered sensor.')
                resolved.append(snapshot)
            fingerprint=self._context_fingerprint(identity,resolved)
            if p.digest!=self._digest(identity,connection.version,p,fingerprint):raise TelemetryConflict('Import content or attribution changed; preview again.')
            result=self.edge().ingest(scope,parsed['readings'],resolved=resolved)
            # Local durable commit is authoritative for raw evidence. Audit contains counts only.
            self.audit(s,connection,'local_export_imported',{k:result[k] for k in ('accepted','duplicates','conflicts','pending','quarantined')})
            return {'accepted':result['accepted'],
                    'duplicates':result['duplicates'],'conflicts':result['conflicts'],
                    'quarantined':result['quarantined'],'queued_for_mapping':result['pending'],'dispositions':result['items'],'raw_stays_local':True}

    def drain(self,identity,payload):
        p=DrainInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);self.connection(s,identity)
            edge=self.edge();scope=self._scope(identity)
            result=edge.retry_pending(scope,self._resolver(s,identity),limit=p.limit)
            start,end=self._window()
            aggregate=edge.rollup(scope,start,end)
            return {'processed':result['resolved'],'pending':result['pending'],'conflicts':0,'rollup':aggregate,'raw_stays_local':True,'cloud_publication':False}

    def health(self,identity):
        from .ingress_models import CultivationIngressGrant
        from .ingress import grant_payload
        from modules.operational_moats.models import ServiceAccount
        self.authorize()
        with Session(self.engine) as s:
            connection=self.get(s,TelemetryConnection,identity)
            last_import=self._last_imports(s,[identity]).get(identity)
            grants=s.execute(select(CultivationIngressGrant,ServiceAccount.active).join(ServiceAccount,ServiceAccount.id==CultivationIngressGrant.service_account_id).where(*self.scope(CultivationIngressGrant),CultivationIngressGrant.connection_id==identity).order_by(CultivationIngressGrant.created_at.desc()).limit(201)).all()
            grant_states=[grant_payload(r,active)['status'] for r,active in grants[:200]]
        diagnostics=self.edge().diagnostics(self._scope(identity)) if self._edge or self._path else None
        if diagnostics is not None:
            transport_status=self.edge().transport_status(self._scope(identity))
            diagnostics={**diagnostics,'last_push_received_at':transport_status['last_committed_at'],'last_push_batch_id':transport_status['last_batch_id'],'transport':transport_status}
        last_push=diagnostics.get('last_push_received_at') if diagnostics else None
        observed=diagnostics.get('last_valid_observed_at') if diagnostics else None
        transport='disabled' if connection.mode!='push' else 'revoked' if connection.revoked_at else 'awaiting' if not last_push else 'received'
        if transport=='received' and connection.stale_after_seconds:
            try:
                received=datetime.fromisoformat(last_push.replace('Z','+00:00'))
                transport='stale' if (datetime.now(timezone.utc)-utc(received)).total_seconds()>connection.stale_after_seconds else 'receiving'
            except (ValueError,TypeError,AttributeError):transport='unknown'
        freshness='unknown'
        if observed and connection.stale_after_seconds:
            try:
                at=datetime.fromisoformat(observed.replace('Z','+00:00'))
                freshness='stale' if (datetime.now(timezone.utc)-utc(at)).total_seconds()>connection.stale_after_seconds else 'recent'
            except (ValueError,TypeError,AttributeError):pass
        return {'connection':{**connection_payload(connection),'last_import_at':last_import},'edge':diagnostics,
            'live_contract_status':'normalized_push' if connection.mode=='push' else 'blocked',
            'ingress':{'grant_state':'active' if 'active' in grant_states else 'unknown' if len(grants)>200 else 'revoked' if 'revoked' in grant_states else 'disabled' if 'disabled' in grant_states else 'expired' if grant_states else 'unprovisioned','grants_truncated':len(grants)>200,'transport_state':transport,'last_push_received_at':last_push,'last_push_batch_id':diagnostics.get('last_push_batch_id') if diagnostics else None},
            'freshness':{'basis':'connection_scope_not_room_condition','last_import_at':last_import,'last_received_at':diagnostics.get('last_received_at') if diagnostics else None,'last_valid_observed_at':observed,'observation_status':freshness,'sensor_freshness_status':'unknown','last_provider_contact_at':None,'live_connected':False}}

    def _window(self,start=None,end=None):
        if (start is None)!=(end is None):raise ValueError('Supply both start and end.')
        edge=self.edge()
        if start is None:
            now=datetime.now(timezone.utc).timestamp()
            end=datetime.fromtimestamp(int(now//edge.bucket_seconds)*edge.bucket_seconds,timezone.utc)
            buckets=min(86400//edge.bucket_seconds,edge.max_batch,edge.max_window_seconds//edge.bucket_seconds)
            if buckets<1:raise ValueError('Configured window must contain at least one bucket.')
            start=end-timedelta(seconds=buckets*edge.bucket_seconds)
        p=WindowInput(start=start,end=end)
        if any(t.timestamp()%edge.bucket_seconds for t in (p.start,p.end)) or (p.end-p.start).total_seconds()>min(edge.max_window_seconds,edge.max_batch*edge.bucket_seconds):
            raise ValueError('Window must use configured UTC bucket boundaries and fit configured limits.')
        return p.start,p.end

    def rollup(self,identity,payload):
        p=WindowInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);connection=self.get(s,TelemetryConnection,identity)
            start,end=self._window(p.start,p.end)
            result=self.edge().rollup(self._scope(identity),start,end)
            self.audit(s,connection,'local_rollup',result)
            return {**result,'raw_stays_local':True,'cloud_publication':False,'receiver_acknowledged':False}

    def maintenance(self,identity):
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);self.get(s,TelemetryConnection,identity)
            edge=self.edge()
            return {'edge':edge.diagnostics(self._scope(identity)),'configuration':{k:getattr(edge,k) for k in ('bucket_seconds','max_gap_seconds','max_window_seconds','max_batch','max_query_rows')},'archive_configured':bool(self._archive_dir),'retention_blocker':self._retention_blocker(),'automatic_collection':False,'cloud_publication':False,'receiver_acknowledged':False}

    def _retention_blocker(self):
        return 'requires_clean_verified_archive_and_resolved_evidence' if self._archive_dir else 'durable_aggregate_receiver_not_configured'

    def archive(self,identity,payload):
        p=DrainInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);connection=self.get(s,TelemetryConnection,identity)
            if not self._archive_dir:raise HTTPException(503,'Local aggregate archive is not configured.')
            result=self.edge().archive_aggregates(self._scope(identity),self._archive_dir,limit=p.limit)
            self.audit(s,connection,'local_aggregates_archived',result)
            return {**result,'raw_stays_local':True,'cloud_publication':False}

    def evidence(self,identity,limit=100,after=''):
        DrainInput(limit=limit)
        if len(after)>160:raise ValueError('Evidence cursor is too long.')
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);self.get(s,TelemetryConnection,identity)
            return self.edge().evidence(self._scope(identity),limit=limit,after=after)

    def retention(self,identity,payload):
        p=RetentionInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s);connection=self.get(s,TelemetryConnection,identity)
            edge=self.edge();scope=self._scope(identity)
            if not p.execute:
                return {'executed':False,'purged':0,'eligible':None,'preview_basis':'edge_prerequisites_checked_on_execution','blocker':self._retention_blocker(),'edge':edge.diagnostics(scope)}
            result=edge.retention(scope,p.before,limit=p.limit)
            self.audit(s,connection,'local_retention',result)
            return {**result,'executed':True,'blocker':self._retention_blocker() if result['protected'] else None,'receiver_acknowledged':False}

    def _summary(self,room_id,start,end,cycle_id=None):
        result=self.edge().room_summary(self.org,self.facility,room_id,start,end,cycle_id=cycle_id)
        if len(result['streams'])>200:result.update(streams=result['streams'][:200],truncated=True,status='UNKNOWN')
        for stream in result['streams']:
            threshold=stream['snapshot'].get('threshold_seconds')
            stream['alert_threshold_status']='configured' if threshold is not None and threshold>0 else 'not_configured'
            stream['threshold_semantics']='continuous_same_direction'
            if stream['alert_threshold_status']=='not_configured':stream['deviations']=[]
        return result

    def _connection_freshness(self,room_ids):
        with Session(self.engine) as s:
            ids=s.scalars(select(CultivationDevice.connection_id).join(DeviceMapping,DeviceMapping.device_id==CultivationDevice.id).where(*self.scope(CultivationDevice),*self.scope(DeviceMapping),DeviceMapping.room_id.in_(room_ids)).distinct().order_by(CultivationDevice.connection_id).limit(9)).all()
            imported=self._last_imports(s,ids[:8])
        values=[]
        for identity in ids[:8]:
            diagnostics=self.edge().diagnostics(self._scope(identity)) if self._edge or self._path else None
            values.append({'connection_id':identity,'connection_url':f'/api/v1/cultivation-intelligence/connections/{identity}/health','last_import_at':imported.get(identity),'last_received_at':diagnostics['last_received_at'] if diagnostics else None,'last_valid_observed_at':diagnostics['last_valid_observed_at'] if diagnostics else None,'counts':diagnostics['counts'] if diagnostics else None,'live_connected':False,'sensor_freshness_status':'unknown','basis':'connection_scope_not_room_condition'})
        return {'connections':values,'truncated':len(ids)>8}

    def room(self,identity,start=None,end=None):
        result=super().room(identity)
        result['canonical_links']={'self':f'/api/v1/cultivation-intelligence/rooms/{identity}','work':[{'id':w['id'],'url':f"/api/v1/work/{w['id']}"} for w in result['work']],'cycles':[{'id':c['id'],'url':f"/api/v1/cultivation-intelligence/cycles/{c['id']}"} for c in result['cycles']]}
        result['connection_freshness']=self._connection_freshness([identity])
        result['edge_latest']=self.edge().latest(self.org,self.facility,identity) if self._edge or self._path else None
        result['cycle_attribution_status']='ambiguous' if len(result['cycles'])>1 else 'assigned' if result['cycles'] else 'unassigned'
        if self._edge or self._path:
            start,end=self._window(start,end)
            result['edge_summary']=self._summary(identity,start,end)
        elif start is not None or end is not None:self._window(start,end)
        return result

    def cycle(self,identity,start=None,end=None):
        result=super().cycle(identity)
        room_ids=list(dict.fromkeys(o['room_id'] for o in reversed(result['occupancy'])))
        result['canonical_links']={'self':f'/api/v1/cultivation-intelligence/cycles/{identity}','rooms':[{'id':r,'url':f'/api/v1/cultivation-intelligence/rooms/{r}'} for r in room_ids],'harvest':f"/api/v1/inventory/production/plants/harvests/{result['harvest']['id']}" if result['harvest'] else None,'plants':[{'id':m['plant_id'],'url':f"/api/v1/inventory/production/plants/{m['plant_id']}/lineage"} for m in result['members']]}
        result['connection_freshness']=self._connection_freshness(room_ids)
        result['edge_summary']={'rooms':[],'truncated':result['truncated'] or len(room_ids)>8,'status':'UNKNOWN'}
        if self._edge or self._path:
            start,end=self._window(start,end)
            # Detail-on-demand: at most eight local summary reads, never raw history
            # or one read per plant. Longer room histories explicitly truncate.
            for room_id in room_ids[:8]:
                summary=self._summary(room_id,start,end,cycle_id=identity)
                result['edge_summary']['truncated'] |= summary['truncated']
                result['edge_summary']['rooms'].append({'room_id':room_id,'summary':summary})
        elif start is not None or end is not None:self._window(start,end)
        return result
