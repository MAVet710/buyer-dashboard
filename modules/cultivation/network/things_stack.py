"""The Things Stack v3 registry and standardized uplinks, never downlinks."""
import math
from .contracts import NetworkError,bounded_rows,object_value,identity,stamp,fingerprint,display,tts_addresses,tts_id
from .http import ReadOnlyHttp

# Official normalized schema only. Soil moisture is NOT assumed to be VWC;
# cumulative water meters are NOT irrigation events. Lux is NOT PPFD.
FIELDS={('air','temperature'):('temperature','C'),('air','relativeHumidity'):('relative_humidity','%'),
        ('air','co2'):('co2','ppm'),('soil','temperature'):('substrate_temperature','C'),
        ('soil','ec'):('substrate_ec','dS/m')}

class ThingsStack:
    def __init__(self,api_key,config,http=None):
        self.registry,self.broker,self.tenant=tts_addresses(config)
        self.application=tts_id(config.get('application_id'))
        if not isinstance(api_key,str) or not 16<=len(api_key)<=1024 or not api_key.isascii() or any(c.isspace() for c in api_key):
            raise NetworkError('invalid_credential')
        self._key=api_key;self.http=http or ReadOnlyHttp()

    def discover(self):
        data=object_value(self.http.get(self.registry,'/api/v3/applications/'+self.application+'/devices',
            {'Authorization':'Bearer '+self._key},{'field_mask':'name','limit':101,'page':1}))
        rows=bounded_rows(data.get('end_devices',[]),101)
        result=[];seen=set()
        for row in rows[:100]:
            ids=object_value(row.get('ids'));device=tts_id(ids.get('device_id'))
            app=object_value(ids.get('application_ids')).get('application_id')
            if app!=self.application or device in seen:raise NetworkError('source_scope_mismatch')
            seen.add(device)
            result.append({'id':device,'name':display(row.get('name'),device),'streams':[],
                           'status':'waiting_for_standardized_sample'})
        return {'devices':result,'truncated':len(rows)>100,'adapter':'things_stack',
                'transport':'mqtt_tls','history_recovery_supported':False}

    def mqtt_settings(self):
        username=self.application+'@'+self.tenant
        return {'host':self.broker,'port':8883,'username':username,'password':self._key,
                'topic':'v3/'+username+'/devices/+/up','application_id':self.application}


def normalized_uplink(payload,application,topic=None,username=None):
    root=object_value(payload)
    if root.get('simulated') is True:raise NetworkError('simulated_source_not_live')
    ids=object_value(root.get('end_device_ids'))
    app=object_value(ids.get('application_ids')).get('application_id')
    device=tts_id(ids.get('device_id'))
    if app!=application:raise NetworkError('source_scope_mismatch')
    if topic is not None and topic!='v3/'+str(username)+'/devices/'+device+'/up':
        raise NetworkError('source_scope_mismatch')
    uplink=object_value(root.get('uplink_message'))
    normalized=bounded_rows(uplink.get('normalized_payload',[]),20)
    if not normalized:raise NetworkError('standardized_payload_required')
    if len(normalized)!=1:raise NetworkError('multi_sample_profile_required')
    counter=uplink.get('f_cnt',0)  # Protocol Buffers omit a genuine zero counter.
    if type(counter) is not int or not 0<=counter<2**32:raise NetworkError('invalid_frame_counter')
    received=stamp(root.get('received_at') or uplink.get('received_at'))
    session=uplink.get('session_key_id')
    if session is not None and (not isinstance(session,str) or len(session)>128):raise NetworkError('invalid_session')
    sample=normalized[0]
    at=stamp(sample.get('time') or received)
    records=[];streams=[]
    warning=bool(uplink.get('normalized_payload_warnings') or uplink.get('decoded_payload_warnings'))
    if uplink.get('normalized_payload_errors') or uplink.get('decoded_payload_errors'):
        raise NetworkError('payload_decoder_failed')
    for (group,field),(metric,unit) in FIELDS.items():
        values=sample.get(group,{})
        if not isinstance(values,dict):raise NetworkError('malformed_response')
        if field not in values:continue
        value=values[field]
        valid=type(value) in (int,float) and math.isfinite(value)
        channel='normalized.'+group+'.'+field
        records.append({'event_id':fingerprint(['tts',device,session or received,counter,channel]),
            'source_device_id':'tts:'+device,'source_channel':channel,'source_metric':channel,
            'unit':unit,'value':value if valid else None,'quality':'invalid' if not valid else 'suspect' if warning else 'valid',
            'observed_at':at,'timestamp_basis':'provider_normalized_sample' if sample.get('time') else 'provider_receipt'})
        streams.append({'source_channel':channel,'source_metric':channel,'source_unit_id':unit,
            'source_unit_label':unit,'unit':unit,'probe':0,'label':metric.replace('_',' '),
            'suggested_metric':metric,'sample_value':value if valid else None,'sample_at':at})
    if not records:raise NetworkError('supported_measurement_missing')
    return {'device_id':device,'readings':records,'streams':streams,
            'timestamp_basis':'normalized_sample' if sample.get('time') else 'provider_receipt'}
