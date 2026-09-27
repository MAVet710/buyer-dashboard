"""Guided onboarding reuses canonical Metrc credentials, mappings and hydration.

No provider mutation, account provisioning or production-mode bypass lives here.
Discovery is a read-only preview; only an explicit confirmed link writes locally.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import replace
import hashlib
import json
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, Facility, Organization, new_id
from modules.integrations import IntegrationConfigurationService
from modules.regulatory.models import RegulatoryFacilityMapping
from services.metrc_facility_onboarding import DiscoveredMetrcFacility, MetrcFacilityOnboardingService
from .adoption_models import ReadinessAnnotation
from .metrc_context import metrc_scope_key, metrc_sandbox_scope_key, resolve_metrc_context
from .metrc_sync_policy import MetrcPolicySyncControlService
from .metrc_natural_sync import MetrcNaturalSyncControlService
from .metrc_onboarding_pair import vendor_for_setup, discover_pair, finish_link
from modules.alpha_mode.environment_guard import require_environment_isolation
from ..permissions import require_permission

RUN_KEY = 'wizard_metrc_import'
_LOCK = Lock()
_ACTIVE = set()


@contextmanager
def single_setup(engine, organization_id, facility_id):
    """One wizard operation per facility, including across PostgreSQL processes."""
    key = (organization_id, facility_id)
    with _LOCK:
        if key in _ACTIVE:
            raise HTTPException(409, 'Setup is already running. Refresh its progress.')
        _ACTIVE.add(key)
    connection = None
    lock_engine = None
    lock_id = int.from_bytes(hashlib.sha256(('wizard-metrc|'+'|'.join(key)).encode()).digest()[:8], 'big', signed=True)
    try:
        if engine.dialect.name == 'postgresql':
            # One dedicated connection prevents the long import guard from
            # occupying a slot needed by the existing two-connection API pool.
            lock_engine=create_engine(engine.url,poolclass=NullPool,hide_parameters=True,
                connect_args={"connect_timeout":5})
            connection = lock_engine.connect()
            acquired = connection.scalar(text('SELECT pg_try_advisory_xact_lock(:id)'), {'id':lock_id}) is True
            if not acquired:
                raise HTTPException(409, 'Setup is already running. Refresh its progress.')
        yield
    finally:
        try:
            if connection is not None:
                # Transaction-scoped lock is safe behind transaction pooling.
                # Rollback releases it even when the operation raised.
                connection.rollback()
                connection.close()
        except Exception:
            if connection is not None:
                connection.invalidate()
                connection.close()
            raise
        finally:
            if lock_engine is not None:
                lock_engine.dispose()
            with _LOCK:
                _ACTIVE.discard(key)


class GuidedMetrcSetup:
    def __init__(self, engine, settings, context):
        self.engine, self.settings, self.context = engine, settings, context
        self.org, self.facility = context.organization_id, context.facility_id

    def authorize(self, write=False):
        with Session(self.engine) as session:
            facility = session.scalar(select(Facility).where(Facility.id==self.facility,
                Facility.organization_id==self.org, Facility.active.is_(True)))
            actor = session.get(AppUser, self.context.user_id)
            if facility is None or actor is None or not actor.active:
                raise HTTPException(403, 'An active facility and account are required.')
            if actor.organization_id != self.org and self.context.role.casefold() != 'dev':
                raise HTTPException(403, 'This account cannot configure the selected organization.')
            if write:
                if self.context.role.casefold() not in {'dev','admin'}:
                    raise HTTPException(403, 'A facility administrator must confirm onboarding.')
                require_permission(self.context, self.engine, 'integrations.manage_metrc', session=session)
            return {'id':facility.id,'name':facility.name,'license_number':facility.license_number}

    def credentials(self):
        if not self.settings.integration_encryption_key:
            raise HTTPException(503, 'Protected credential storage is unavailable.')
        return IntegrationConfigurationService(self.engine, self.settings.integration_encryption_key)

    def mode(self):
        from modules.alpha_mode import AlphaOperatingModeService
        return AlphaOperatingModeService(self.engine).current(self.org, self.facility)

    def environment(self):
        mode = self.mode()
        if not mode.metrc_enabled:
            raise HTTPException(409, 'Provider access is disabled by the selected facility mode.')
        return 'production' if mode.effective_mode == 'metrc_production' else 'sandbox'

    def read(self):
        facility = self.authorize()
        mode = self.mode()
        service = self.credentials()
        user = service.get('user', metrc_scope_key(self.context), 'metrc')
        environment = 'production' if mode.effective_mode == 'metrc_production' else 'sandbox'
        vendor = vendor_for_setup(service,self.context,environment)
        public = service.public(user)
        config = public.get('configuration') or {}
        _, metrc = resolve_metrc_context(self.engine, self.settings, self.context)
        with Session(self.engine) as session:
            row = session.scalar(select(ReadinessAnnotation).where(ReadinessAnnotation.organization_id==self.org,
                ReadinessAnnotation.facility_id==self.facility, ReadinessAnnotation.item_key==RUN_KEY))
            try:
                raw_run = json.loads(row.notes) if row else None
                allowed = {'id','status','started_at','completed_at','environment','license_number','provider_mutations','error_code','sync_mode','totals','workspace_summary'}
                run = {k:v for k,v in raw_run.items() if k in allowed} if isinstance(raw_run,dict) else None
            except (ValueError, TypeError):
                run = None
        if run and run.get('status') in {'pending','running'}:
            from .guided_metrc_jobs import is_local_active
            from .guided_metrc_recovery import import_active_elsewhere
            try:pending_age=(datetime.now(timezone.utc)-datetime.fromisoformat(run['started_at'])).total_seconds()
            except (ValueError,TypeError,KeyError):pending_age=121
            grace=run.get('status')=='pending' and pending_age<120
            if not grace and not is_local_active(self.org,self.facility) and not import_active_elsewhere(self.engine,self.org,self.facility):
                run={**run,'status':'interrupted','error_code':'resume_required'}
        history = MetrcNaturalSyncControlService(self.engine).status(
            organization_id=self.org, facility_id=self.facility, metrc=metrc)
        safe_states = [{key:value.get(key) for key in ('resource','status','records_seen','records_written',
            'last_completed_at','last_success_at')} | {'restricted':str(value.get('cursor') or '').startswith('permission-skipped')}
            for value in history.get('states', [])]
        can_manage = False
        try:
            self.authorize(write=True)
            can_manage = True
        except HTTPException:
            pass
        return {'facility':facility,'mode':mode.effective_mode,'can_manage':can_manage,
            'environment':metrc.environment,'state':config.get('state') or 'MA',
            'user_key_saved':bool(user and user.encrypted_secret),'platform_key_ready':bool(vendor and vendor.encrypted_secret),
            'configured':metrc.configured,'trusted_mapping':metrc.trusted_mapping,
            'production_available':True,'production_writes_enabled':False,
            'can_manage_platform':self.context.role.casefold()=='dev',
            'run':run,'resources':safe_states,'full_baseline_ready':bool(history.get('full_baseline_ready')),
            'import_scope':'Existing provider records populate local workspaces. This setup never submits changes to Metrc.'}

    def save_key(self, state, api_key):
        self.authorize(write=True)
        environment = self.environment()
        if state != 'MA':
            raise HTTPException(422, 'This guided setup currently supports Massachusetts.')
        if not isinstance(api_key, str) or not 8 <= len(api_key.strip()) <= 1024 or any(ord(c)<32 for c in api_key):
            raise HTTPException(422, 'Enter your current Metrc user API key.')
        with single_setup(self.engine, self.org, self.facility):
            service = self.credentials()
            previous = service.get('user', metrc_scope_key(self.context), 'metrc')
            config = dict(service.public(previous).get('configuration') or {})
            if config.get('environment') not in {None,environment}:
                raise HTTPException(409, 'This facility already has a different provider environment. Review that connection first.')
            with Session(self.engine) as session:
                require_environment_isolation(session,self.org,self.facility,environment)
            config.update(state='MA', environment=environment)
            service.save(scope_type='user', scope_key=metrc_scope_key(self.context), provider='metrc',
                organization_id=self.org, facility_id=self.facility, configuration=config,
                secret=api_key.strip(), actor=self.context.user_id)
        return {'saved':True,'user_key_saved':True,'validated':False}

    def save_platform_key(self,state,environment,api_key):
        self.authorize(write=True)
        if self.context.role.casefold()!='dev':
            raise HTTPException(403,'Only the platform administrator can configure the integrator credential.')
        if state!='MA' or environment not in ('sandbox','production'):
            raise HTTPException(422,'Choose the supported state and explicit provider environment.')
        if not isinstance(api_key,str) or not 8<=len(api_key.strip())<=1024 or any(ord(c)<32 for c in api_key):
            raise HTTPException(422,'Enter the platform integrator API key.')
        from .metrc_production_context import platform_vendor_scope
        self.credentials().save(scope_type='platform',scope_key=platform_vendor_scope(state,environment),
            provider='metrc',organization_id=None,facility_id=None,
            configuration={'state':state,'environment':environment,'credential_kind':'integrator'},
            secret=api_key.strip(),actor=self.context.user_id,audit_organization_id=self.org,audit_facility_id=self.facility)
        return {'saved':True,'environment':environment,'validated':False}

    def _discover(self):
        environment = self.environment()
        with Session(self.engine) as session:
            require_environment_isolation(session,self.org,self.facility,environment)
        vendor,user,records = discover_pair(self.credentials(),self.context,environment)
        return vendor,user,[DiscoveredMetrcFacility.from_record(row) for row in records]

    @staticmethod
    def digest(vendor, user, discovered):
        value = [vendor.id, str(vendor.updated_at), user.id, str(user.updated_at),
                 [row.public() for row in discovered]]
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()

    def preview(self):
        facility = self.authorize(write=True)
        vendor, user, discovered = self._discover()
        return {'preview_id':self.digest(vendor,user,discovered),'environment':self.environment(),'state':'MA',
            'facility':facility,'facilities':[row.public() for row in discovered],
            'provider_mutations':0,'local_records_created':0}

    def link(self, license_number, preview_id, create_new=False):
        self.authorize(write=True)
        environment=self.environment()
        with single_setup(self.engine,self.org,self.facility):
            vendor,user,discovered=self._discover()
            if preview_id!=self.digest(vendor,user,discovered):
                raise HTTPException(409,'The credential or facility list changed. Preview again before linking.')
            matches=[row for row in discovered if row.license_number==license_number]
            if len(matches)!=1:
                raise HTTPException(409,'Select one facility from the current Metrc response.')
            # Canonical services join this one outer transaction. A failed link
            # cannot leave a replaced credential or half-confirmed facility.
            with self.engine.begin() as connection:
                target_id=self.facility
                with Session(bind=connection) as session:
                    session.execute(select(Organization.id).where(Organization.id==self.org).with_for_update())
                    if create_new:
                        matches_local=session.scalars(select(Facility).where(Facility.organization_id==self.org,
                            Facility.license_number==license_number,Facility.active.is_(True))).all()
                        if len(matches_local)>1:
                            raise HTTPException(409,'More than one existing local facility has this license. Resolve the duplicate first.')
                        target_id=matches_local[0].id if matches_local else None
                    else:
                        other=session.scalar(select(Facility.id).where(Facility.organization_id==self.org,
                            Facility.license_number==license_number,Facility.id!=self.facility,Facility.active.is_(True)))
                        if other:
                            raise HTTPException(409,'This license already has a DoobieLogic facility. Open that facility rather than create a duplicate.')
                    if target_id is None:
                        target=MetrcFacilityOnboardingService(connection,self.settings.integration_encryption_key)._create_facility(
                            organization_id=self.org,discovered=matches[0],actor=self.context.user_id)
                        target_id=target.id
                    local=session.scalar(select(Facility).where(Facility.id==target_id,
                        Facility.organization_id==self.org).with_for_update())
                    if local is None or not local.active or (local.license_number and local.license_number!=license_number):
                        raise HTTPException(409,'This facility is unavailable or already belongs to another license.')
                    require_environment_isolation(session,self.org,target_id,environment)
                    from modules.integrations.models import IntegrationConfiguration
                    for prior in (vendor,user):
                        now=session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.id==prior.id).with_for_update())
                        if now is None or now.encrypted_secret!=prior.encrypted_secret or now.configuration_json!=prior.configuration_json:
                            raise HTTPException(409,'Connection changed during discovery. Preview it again.')
                    mappings=session.scalars(select(RegulatoryFacilityMapping).where(
                        RegulatoryFacilityMapping.organization_id==self.org,
                        RegulatoryFacilityMapping.facility_id==target_id,
                        RegulatoryFacilityMapping.active.is_(True))).all()
                    if any(row.provider!='metrc' or row.environment!=environment or row.license_number!=license_number
                           or row.jurisdiction_code!='MA' for row in mappings):
                        raise HTTPException(409,'The existing regulatory mapping conflicts with this selection.')
                from modules.alpha_mode import AlphaOperatingModeService
                if create_new and target_id!=self.facility:
                    AlphaOperatingModeService(connection).set_mode(self.org,target_id,
                        mode='metrc_production' if environment=='production' else 'metrc_sandbox',actor=self.context.user_id)
                current_mode=AlphaOperatingModeService(connection).current(self.org,target_id).effective_mode
                if current_mode!=('metrc_production' if environment=='production' else 'metrc_sandbox'):
                    raise HTTPException(409,'Facility mode changed during discovery. Review it before linking.')
                MetrcFacilityOnboardingService(connection,self.settings.integration_encryption_key).confirm(
                    organization_id=self.org,actor=self.context.user_id,state='MA',environment=environment,
                    record=matches[0].raw,source_user_credential=user,source_vendor_credential=vendor,
                    target_facility_id=target_id,create_new=False)
                finish_link(connection,self.settings,replace(self.context,facility_id=target_id),environment,matches[0].raw)
            return {'linked':True,'facility_id':target_id,'license_number':license_number,
                    'environment':environment,'import_started':False,'provider_mutations':0}

    def _run_note(self, run, expected_id=None):
        from .scheduled_reports import audit
        with Session(self.engine) as session, session.begin():
            session.scalar(select(Facility).where(Facility.id==self.facility,
                Facility.organization_id==self.org).with_for_update())
            row=session.scalar(select(ReadinessAnnotation).where(ReadinessAnnotation.organization_id==self.org,
                ReadinessAnnotation.facility_id==self.facility,ReadinessAnnotation.item_key==RUN_KEY).with_for_update())
            previous={}
            if row:
                try:previous=json.loads(row.notes)
                except (ValueError,TypeError):pass
            if expected_id is not None and previous.get('id')!=expected_id:
                raise HTTPException(409,'A newer import owns this progress record. Refresh before continuing.')
            if expected_id is None and previous.get('status')=='pending':
                try:pending_age=(datetime.now(timezone.utc)-datetime.fromisoformat(previous['started_at'])).total_seconds()
                except (ValueError,TypeError,KeyError):pending_age=121
                if pending_age<120:raise HTTPException(409,'An import is already being started. Refresh its progress.')
            if row is None:
                row=ReadinessAnnotation(id=new_id(),organization_id=self.org,facility_id=self.facility,item_key=RUN_KEY)
                session.add(row)
            row.notes=json.dumps(run,sort_keys=True)
            row.updated_by=self.context.user_id
            row.updated_at=datetime.now(timezone.utc)
            audit(session,self.context,row,'wizard_import_progress',after=run)

    def require_import_context(self):
        self.authorize(write=True)
        _,metrc=resolve_metrc_context(self.engine,self.settings,self.context)
        if not metrc.configured or not metrc.trusted_mapping or metrc.environment!=self.environment() or metrc.status!='connected':
            raise HTTPException(409,'Validate and confirm the exact facility connection before importing.')
        return metrc

    def import_records(self,run_id=None):
        self.authorize(write=True)
        with single_setup(self.engine,self.org,self.facility):
            metrc=self.require_import_context()
            run={'id':run_id or str(uuid4()),'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
                 'environment':metrc.environment,'license_number':metrc.license_number,
                 'provider_mutations':0,'error_code':None}
            self._run_note(run,expected_id=run_id)
            try:
                result=MetrcPolicySyncControlService(self.engine).sync(organization_id=self.org,
                    facility_id=self.facility,metrc=metrc,actor=self.context.user_id)
                _,current=resolve_metrc_context(self.engine,self.settings,self.context)
                unchanged=(current.configured and current.trusted_mapping and current.environment==metrc.environment
                    and current.license_number==metrc.license_number and current.user_api_key==metrc.user_api_key
                    and current.integrator_api_key==metrc.integrator_api_key)
                totals=result.get('totals') or {}
                from .guided_metrc_summary import import_summary
                summary=import_summary(result)
                run.update(status='needs_review' if not unchanged or totals.get('errors') or summary['conflict_count'] or summary['summary_truncated'] else 'completed',
                    workspace_summary=summary,
                    completed_at=datetime.now(timezone.utc).isoformat(),sync_mode=result.get('sync_mode'),
                    totals={key:int(totals.get(key) or 0) for key in ('records','accepted','duplicates','errors','restrictions')})
                self._run_note(run,expected_id=run['id'])
            except Exception:
                run.update(status='interrupted',error_code='import_requires_review',completed_at=datetime.now(timezone.utc).isoformat())
                self._run_note(run,expected_id=run['id'])
                raise HTTPException(502,'Import did not finish. Saved evidence is preserved; review progress before resuming.') from None
            return run
