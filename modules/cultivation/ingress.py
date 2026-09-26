"""Read-only machine admission and human-audited grant provisioning."""
from datetime import datetime, timezone
from dataclasses import dataclass
import json
import re
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager

from fastapi import HTTPException
from pydantic import Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization, new_id
from modules.operational_moats.models import ServiceAccount
from modules.operational_moats.service import _hash_token, _new_token
from .context_resolution import build_resolver
from .edge_store import Scope
from .ingress_models import CultivationIngressGrant
from .intelligence_models import TelemetryConnection
from .intelligence_service import IntelligenceService, VersionInput, fields
from .telemetry import utc

MAX_BYTES = 1048576
IDENTITY = re.compile(r'^[A-Za-z0-9_.:@-]{1,120}$')


def fail(status, code):
    raise HTTPException(status, code, headers={'Retry-After':'5'} if status in (429,503) else None)


@dataclass(frozen=True)
class AuthorizedIngress:
    scope: Scope
    grant_id: str


def authenticate(session, token, connection_id, headers, *, lock=False):
    """No last_used write, wildcard fallback, actor substitution or auth cache."""
    if not isinstance(token,str) or not token.startswith('dla_') or not 20 <= len(token) <= 256:
        fail(401,'invalid_credential')
    account=session.scalar(select(ServiceAccount).where(ServiceAccount.token_hash==_hash_token(token)).execution_options(populate_existing=True))
    if account is None or not account.active:fail(401,'invalid_credential')
    try:scopes=json.loads(account.scopes_json)
    except (ValueError,TypeError):scopes=[]
    if not isinstance(scopes,list) or 'cultivation:ingest' not in scopes or not account.facility_id:fail(403,'ingress_forbidden')
    scope=Scope(account.organization_id,account.facility_id,connection_id)
    for key, expected in (('x-facility-id',scope.facility_id),('x-organization-id',scope.organization_id)):
        values=headers.getlist(key) if hasattr(headers,'getlist') else [headers[key]] if key in headers else []
        if any(value!=expected for value in values):fail(403,'ingress_forbidden')
    q=select(Facility).join(Organization,Organization.id==Facility.organization_id).where(Facility.id==scope.facility_id,Facility.organization_id==scope.organization_id,Organization.active.is_(True))
    facility=session.scalar((q.with_for_update(of=Facility) if lock else q).execution_options(populate_existing=True))
    if facility is None or not facility.active or not facility.cultivation_enabled:fail(403,'ingress_forbidden')
    # Facility-first ordering matches all human cultivation writers. Lock account
    # too so generic account updates cannot race the final admission on PostgreSQL.
    if lock:
        account=session.scalar(select(ServiceAccount).where(ServiceAccount.id==account.id).with_for_update().execution_options(populate_existing=True))
        if account is None or not account.active or account.facility_id!=scope.facility_id or account.organization_id!=scope.organization_id:fail(403,'ingress_forbidden')
        try:scopes=json.loads(account.scopes_json)
        except (ValueError,TypeError):scopes=[]
        if not isinstance(scopes,list) or 'cultivation:ingest' not in scopes:fail(403,'ingress_forbidden')
    connection=session.scalar(select(TelemetryConnection).where(TelemetryConnection.id==connection_id,TelemetryConnection.organization_id==scope.organization_id,TelemetryConnection.facility_id==scope.facility_id).execution_options(populate_existing=True))
    grant=session.scalar(select(CultivationIngressGrant).where(CultivationIngressGrant.service_account_id==account.id,CultivationIngressGrant.organization_id==scope.organization_id,CultivationIngressGrant.facility_id==scope.facility_id,CultivationIngressGrant.connection_id==connection_id).execution_options(populate_existing=True))
    if connection is None or connection.status!='configured' or connection.revoked_at or connection.mode!='push' or connection.provider!='json':fail(403,'ingress_forbidden')
    if grant is None or grant.revoked_at or utc(grant.expires_at)<=datetime.now(timezone.utc):fail(403,'ingress_forbidden')
    return AuthorizedIngress(scope,grant.id)


def validate_envelope(data, max_batch=500):
    if not isinstance(data,dict) or set(data)!={'schema_version','batch_id','readings'}:fail(422,'invalid_envelope')
    if type(data['schema_version']) is not int or data['schema_version']!=1:fail(422,'unsupported_schema')
    if not isinstance(data['batch_id'],str) or not IDENTITY.fullmatch(data['batch_id']):fail(422,'invalid_identity')
    readings=data['readings']
    if not isinstance(readings,list) or not readings:fail(422,'invalid_readings')
    if len(readings)>min(500,max_batch):fail(413,'reading_limit')
    required={'event_id','source_device_id','source_channel','source_metric','value','unit','observed_at'}
    for row in readings:
        if not isinstance(row,dict) or not required<=row.keys() or row.keys()-required-{'quality'}:fail(422,'invalid_reading_structure')
        for key in ('event_id','source_device_id','source_channel','source_metric'):
            if not isinstance(row[key],str) or not IDENTITY.fullmatch(row[key]):fail(422,'invalid_identity')
        for key,value in row.items():
            if isinstance(value,(dict,list)) or (isinstance(value,str) and len(value)>256):fail(422,'invalid_reading_structure')
        # Invalid scalar measurement/time/quality belongs in durable quarantine.
    return data


class AdmissionLimiter:
    """Bounded per-process admission; no credential/token retained in memory."""
    def __init__(self,concurrency=4,rate=60,scopes=1024):
        self.semaphore=threading.BoundedSemaphore(concurrency)
        self.lock=threading.Lock();self.windows=OrderedDict();self.rate=rate;self.scopes=scopes

    @contextmanager
    def slot(self):
        if not self.semaphore.acquire(blocking=False):fail(429,'ingress_busy')
        try:yield
        finally:self.semaphore.release()

    def admit(self,scope):
        now=time.monotonic()
        with self.lock:
            while self.windows and next(iter(self.windows.values()))[0]<=now-60:self.windows.popitem(last=False)
            start,count=self.windows.get(scope.key,(now,0))
            if count>=self.rate:fail(429,'ingress_rate_limit')
            if scope.key not in self.windows and len(self.windows)>=self.scopes:fail(429,'ingress_busy')
            self.windows[scope.key]=(start,count+1)


limiter=AdmissionLimiter()


def commit_batch(engine,token,connection_id,headers,data,edge_factory):
    with Session(engine) as session,session.begin():
        # No SQL write even for SQLite auth tests. Production facility FOR UPDATE
        # serializes cultivation writers; already-admitted batches may finish.
        if engine.dialect.name=='sqlite':session.execute(text('BEGIN'))
        elif engine.dialect.name=='postgresql':
            session.execute(text("SET LOCAL lock_timeout = '3s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
        admission=authenticate(session,token,connection_id,headers,lock=True)
        scope=admission.scope
        edge=edge_factory()
        validate_envelope(data,edge.max_batch)
        resolver=build_resolver(session,scope,max_gap_seconds=edge.max_gap_seconds)
        resolved=[resolver(scope,row) for row in data['readings']]
        # This release owns both contracts. Never acknowledge a push without
        # recording transport disposition in the same durable evidence commit.
        result=edge.ingest(scope,data['readings'],resolved=resolved,
                           transport={'batch_id':data['batch_id'],'grant_id':admission.grant_id})
        if result.get('committed') is not True:fail(503,'storage_unavailable')
        return {'schema_version':1,'batch_id':data['batch_id'],**{k:result[k] for k in ('committed','accepted','duplicates','conflicts','quarantined','pending','items')}}


class GrantInput(VersionInput):
    label: str = Field(min_length=1,max_length=120)
    expires_at: datetime
    @field_validator('expires_at')
    @classmethod
    def expiry(cls,value):
        if value.tzinfo is None or value.utcoffset() is None or value<=datetime.now(timezone.utc):raise ValueError('Future timezone-aware expiry required.')
        return value


def grant_payload(row,account_active=True):
    status='revoked' if row.revoked_at else 'expired' if utc(row.expires_at)<=datetime.now(timezone.utc) else 'disabled' if not account_active else 'active'
    return {**fields(row,'id connection_id service_account_id label version created_at expires_at revoked_at'),'status':status}


class IngressGrantService(IntelligenceService):
    def grants(self,identity):
        self.authorize()
        with Session(self.engine) as s:
            self.get(s,TelemetryConnection,identity)
            rows=s.execute(select(CultivationIngressGrant,ServiceAccount.active).join(ServiceAccount,ServiceAccount.id==CultivationIngressGrant.service_account_id).where(*self.scope(CultivationIngressGrant),CultivationIngressGrant.connection_id==identity).order_by(CultivationIngressGrant.id).limit(201)).all()
            return {'grants':[grant_payload(r,active) for r,active in rows[:200]],'truncated':len(rows)>200}

    def issue_grant(self,identity,payload):
        p=GrantInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            connection=self.connection(s,identity)
            if connection.mode!='push' or connection.provider!='json':raise ValueError('Push requires normalized JSON.')
            self.bump(s,connection,p.version)
            token=_new_token('dla');account_id=new_id()
            account=ServiceAccount(id=account_id,organization_id=self.org,facility_id=self.facility,name='cultivation-'+account_id,token_hash=_hash_token(token),scopes_json='["cultivation:ingest"]',active=True,created_by=self.context.user_id)
            s.add(account);s.flush()
            row=self.new(CultivationIngressGrant,connection_id=identity,service_account_id=account.id,label=p.label,expires_at=p.expires_at,version=1,created_by=self.context.user_id)
            s.add(row);s.flush();self.audit(s,row,'ingress_grant_issued',{'connection_id':identity,'service_account_id':account.id})
            return {'grant':grant_payload(row),'connection_version':connection.version,'token':token}

    def revoke_grant(self,identity,grant_id,payload):
        p=VersionInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            self.get(s,TelemetryConnection,identity)
            row=self.get(s,CultivationIngressGrant,grant_id,lock=True)
            if row.connection_id!=identity:raise LookupError('Grant not found.')
            self.bump(s,row,p.version)
            row.revoked_at=datetime.now(timezone.utc);row.revoked_by=self.context.user_id
            account=s.get(ServiceAccount,row.service_account_id);account.active=False
            self.audit(s,row,'ingress_grant_revoked',{'connection_id':identity})
            return grant_payload(row)
