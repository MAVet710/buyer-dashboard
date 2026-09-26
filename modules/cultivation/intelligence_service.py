"""Authenticated cultivation relationship services; never controls equipment or stock."""
from datetime import date, datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select, update, text
from sqlalchemy.orm import Session
from modules.coman.models import AppUser, Facility, WorkItem, InventoryLot, AuditEvent, new_id
from modules.material_lineage.models import MaterialTransformation, MaterialTransformationOutput
from modules.inventory_quality.models import LotQualityEvidence
from .post_harvest import CultivationPostHarvestBatch
from .batch_models import CultivationPlantGroupMember, CultivationPlantParentLink
from modules.coman.audit import record_audit_event
from .intelligence_models import (CropCycle, CropCyclePlant, CropCycleRoom, CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget, CultivationOperationalEvent, TelemetryConnection, CultivationDevice, CultivationSensor, DeviceMapping, EnvironmentalZone, CultivationPlantGroup, CultivationHarvest)
from .models import CultivationPlant, CultivationRoom, CultivationHarvestPlant, CultivationCostEntry
from .metrics import canonical_metric, normalize_metric_value, CANONICAL_UNITS
from .telemetry import TelemetryService, TelemetryConflict, utc

LIMIT = 200

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

class VersionInput(Input):
    version: int = Field(ge=1)

class CycleInput(Input):
    cycle_code: str = Field(min_length=1,max_length=120)
    display_name: str = Field(min_length=1,max_length=255)
    genetics_label: str = Field(default='',max_length=255)
    nursery_group_id: str | None = None
    recipe_id: str | None = None
    started_on: date | None = None
    estimated_harvest_date: date | None = None
    @model_validator(mode='after')
    def dates(self):
        if self.started_on and self.estimated_harvest_date and self.estimated_harvest_date < self.started_on:
            raise ValueError('Expected harvest must not precede start.')
        return self

class TimedInput(Input):
    @field_validator('entered_at','exited_at','effective_at','occurred_at', check_fields=False)
    @classmethod
    def aware(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError('Timestamp requires a timezone.')
        return utc(value) if value else value

class OccupancyInput(VersionInput, TimedInput):
    room_id: str
    zone_id: str | None = None
    stage_id: str | None = None
    entered_at: datetime
    exited_at: datetime | None = None
    @model_validator(mode='after')
    def interval(self):
        if self.exited_at and self.exited_at <= self.entered_at:
            raise ValueError('Exit must follow entry.')
        return self

class MembersInput(VersionInput, TimedInput):
    plant_ids: list[str] = Field(min_length=1,max_length=200)
    action: Literal['add','remove']
    effective_at: datetime
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.plant_ids)) != len(self.plant_ids):
            raise ValueError('Plant IDs must be unique.')
        if self.effective_at > datetime.now(timezone.utc):
            raise ValueError('Membership changes cannot be in the future.')
        return self

class HarvestInput(VersionInput):
    harvest_id: str

class RecipeTargetInput(Input):
    metric: str
    minimum: float | None = None
    maximum: float | None = None
    unit: str
    threshold_seconds: int | None = Field(default=None,ge=1,le=2678400,strict=True)
    @field_validator('minimum','maximum',mode='before')
    @classmethod
    def not_boolean(cls,value):
        if isinstance(value,bool):raise ValueError('Boolean values are not measurements.')
        return value
    @model_validator(mode='after')
    def target(self):
        self.metric = canonical_metric(self.metric)
        if self.minimum is None and self.maximum is None:
            raise ValueError('A target needs at least one bound.')
        if self.unit != CANONICAL_UNITS[self.metric]:
            raise ValueError('Targets require normalized registry units.')
        for value in (self.minimum,self.maximum):
            if value is not None:
                normalize_metric_value(self.metric,value,self.unit)
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('Minimum exceeds maximum.')
        return self

class RecipeStageInput(Input):
    stage_key: str = Field(min_length=1,max_length=120)
    display_name: str = Field(min_length=1,max_length=255)
    sequence: int = Field(ge=0,le=1000)
    targets: list[RecipeTargetInput] = Field(default_factory=list,max_length=32)
    @model_validator(mode='after')
    def unique(self):
        if len({t.metric for t in self.targets}) != len(self.targets):
            raise ValueError('Duplicate target metric.')
        return self

class RecipeInput(Input):
    name: str = Field(min_length=1,max_length=255)
    description: str = Field(default='',max_length=4000)
    stages: list[RecipeStageInput] = Field(min_length=1,max_length=32)
    @model_validator(mode='after')
    def unique(self):
        if len({s.stage_key for s in self.stages}) != len(self.stages) or len({s.sequence for s in self.stages}) != len(self.stages):
            raise ValueError('Stage keys and order must be unique.')
        return self

class EventInput(TimedInput):
    room_id: str | None = None
    cycle_id: str | None = None
    event_type: str = Field(min_length=1,max_length=80)
    title: str = Field(min_length=1,max_length=255)
    notes: str = Field(default='',max_length=4000)
    occurred_at: datetime

class ConnectionInput(Input):
    provider: Literal['json','csv','growlink']
    label: str = Field(min_length=1,max_length=160)
    mode: Literal['file','push'] = 'file'
    expected_interval_seconds: int | None = Field(default=None,ge=1,le=2678400,strict=True)
    stale_after_seconds: int | None = Field(default=None,ge=1,le=2678400,strict=True)
    @model_validator(mode='after')
    def transport(self):
        if self.mode=='push' and self.provider!='json':raise ValueError('Push requires normalized JSON.')
        return self

class DeviceInput(VersionInput):
    source_device_id: str = Field(min_length=1,max_length=120,pattern=r'^[A-Za-z0-9_.:@-]+$')
    display_name: str = Field(default='',max_length=255)

class MappingInput(VersionInput, TimedInput):
    room_id: str
    zone_id: str | None = None
    effective_at: datetime

class SensorInput(VersionInput):
    source_channel: str = Field(min_length=1,max_length=120,pattern=r'^[A-Za-z0-9_.:@-]+$')
    source_metric: str = Field(min_length=1,max_length=120,pattern=r'^[A-Za-z0-9_.:@-]+$')
    source_unit: str = Field(min_length=1,max_length=32)
    metric: str

class OccupancyCloseInput(VersionInput, TimedInput):
    exited_at: datetime

class ZoneInput(Input):
    zone_code: str = Field(min_length=1,max_length=120)
    display_name: str = Field(default='',max_length=255)


def fields(row, names):
    return {name: getattr(row,name) for name in names.split()}

def cycle_payload(row):
    return fields(row,'id cycle_code display_name genetics_label nursery_group_id recipe_id harvest_id status started_on estimated_harvest_date version')

def room_payload(row):
    return fields(row,'id room_code display_name phase active plant_capacity')

def connection_payload(row):
    return {**fields(row,'id provider label mode status version revoked_at expected_interval_seconds stale_after_seconds'), 'live_supported':False}


def target_payload(row):
    return {**fields(row,'metric minimum maximum unit threshold_seconds'),
            'alert_threshold_status':'configured' if row.threshold_seconds is not None else 'not_configured'}


class IntelligenceService:
    def __init__(self, engine, context):
        self.engine, self.context = engine, context
        self.org, self.facility = context.organization_id, context.facility_id

    def authorize(self, *, write=False, connections=False, session=None):
        from backend.app.auth import require_facility_capability
        from backend.app.permissions import require_permission
        from backend.app.routers.plants import require_write
        from fastapi import HTTPException
        require_facility_capability(self.context,self.engine,'cultivation')
        if not self.context.user_id:
            raise HTTPException(401,'Authentication required.')
        if write:
            require_write(self.context)
            if connections and self.context.role.casefold() not in {'dev','admin'}:
                raise HTTPException(403,'Facility administrator required.')
            if session is not None and self.engine.dialect.name == 'sqlite':
                # SQLite ignores FOR UPDATE. Acquire its write reservation before
                # the permission/configuration reads to serialize overlapping changes.
                session.execute(text('BEGIN IMMEDIATE'))
            require_permission(self.context,self.engine,'cultivation.manage_connections' if connections else 'cultivation.manage_intelligence',session=session)
            if session is not None:
                actor = session.get(AppUser,self.context.user_id)
                if actor is None or not actor.active or (actor.organization_id != self.org and self.context.role.casefold() != 'dev'):
                    raise HTTPException(403,'Active application user required.')
                # Serializes recipe version allocation and cross-cycle membership on PostgreSQL.
                session.execute(select(Facility.id).where(Facility.id == self.facility,Facility.organization_id == self.org).with_for_update())

    def scope(self, model):
        return (model.organization_id == self.org, model.facility_id == self.facility)

    def get(self, session, model, identity, *, lock=False):
        query = select(model).where(*self.scope(model),model.id == identity)
        row = session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise LookupError('Record not found in the active facility.')
        return row

    def bump(self, session, row, version):
        changed = session.execute(update(type(row)).where(*self.scope(type(row)),type(row).id == row.id,type(row).version == version).values(version=version+1).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise TelemetryConflict('Version changed; refresh before retrying.')
        session.refresh(row)

    def audit(self, session, row, action, changes=None):
        record_audit_event(session,organization_id=self.org,facility_id=self.facility,entity_type=row.__tablename__,entity_id=row.id,action=action,actor=self.context.user_id,source='api',correlation_id=new_id(),changes=changes or {})

    def new(self, model, **kwargs):
        return model(id=new_id(),organization_id=self.org,facility_id=self.facility,**kwargs)

    def flags(self):
        from backend.app.permissions import permission_snapshot
        from backend.app.routers.plants import WRITE_ROLES
        effective = permission_snapshot(self.context,self.engine)['effective']
        return {'can_manage':self.context.role.casefold() in WRITE_ROLES and effective['cultivation.manage_intelligence'], 'can_manage_connections':self.context.role.casefold() in {'dev','admin'} and effective['cultivation.manage_connections']}

    def create_cycle(self, payload):
        p = CycleInput.model_validate(payload)
        with Session(self.engine) as s, s.begin():
            self.authorize(write=True,session=s)
            if p.nursery_group_id:
                self.get(s,CultivationPlantGroup,p.nursery_group_id)
            if p.recipe_id:
                recipe = self.get(s,CultivationRecipe,p.recipe_id)
                if recipe.status != 'approved':
                    raise ValueError('Cycle requires an approved recipe version.')
            row = self.new(CropCycle,**p.model_dump(),created_by=self.context.user_id,version=1,status='planned')
            s.add(row); s.flush(); self.audit(s,row,'cycle_created')
            return cycle_payload(row)

    def occupancy(self, identity, payload):
        p = OccupancyInput.model_validate(payload)
        with Session(self.engine) as s, s.begin():
            self.authorize(write=True,session=s)
            cycle = self.get(s,CropCycle,identity,lock=True)
            self.bump(s,cycle,p.version)
            if cycle.status in {'harvested','closed','cancelled'}:
                raise TelemetryConflict('Cycle is no longer open.')
            self.get(s,CultivationRoom,p.room_id)
            if cycle.started_on and p.entered_at.date() < cycle.started_on:
                raise ValueError('Occupancy cannot precede cycle start.')
            if p.zone_id and self.get(s,EnvironmentalZone,p.zone_id).room_id != p.room_id:
                raise ValueError('Zone does not belong to room.')
            if p.stage_id:
                stage = self.get(s,CultivationRecipeStage,p.stage_id)
                if stage.recipe_id != cycle.recipe_id or self.get(s,CultivationRecipe,stage.recipe_id).status != 'approved':
                    raise ValueError('Stage must belong to the approved cycle recipe.')
            overlap = select(CropCycleRoom.id).where(*self.scope(CropCycleRoom),CropCycleRoom.cycle_id == identity,or_(CropCycleRoom.exited_at.is_(None),CropCycleRoom.exited_at > p.entered_at))
            if p.exited_at:
                overlap = overlap.where(CropCycleRoom.entered_at < p.exited_at)
            if s.scalar(overlap.limit(1)):
                raise TelemetryConflict('Cycle occupancy intervals overlap.')
            row = self.new(CropCycleRoom,cycle_id=identity,assigned_by=self.context.user_id,**p.model_dump(exclude={'version'}))
            s.add(row); cycle.status='active'; s.flush(); self.audit(s,cycle,'occupancy_added',{'occupancy_id':row.id})
            return {'id':row.id,'version':cycle.version}

    def members(self, identity, payload):
        p = MembersInput.model_validate(payload)
        with Session(self.engine) as s, s.begin():
            self.authorize(write=True,session=s)
            cycle = self.get(s,CropCycle,identity,lock=True); self.bump(s,cycle,p.version)
            if cycle.harvest_id or cycle.status in {'closed','cancelled'}:
                raise TelemetryConflict('Linked or closed cycle membership is immutable.')
            if cycle.started_on and p.effective_at.date() < cycle.started_on:
                raise ValueError('Membership cannot precede cycle start.')
            plants = s.scalars(select(CultivationPlant).where(*self.scope(CultivationPlant),CultivationPlant.id.in_(p.plant_ids)).order_by(CultivationPlant.id).with_for_update()).all()
            if len(plants) != len(p.plant_ids):
                raise LookupError('Plant not found in the active facility.')
            rows = s.scalars(select(CropCyclePlant).where(*self.scope(CropCyclePlant),CropCyclePlant.plant_id.in_(p.plant_ids),or_(CropCyclePlant.removed_at.is_(None),CropCyclePlant.removed_at > p.effective_at))).all()
            if p.action == 'add':
                if rows:
                    raise TelemetryConflict('Plant membership overlaps an existing cycle interval.')
                for plant in plants:
                    if plant.phase in {'harvested','destroyed'}:
                        raise ValueError('Retired plants cannot join a cycle.')
                    s.add(self.new(CropCyclePlant,cycle_id=identity,plant_id=plant.id,added_at=p.effective_at,added_by=self.context.user_id))
            else:
                if len(rows) != len(plants) or any(r.cycle_id != identity or utc(r.added_at) >= p.effective_at for r in rows):
                    raise TelemetryConflict('No exact active membership interval to close.')
                for row in rows:
                    row.removed_at=p.effective_at
            self.audit(s,cycle,'members_'+p.action,{'plant_ids':p.plant_ids,'effective_at':p.effective_at.isoformat()})
            return {'id':identity,'version':cycle.version,'changed':len(plants)}

    def close_occupancy(self, identity, occupancy_id, payload):
        p=OccupancyCloseInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,session=s)
            cycle=self.get(s,CropCycle,identity,lock=True);self.bump(s,cycle,p.version)
            row=self.get(s,CropCycleRoom,occupancy_id,lock=True)
            if row.cycle_id!=identity:raise LookupError('Occupancy does not belong to cycle.')
            if row.exited_at is not None:raise TelemetryConflict('Occupancy is already closed.')
            if p.exited_at<=utc(row.entered_at) or p.exited_at<datetime.now(timezone.utc):
                raise ValueError('Close time must follow entry and cannot rewrite past attribution.')
            row.exited_at=p.exited_at
            self.audit(s,cycle,'occupancy_closed',{'occupancy_id':row.id,'exited_at':p.exited_at.isoformat()})
            return {'id':row.id,'version':cycle.version}

    def create_zone(self, room_id, payload):
        p=ZoneInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            self.get(s,CultivationRoom,room_id,lock=True)
            row=self.new(EnvironmentalZone,room_id=room_id,**p.model_dump());s.add(row);s.flush();self.audit(s,row,'zone_created')
            return fields(row,'id room_id zone_code display_name active')

    def zones(self, room_id):
        self.authorize()
        with Session(self.engine) as s:
            self.get(s,CultivationRoom,room_id)
            rows=s.scalars(select(EnvironmentalZone).where(*self.scope(EnvironmentalZone),EnvironmentalZone.room_id==room_id).order_by(EnvironmentalZone.zone_code).limit(LIMIT+1)).all()
            return {'zones':[fields(r,'id room_id zone_code display_name active') for r in rows[:LIMIT]],'truncated':len(rows)>LIMIT}

    def device_mappings(self, identity):
        return self._device_children(identity,DeviceMapping,'mappings','id device_id room_id zone_id effective_at',DeviceMapping.effective_at.desc())

    def sensors(self, identity):
        return self._device_children(identity,CultivationSensor,'sensors','id device_id source_channel source_metric source_unit metric unit',CultivationSensor.source_channel)

    def _device_children(self,identity,model,key,names,order):
        self.authorize()
        with Session(self.engine) as s:
            self.get(s,CultivationDevice,identity)
            rows=s.scalars(select(model).where(*self.scope(model),model.device_id==identity).order_by(order,model.id).limit(LIMIT+1)).all()
            return {key:[fields(r,names) for r in rows[:LIMIT]],'truncated':len(rows)>LIMIT}

    def link_harvest(self, identity, payload):
        p = HarvestInput.model_validate(payload)
        with Session(self.engine) as s, s.begin():
            self.authorize(write=True,session=s)
            cycle = self.get(s,CropCycle,identity,lock=True); self.bump(s,cycle,p.version)
            harvest = self.get(s,CultivationHarvest,p.harvest_id,lock=True)
            if harvest.status=='cancelled' or cycle.status in {'cancelled','closed'}:
                raise TelemetryConflict('Cancelled or closed records cannot be linked.')
            if cycle.harvest_id:
                raise TelemetryConflict('Harvest link is immutable.')
            if harvest.harvested_at is None:
                raise ValueError('Canonical harvest time is required.')
            at=utc(harvest.harvested_at)
            members=set(s.scalars(select(CropCyclePlant.plant_id).where(*self.scope(CropCyclePlant),CropCyclePlant.cycle_id==identity,CropCyclePlant.added_at<=at,or_(CropCyclePlant.removed_at.is_(None),CropCyclePlant.removed_at>at))))
            harvested=set(s.scalars(select(CultivationHarvestPlant.plant_id).where(*self.scope(CultivationHarvestPlant),CultivationHarvestPlant.harvest_id==harvest.id)))
            if not members or members != harvested:
                raise ValueError('Harvest must contain exactly the cycle members at harvest time.')
            if s.scalar(select(CropCycle.id).where(*self.scope(CropCycle),CropCycle.harvest_id==harvest.id)):
                raise TelemetryConflict('Harvest is already allocated to a cycle.')
            cycle.harvest_id=harvest.id; cycle.status='harvested'
            self.audit(s,cycle,'harvest_linked',{'harvest_id':harvest.id,'allocation':'exclusive_exact_membership'})
            return cycle_payload(cycle)

    def recipes(self):
        self.authorize()
        with Session(self.engine) as s:
            return self._recipes(s)

    def _recipes(self, s, identity=None):
        query=select(CultivationRecipe).where(*self.scope(CultivationRecipe))
        if identity:query=query.where(CultivationRecipe.id==identity)
        recipes=s.scalars(query.order_by(CultivationRecipe.name,CultivationRecipe.version.desc()).limit(LIMIT+1)).all()
        stages=s.scalars(select(CultivationRecipeStage).where(*self.scope(CultivationRecipeStage),CultivationRecipeStage.recipe_id.in_([r.id for r in recipes[:LIMIT]])).order_by(CultivationRecipeStage.sequence)).all()
        targets=s.scalars(select(CultivationRecipeTarget).where(*self.scope(CultivationRecipeTarget),CultivationRecipeTarget.stage_id.in_([r.id for r in stages]))).all()
        target_map={}; stage_map={}
        for t in targets:
            target_map.setdefault(t.stage_id,[]).append(target_payload(t))
        for stage in stages:
            stage_map.setdefault(stage.recipe_id,[]).append({**fields(stage,'id stage_key display_name sequence'),'targets':target_map.get(stage.id,[])})
        return {'recipes':[{**fields(r,'id name version status description approved_by approved_at'),'stages':stage_map.get(r.id,[])} for r in recipes[:LIMIT]],'truncated':len(recipes)>LIMIT}

    def create_recipe(self,payload):
        p=RecipeInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,session=s)
            version=(s.scalar(select(func.max(CultivationRecipe.version)).where(*self.scope(CultivationRecipe),CultivationRecipe.name==p.name)) or 0)+1
            row=self.new(CultivationRecipe,name=p.name,description=p.description,version=version,created_by=self.context.user_id,status='draft')
            s.add(row); s.flush()
            for stage in p.stages:
                record=self.new(CultivationRecipeStage,recipe_id=row.id,**stage.model_dump(exclude={'targets'})); s.add(record); s.flush()
                s.add_all([self.new(CultivationRecipeTarget,stage_id=record.id,**target.model_dump()) for target in stage.targets])
            s.flush(); self.audit(s,row,'recipe_created')
            return self._recipes(s,row.id)['recipes'][0]

    def approve_recipe(self,identity,payload):
        p=VersionInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,session=s)
            row=self.get(s,CultivationRecipe,identity,lock=True)
            if row.version != p.version or row.status != 'draft':
                raise TelemetryConflict('Recipe version is already approved or changed.')
            changed=s.execute(update(CultivationRecipe).where(*self.scope(CultivationRecipe),CultivationRecipe.id==identity,CultivationRecipe.status=='draft',CultivationRecipe.version==p.version).values(status='approved',approved_by=self.context.user_id,approved_at=datetime.now(timezone.utc)))
            if changed.rowcount != 1:
                raise TelemetryConflict('Recipe approval changed concurrently.')
            s.refresh(row); self.audit(s,row,'recipe_approved',{'version':row.version})
            return self._recipes(s,identity)['recipes'][0]

    def event(self,payload):
        p=EventInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,session=s)
            if not p.room_id and not p.cycle_id:
                raise ValueError('Room or cycle required.')
            if p.room_id:self.get(s,CultivationRoom,p.room_id)
            if p.cycle_id:self.get(s,CropCycle,p.cycle_id)
            if p.room_id and p.cycle_id and not s.scalar(select(CropCycleRoom.id).where(*self.scope(CropCycleRoom),CropCycleRoom.room_id==p.room_id,CropCycleRoom.cycle_id==p.cycle_id,CropCycleRoom.entered_at<=p.occurred_at,or_(CropCycleRoom.exited_at.is_(None),CropCycleRoom.exited_at>p.occurred_at)).limit(1)):
                raise ValueError('Room and cycle are not related at event time.')
            row=self.new(CultivationOperationalEvent,**p.model_dump(),actor=self.context.user_id);s.add(row);s.flush();self.audit(s,row,'event_recorded')
            return {'id':row.id}

    def connections(self):
        self.authorize()
        with Session(self.engine) as s:
            rows=s.scalars(select(TelemetryConnection).where(*self.scope(TelemetryConnection)).order_by(TelemetryConnection.id).limit(LIMIT+1)).all()
            imported=self._last_imports(s,[r.id for r in rows[:LIMIT]])
            return {'connections':[{**connection_payload(r),'last_import_at':imported.get(r.id)} for r in rows[:LIMIT]],'truncated':len(rows)>LIMIT}

    def _last_imports(self,session,identities):
        return dict(session.execute(select(AuditEvent.entity_id,func.max(AuditEvent.occurred_at)).where(
            *self.scope(AuditEvent),AuditEvent.entity_type=='cultivation_telemetry_connections',
            AuditEvent.entity_id.in_(identities),AuditEvent.action=='local_export_imported').group_by(AuditEvent.entity_id)).all())

    def create_connection(self,payload):
        p=ConnectionInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            row=self.new(TelemetryConnection,**p.model_dump(),created_by=self.context.user_id,status='configured',version=1)
            s.add(row);s.flush();self.audit(s,row,'connection_configured')
            return connection_payload(row)

    def connection(self,s,identity):
        row=self.get(s,TelemetryConnection,identity,lock=True)
        if row.revoked_at:raise TelemetryConflict('Connection is revoked.')
        return row

    def revoke(self,identity,payload):
        p=VersionInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            row=self.get(s,TelemetryConnection,identity,lock=True);self.bump(s,row,p.version)
            row.revoked_at=datetime.now(timezone.utc);row.status='revoked';self.audit(s,row,'connection_revoked')
            return connection_payload(row)

    def devices(self,identity):
        self.authorize()
        with Session(self.engine) as s:
            self.get(s,TelemetryConnection,identity)
            rows=s.scalars(select(CultivationDevice).where(*self.scope(CultivationDevice),CultivationDevice.connection_id==identity).order_by(CultivationDevice.id).limit(LIMIT+1)).all()
            return {'devices':[fields(r,'id connection_id source_device_id display_name active version') for r in rows[:LIMIT]],'truncated':len(rows)>LIMIT}

    def create_device(self,identity,payload):
        p=DeviceInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            connection=self.connection(s,identity);self.bump(s,connection,p.version)
            row=self.new(CultivationDevice,connection_id=identity,version=1,**p.model_dump(exclude={'version'}));s.add(row);s.flush();self.audit(s,row,'device_registered')
            return {'id':row.id,'version':row.version,'connection_version':connection.version}

    def map_device(self,identity,payload):
        p=MappingInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            device=self.get(s,CultivationDevice,identity,lock=True);connection=self.connection(s,device.connection_id);self.bump(s,device,p.version);self.bump(s,connection,connection.version)
            self.get(s,CultivationRoom,p.room_id)
            if p.zone_id and self.get(s,EnvironmentalZone,p.zone_id).room_id != p.room_id:raise ValueError('Zone belongs to another room.')
            latest=s.scalar(select(func.max(DeviceMapping.effective_at)).where(*self.scope(DeviceMapping),DeviceMapping.device_id==identity))
            if latest and (p.effective_at < datetime.now(timezone.utc) or p.effective_at <= utc(latest)):
                raise ValueError('Remapping must be future-effective and later than previous mappings.')
            row=self.new(DeviceMapping,device_id=identity,created_by=self.context.user_id,**p.model_dump(exclude={'version'}));s.add(row);s.flush();self.audit(s,device,'device_mapped',{'mapping_id':row.id})
            return {'id':row.id,'version':device.version,'connection_version':connection.version}

    def create_sensor(self,identity,payload):
        p=SensorInput.model_validate(payload);metric=canonical_metric(p.metric)
        # Validate unit compatibility without inventing a measurement.
        probe=1 if metric=='irrigation_event' else 0
        if metric=='temperature' or metric=='substrate_temperature':probe=20
        normalize_metric_value(metric,probe,p.source_unit)
        with Session(self.engine) as s,s.begin():
            self.authorize(write=True,connections=True,session=s)
            device=self.get(s,CultivationDevice,identity,lock=True);connection=self.connection(s,device.connection_id);self.bump(s,device,p.version);self.bump(s,connection,connection.version)
            row=self.new(CultivationSensor,device_id=identity,source_channel=p.source_channel,source_metric=p.source_metric,source_unit=p.source_unit,metric=metric,unit=CANONICAL_UNITS[metric]);s.add(row);s.flush();self.audit(s,device,'sensor_registered',{'sensor_id':row.id})
            return {'id':row.id,'version':device.version,'connection_version':connection.version}

    def workspace(self):
        self.authorize()
        with Session(self.engine) as s:
            rooms=s.scalars(select(CultivationRoom).where(*self.scope(CultivationRoom)).order_by(CultivationRoom.room_code).limit(LIMIT+1)).all()
            cycles=s.scalars(select(CropCycle).where(*self.scope(CropCycle)).order_by(CropCycle.cycle_code).limit(LIMIT+1)).all()
            recipes=self._recipes(s)
            cards=self._room_cards(s,rooms[:LIMIT])
        connections=self.connections()
        return {'rooms':cards,'cycles':[cycle_payload(r) for r in cycles[:LIMIT]],'recipes':recipes['recipes'],'connections':connections['connections'],'truncated':len(rooms)>LIMIT or len(cycles)>LIMIT or recipes['truncated'] or connections['truncated'] or any(r['context_truncated'] for r in cards),'decision_support_only':True,**self.flags()}

    def _room_cards(self,s,rooms):
        now=datetime.now(timezone.utc)
        counts=dict(s.execute(select(CultivationPlant.room_code,func.count(CultivationPlant.id)).where(*self.scope(CultivationPlant),CultivationPlant.room_code.in_([r.room_code for r in rooms]),CultivationPlant.phase.notin_(['harvested','destroyed'])).group_by(CultivationPlant.room_code)).all())
        # One bounded context query for the entire workspace, not one per room.
        rows=s.execute(select(CropCycleRoom.room_id,CropCycleRoom.cycle_id,CropCycleRoom.stage_id,CultivationRecipeStage.stage_key,CultivationRecipeStage.display_name).outerjoin(CultivationRecipeStage,(CultivationRecipeStage.id==CropCycleRoom.stage_id)&(CultivationRecipeStage.organization_id==self.org)&(CultivationRecipeStage.facility_id==self.facility)).where(*self.scope(CropCycleRoom),CropCycleRoom.room_id.in_([r.id for r in rooms]),CropCycleRoom.entered_at<=now,or_(CropCycleRoom.exited_at.is_(None),CropCycleRoom.exited_at>now)).order_by(CropCycleRoom.room_id,CropCycleRoom.id).limit(LIMIT+1)).mappings().all()
        context={}
        for row in rows[:LIMIT]:context.setdefault(row['room_id'],[]).append({k:row[k] for k in ('cycle_id','stage_id','stage_key','display_name')})
        cards=[]
        for room in rooms:
            current=context.get(room.id,[]);stages=[r for r in current if r['stage_id']]
            cards.append({**room_payload(room),'plant_count':counts.get(room.room_code,0),'current_cycle_ids':sorted({r['cycle_id'] for r in current}),'current_stages':stages,'current_stage':stages[0] if len(current)==1 and stages and len(rows)<=LIMIT else None,'context_truncated':len(rows)>LIMIT})
        return cards

    def room(self,identity):
        self.authorize();now=datetime.now(timezone.utc)
        with Session(self.engine) as s:
            room=self.get(s,CultivationRoom,identity)
            plants=s.scalars(select(CultivationPlant).where(*self.scope(CultivationPlant),CultivationPlant.room_code==room.room_code,CultivationPlant.phase.notin_(['harvested','destroyed'])).order_by(CultivationPlant.id).limit(LIMIT+1)).all()
            cycles=s.scalars(select(CropCycle).where(*self.scope(CropCycle),CropCycle.id.in_(select(CropCycleRoom.cycle_id).where(*self.scope(CropCycleRoom),CropCycleRoom.room_id==identity,CropCycleRoom.entered_at<=now,or_(CropCycleRoom.exited_at.is_(None),CropCycleRoom.exited_at>now)))).limit(LIMIT+1)).all()
            events=s.scalars(select(CultivationOperationalEvent).where(*self.scope(CultivationOperationalEvent),CultivationOperationalEvent.room_id==identity).order_by(CultivationOperationalEvent.occurred_at.desc()).limit(LIMIT+1)).all()
            work=s.scalars(select(WorkItem).where(*self.scope(WorkItem),WorkItem.entity_type=='cultivation_room',WorkItem.entity_id==identity).limit(LIMIT+1)).all()
            zones=s.scalars(select(EnvironmentalZone).where(*self.scope(EnvironmentalZone),EnvironmentalZone.room_id==identity).order_by(EnvironmentalZone.zone_code).limit(LIMIT+1)).all()
            recorded_cost=s.execute(select(func.count(CultivationCostEntry.id),func.sum(CultivationCostEntry.amount)).where(*self.scope(CultivationCostEntry),CultivationCostEntry.entity_type=='room',CultivationCostEntry.entity_id==identity)).one()
            approved_targets=s.execute(select(CropCycleRoom.cycle_id,CultivationRecipe.id.label('recipe_id'),CultivationRecipe.version.label('recipe_version'),CultivationRecipeStage.id.label('stage_id'),CultivationRecipeStage.stage_key,CultivationRecipeTarget.metric,CultivationRecipeTarget.minimum,CultivationRecipeTarget.maximum,CultivationRecipeTarget.unit,CultivationRecipeTarget.threshold_seconds).join(CultivationRecipeStage,CultivationRecipeStage.id==CropCycleRoom.stage_id).join(CultivationRecipe,CultivationRecipe.id==CultivationRecipeStage.recipe_id).join(CultivationRecipeTarget,CultivationRecipeTarget.stage_id==CultivationRecipeStage.id).where(*self.scope(CropCycleRoom),*self.scope(CultivationRecipeStage),*self.scope(CultivationRecipe),*self.scope(CultivationRecipeTarget),CropCycleRoom.room_id==identity,CropCycleRoom.entered_at<=now,or_(CropCycleRoom.exited_at.is_(None),CropCycleRoom.exited_at>now),CultivationRecipe.status=='approved',CultivationRecipe.approved_at<=now).limit(LIMIT+1)).mappings().all()
            environment=TelemetryService(self.engine).snapshot(self.org,self.facility,identity,session=s)
            return {'room':room_payload(room),'zones':[fields(z,'id room_id zone_code display_name active') for z in zones[:LIMIT]],'plants':[fields(p,'id plant_tag phase') for p in plants[:LIMIT]],'cycles':[cycle_payload(c) for c in cycles[:LIMIT]],'environment':environment,'edge_summary':None,'events':[fields(e,'id event_type title notes occurred_at') for e in events[:LIMIT]],'work':[fields(w,'id title') for w in work[:LIMIT]],'approved_targets':[{**dict(t),'alert_threshold_status':'configured' if t['threshold_seconds'] is not None else 'not_configured'} for t in approved_targets[:LIMIT]],'costs':{'total':None,'allocation_status':'unknown','recorded_total':recorded_cost[1],'recorded_entry_count':recorded_cost[0],'period':'all_recorded_room_entries','provenance':'cultivation_cost_entries'},'truncated':any(len(x)>LIMIT for x in (plants,cycles,events,work,zones,approved_targets)),**self.flags()}

    def cycle(self,identity):
        self.authorize()
        with Session(self.engine) as s:
            cycle=self.get(s,CropCycle,identity)
            members=s.scalars(select(CropCyclePlant).where(*self.scope(CropCyclePlant),CropCyclePlant.cycle_id==identity).order_by(CropCyclePlant.added_at).limit(LIMIT+1)).all()
            occupancy=s.scalars(select(CropCycleRoom).where(*self.scope(CropCycleRoom),CropCycleRoom.cycle_id==identity).order_by(CropCycleRoom.entered_at.desc(),CropCycleRoom.id).limit(LIMIT+1)).all()
            harvest=self.get(s,CultivationHarvest,cycle.harvest_id) if cycle.harvest_id else None
            post_harvest=s.scalar(select(CultivationPostHarvestBatch).where(*self.scope(CultivationPostHarvestBatch),CultivationPostHarvestBatch.harvest_id==cycle.harvest_id)) if harvest else None
            transformations=s.scalars(select(MaterialTransformation).where(*self.scope(MaterialTransformation),MaterialTransformation.source_entity_type=='harvest',MaterialTransformation.source_entity_id==cycle.harvest_id).order_by(MaterialTransformation.id).limit(LIMIT+1)).all() if harvest else []
            outputs=s.scalars(select(MaterialTransformationOutput).join(InventoryLot,InventoryLot.id==MaterialTransformationOutput.lot_id).where(*self.scope(MaterialTransformationOutput),*self.scope(InventoryLot),MaterialTransformationOutput.transformation_id.in_([t.id for t in transformations[:LIMIT]])).order_by(MaterialTransformationOutput.id).limit(LIMIT+1)).all() if transformations else []
            quality=s.scalars(select(LotQualityEvidence).where(*self.scope(LotQualityEvidence),LotQualityEvidence.lot_id.in_([o.lot_id for o in outputs[:LIMIT]])).limit(LIMIT+1)).all() if outputs else []
            # Only exact exclusive harvest allocation is currently proven. Room/plant cost splitting stays unknown.
            costs=s.scalars(select(CultivationCostEntry).where(*self.scope(CultivationCostEntry),CultivationCostEntry.entity_type=='harvest',CultivationCostEntry.entity_id==cycle.harvest_id).limit(LIMIT+1)).all() if harvest else []
            events=s.scalars(select(CultivationOperationalEvent).where(*self.scope(CultivationOperationalEvent),CultivationOperationalEvent.cycle_id==identity).order_by(CultivationOperationalEvent.occurred_at.desc()).limit(LIMIT+1)).all()
            return {'cycle':cycle_payload(cycle),'approved_recipe':self._recipes(s,cycle.recipe_id)['recipes'][0] if cycle.recipe_id else None,'members':[fields(r,'id plant_id added_at removed_at') for r in members[:LIMIT]],'occupancy':[fields(r,'id room_id zone_id stage_id entered_at exited_at') for r in reversed(occupancy[:LIMIT])],'harvest':fields(harvest,'id harvest_code status wet_weight_g dry_weight_g harvested_at') if harvest else None,'economics':{'allocated_cost':sum(c.amount for c in costs) if costs and len(costs)<=LIMIT else None,'allocation_status':'partial_exclusive_harvest' if costs else 'unknown','provenance':[{'cost_entry_id':c.id,'amount':c.amount,'allocation':'exclusive_exact_harvest_membership'} for c in costs[:LIMIT]],'true_cogs':None},'events':[fields(e,'id event_type title notes occurred_at') for e in events[:LIMIT]],'post_harvest':fields(post_harvest,'id harvest_id stage location_code started_at completed_at') if post_harvest else None,'lineage':[fields(t,'id transformation_type source_entity_type source_entity_id status') for t in transformations[:LIMIT]],'lineage_outputs':[fields(o,'id transformation_id lot_id quantity unit measurement_basis') for o in outputs[:LIMIT]],'quality':[fields(q,'lot_id lab_testing_state coa_document_id evidence_source verified_at') for q in quality[:LIMIT]],'truncated':any(len(x)>LIMIT for x in (members,occupancy,costs,events,transformations,outputs,quality)),**self.flags()}

    def exposure(self,identity):
        self.authorize()
        with Session(self.engine) as s:
            plant=self.get(s,CultivationPlant,identity)
            members=s.scalars(select(CropCyclePlant).where(*self.scope(CropCyclePlant),CropCyclePlant.plant_id==identity).order_by(CropCyclePlant.added_at,CropCyclePlant.id).limit(LIMIT+1)).all()
            occupancy=s.scalars(select(CropCycleRoom).where(*self.scope(CropCycleRoom),CropCycleRoom.cycle_id.in_([m.cycle_id for m in members[:LIMIT]])).order_by(CropCycleRoom.entered_at,CropCycleRoom.id).limit(LIMIT+1)).all()
            groups=s.scalars(select(CultivationPlantGroupMember.group_id).join(CultivationPlantGroup,CultivationPlantGroup.id==CultivationPlantGroupMember.group_id).where(*self.scope(CultivationPlantGroup),*self.scope(CultivationPlantGroupMember),CultivationPlantGroupMember.plant_id==identity).order_by(CultivationPlantGroupMember.group_id).limit(LIMIT+1)).all()
            harvests=s.scalars(select(CultivationHarvestPlant.harvest_id).join(CultivationHarvest,CultivationHarvest.id==CultivationHarvestPlant.harvest_id).where(*self.scope(CultivationHarvest),*self.scope(CultivationHarvestPlant),CultivationHarvestPlant.plant_id==identity).order_by(CultivationHarvestPlant.harvest_id).limit(LIMIT+1)).all()
            parent=s.scalar(select(CultivationPlantParentLink.parent_plant_id).join(CultivationPlant,CultivationPlant.id==CultivationPlantParentLink.parent_plant_id).where(*self.scope(CultivationPlant),*self.scope(CultivationPlantParentLink),CultivationPlantParentLink.child_plant_id==identity,CultivationPlantParentLink.relationship=='mother'))
            prefix='/api/v1/cultivation-intelligence'
            return {'plant_id':identity,'exposure_status':'unknown','intervals':[],'reason':'Canonical individual room movement intervals are not established by crop membership; cohort telemetry is not confirmed individual exposure.',
                    'memberships':[{**fields(m,'id cycle_id added_at removed_at'),'cycle_url':f'{prefix}/cycles/{m.cycle_id}'} for m in members[:LIMIT]],
                    'cohort_occupancy':[{**fields(o,'id cycle_id room_id zone_id stage_id entered_at exited_at'),'room_url':f'{prefix}/rooms/{o.room_id}','cycle_url':f'{prefix}/cycles/{o.cycle_id}','evidence_basis':'cycle_occupancy_not_individual_movement'} for o in occupancy[:LIMIT] if any(m.cycle_id==o.cycle_id and (m.removed_at is None or utc(o.entered_at)<utc(m.removed_at)) and (o.exited_at is None or utc(m.added_at)<utc(o.exited_at)) for m in members[:LIMIT])],
                    'relationships':{'mother_plant_tag':plant.mother_plant_tag or None,'mother_plant_id':parent,'group_ids':groups[:LIMIT],'harvest_ids':harvests[:LIMIT]},'truncated':any(len(r)>LIMIT for r in (members,occupancy,groups,harvests))}
