"""Guided network setup extends existing encrypted connections and room mappings."""
from datetime import datetime,timezone
import json
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from modules.coman.models import new_id
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration
from ..intelligence_service import IntelligenceService
from ..intelligence_models import TelemetryConnection,CultivationDevice,CultivationSensor,DeviceMapping,EnvironmentalZone
from ..models import CultivationRoom
from ..metrics import canonical_metric,normalize_metric_value
from .contracts import NetworkError,fingerprint
from .schemas import ConnectionInput,ApproveInput,checked_options

class NetworkService(IntelligenceService):
    def __init__(self,engine,context,encryption_key,runtime):
        super().__init__(engine,context)
        self.encryption_key=encryption_key;self.runtime=runtime

    def host(self):
        if self.runtime is None or not self.runtime.config.matches(self.org,self.facility):
            raise HTTPException(409,'Network collection is not configured for this facility host.')
        return self.runtime

    def manager(self,session=None):
        self.authorize(write=True,connections=True,session=session)
        return self.host()

    def connection_config(self,session,identity,lock=False):
        connection=self.get(session,TelemetryConnection,identity,lock=lock)
        config=self.get(session,IntegrationConfiguration,connection.integration_configuration_id,lock=lock)
        if connection.mode!='network' or config.provider!='cultivation_network' or connection.revoked_at:
            raise NetworkError('network_connection_unavailable')
        try:data=json.loads(config.configuration_json)
        except ValueError:raise NetworkError('configuration_unavailable') from None
        return connection,config,data

    def create(self,payload,api_key):
        self.manager()
        p=ConnectionInput.model_validate(payload)
        options=checked_options(p.adapter,p.options)
        if p.stale_after_seconds<p.expected_interval_seconds:raise NetworkError('invalid_stale_interval')
        if not isinstance(api_key,str) or not 16<=len(api_key)<=1024 or any(c.isspace() for c in api_key):
            raise NetworkError('invalid_credential')
        if p.adapter=='aranet_cloud' and len(api_key)!=32:raise NetworkError('invalid_credential')
        if p.adapter=='things_stack':self.host().config.verify_mqtt()
        cipher=IntegrationConfigurationService(self.engine,self.encryption_key).cipher
        with Session(self.engine) as s,s.begin():
            self.manager(s)
            count=s.scalar(select(func.count()).select_from(TelemetryConnection).where(*self.scope(TelemetryConnection),TelemetryConnection.mode=='network'))
            if count>=8:raise NetworkError('connection_limit')
            identity=new_id()
            config=IntegrationConfiguration(id=new_id(),organization_id=self.org,facility_id=self.facility,
                provider='cultivation_network',scope_type='facility',scope_key=f'{self.org}:{self.facility}:network:{identity}',
                configuration_json=json.dumps({'adapter':p.adapter,'options':options,'enabled':False,'devices':[]}),
                encrypted_secret=cipher.encrypt(api_key.encode()).decode(),secret_hint='',status='configured',updated_by=self.context.user_id)
            s.add(config);s.flush()
            row=self.new(TelemetryConnection,provider='json',mode='network',label=p.label,
                integration_configuration_id=config.id,status='configured',version=1,created_by=self.context.user_id,
                expected_interval_seconds=p.expected_interval_seconds,stale_after_seconds=p.stale_after_seconds)
            row.id=identity
            s.add(row);s.flush()
            self.audit(s,row,'network_connection_saved',{'adapter':p.adapter,'credential_saved':True,'enabled':False})
            return {'id':identity,'version':row.version,'adapter':p.adapter,'enabled':False,'validated':False}

    def discover(self,identity):
        runtime=self.manager()
        with Session(self.engine) as s:
            row,config,data=self.connection_config(s,identity)
            return runtime.discover(self.context.user_id,self.org,self.facility,identity,row.version)

    def preview(self,identity,preview_id):
        runtime=self.manager()
        with Session(self.engine) as s:
            row,_,_=self.connection_config(s,identity)
        return runtime.preview(self.context.user_id,self.org,self.facility,identity,row.version,preview_id)

    def approve(self,identity,payload):
        p=ApproveInput.model_validate(payload)
        with Session(self.engine) as s,s.begin():
            runtime=self.manager(s)
            row,config,data=self.connection_config(s,identity,lock=True)
            preview=runtime.preview(self.context.user_id,self.org,self.facility,identity,row.version,p.preview_id)
            if preview['state'] not in ('complete','listening'):raise NetworkError('discovery_not_ready')
            offered={device['id']:device for device in preview['devices']}
            if len({d.source_id for d in p.devices})!=len(p.devices):raise NetworkError('duplicate_device_selection')
            now=datetime.now(timezone.utc);approved=[]
            for choice in p.devices:
                found=offered.get(choice.source_id)
                if not found:raise NetworkError('device_not_in_verified_preview')
                room=self.get(s,CultivationRoom,choice.room_id)
                if not room.active:raise NetworkError('room_inactive')
                if choice.zone_id:
                    zone=self.get(s,EnvironmentalZone,choice.zone_id)
                    if not zone.active or zone.room_id!=room.id:raise NetworkError('zone_scope_mismatch')
                source_id=('aranet:' if data['adapter']=='aranet_cloud' else 'tts:')+choice.source_id
                device=s.scalar(select(CultivationDevice).where(*self.scope(CultivationDevice),CultivationDevice.connection_id==identity,CultivationDevice.source_device_id==source_id))
                if device is None:
                    device=self.new(CultivationDevice,connection_id=identity,source_device_id=source_id,display_name=found['name'],active=True,version=1)
                    s.add(device);s.flush()
                elif not device.active:raise NetworkError('device_inactive')
                streams={stream['source_channel']:stream for stream in found['streams']}
                if len({c.source_channel for c in choice.streams})!=len(choice.streams):raise NetworkError('duplicate_stream')
                selected=[]
                for selection in choice.streams:
                    stream=streams.get(selection.source_channel)
                    if not stream or not stream.get('unit'):raise NetworkError('verified_units_required')
                    metric=canonical_metric(selection.metric)
                    normalize_metric_value(metric,stream['sample_value'],stream['unit'])
                    sensor=s.scalar(select(CultivationSensor).where(*self.scope(CultivationSensor),CultivationSensor.device_id==device.id,CultivationSensor.source_channel==selection.source_channel,CultivationSensor.source_metric==stream['source_metric']))
                    _,_,canonical_unit=normalize_metric_value(metric,stream['sample_value'],stream['unit'])
                    if sensor is None:
                        s.add(self.new(CultivationSensor,device_id=device.id,source_channel=selection.source_channel,
                            source_metric=stream['source_metric'],source_unit=stream['unit'],metric=metric,unit=canonical_unit))
                    elif (sensor.metric,sensor.source_unit)!=(metric,stream['unit']):
                        raise NetworkError('existing_sensor_mapping_conflict')
                    selected.append({k:stream[k] for k in ('source_channel','source_metric','source_unit_id','source_unit_label','unit','probe')}|{'metric':metric})
                previous=s.scalar(select(DeviceMapping).where(*self.scope(DeviceMapping),DeviceMapping.device_id==device.id).order_by(DeviceMapping.effective_at.desc()).limit(1))
                if previous is None or (previous.room_id,previous.zone_id)!=(room.id,choice.zone_id):
                    s.add(self.new(DeviceMapping,device_id=device.id,room_id=room.id,zone_id=choice.zone_id,effective_at=now,created_by=self.context.user_id))
                approved.append({'source_id':choice.source_id,'device_id':device.id,'room_id':room.id,
                    'zone_id':choice.zone_id,'streams':selected})
            data.update(devices=approved,enabled=True,approved_at=now.isoformat())
            config.configuration_json=json.dumps(data,sort_keys=True)
            config.status='connected';config.last_validated_at=now;config.last_error='';config.updated_by=self.context.user_id
            self.bump(s,row,row.version)
            self.audit(s,row,'network_devices_approved',{'adapter':data['adapter'],'device_count':len(approved),
                'device_mappings':approved,'provider_controls_enabled':False})
            result={'id':row.id,'version':row.version,'enabled':True,'status':'waiting_for_reading','device_count':len(approved)}
        runtime.invalidate(identity)
        return result

    def active(self,identity,version,enabled):
        with Session(self.engine) as s,s.begin():
            runtime=self.manager(s);row,config,data=self.connection_config(s,identity,lock=True)
            if enabled and (not data.get('devices') or config.status!='connected'):
                raise NetworkError('verify_and_map_devices_first')
            self.bump(s,row,version);data['enabled']=enabled
            if enabled:data['approved_at']=datetime.now(timezone.utc).isoformat()
            config.configuration_json=json.dumps(data,sort_keys=True);config.updated_by=self.context.user_id
            self.audit(s,row,'network_collection_changed',{'enabled':enabled})
            result={'id':identity,'version':row.version,'enabled':enabled}
        runtime.invalidate(identity)
        return result

    def rotate_key(self,identity,version,api_key):
        self.manager()
        if not isinstance(api_key,str) or not 16<=len(api_key)<=1024 or any(c.isspace() for c in api_key):
            raise NetworkError('invalid_credential')
        cipher=IntegrationConfigurationService(self.engine,self.encryption_key).cipher
        with Session(self.engine) as session,session.begin():
            runtime=self.manager(session)
            row,config,data=self.connection_config(session,identity,lock=True)
            if data['adapter']=='aranet_cloud' and len(api_key)!=32:raise NetworkError('invalid_credential')
            self.bump(session,row,version)
            data['enabled']=False
            config.encrypted_secret=cipher.encrypt(api_key.encode()).decode()
            config.configuration_json=json.dumps(data,sort_keys=True)
            config.status='configured';config.last_validated_at=None;config.last_error=''
            config.updated_by=self.context.user_id
            self.audit(session,row,'network_credential_replaced',{'credential_saved':True,'enabled':False,'requires_rediscovery':True})
            result={'id':identity,'version':row.version,'enabled':False,'requires_rediscovery':True}
        runtime.invalidate(identity)
        return result

    def status(self):
        self.authorize()
        ready=bool(self.runtime and self.runtime.config.matches(self.org,self.facility))
        can_manage=False
        if ready:
            try:self.manager();can_manage=True
            except HTTPException:pass
        values=[]
        with Session(self.engine) as s:
            rows=s.execute(select(TelemetryConnection,IntegrationConfiguration).join(IntegrationConfiguration,
                IntegrationConfiguration.id==TelemetryConnection.integration_configuration_id).where(
                    *self.scope(TelemetryConnection),*self.scope(IntegrationConfiguration),TelemetryConnection.mode=='network',
                    IntegrationConfiguration.provider=='cultivation_network').order_by(TelemetryConnection.id).limit(9)).all()
            for row,config in rows[:8]:
                data=json.loads(config.configuration_json)
                health=self.runtime.health(row.id) if ready else {'status':'host_unavailable'}
                if not data.get('enabled') or row.revoked_at:health={**health,'status':'disabled'}
                values.append({'id':row.id,'version':row.version,'label':row.label,'adapter':data['adapter'],
                    'enabled':bool(data.get('enabled')) and not row.revoked_at,'device_count':len(data.get('devices',[])),
                    'expected_interval_seconds':row.expected_interval_seconds,'stale_after_seconds':row.stale_after_seconds,**health})
        mqtt_available=False
        if ready:
            try:self.runtime.config.verify_mqtt();mqtt_available=True
            except NetworkError:pass
        return {'host_ready':ready,'can_manage':can_manage,'mqtt_available':mqtt_available,'connections':values,'truncated':len(rows)>8,
                'adapters':['aranet_cloud','things_stack'],'equipment_controls':False}
