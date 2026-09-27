"""Official Aranet Cloud GET contract. Unit identifiers come from its metadata."""
import math
from .contracts import NetworkError,bounded_rows,object_value,identity,stamp,fingerprint,display
from .http import ReadOnlyHttp

UNITS={'c':'C','Ã‚Â°c':'C','celsius':'C','f':'F','Ã‚Â°f':'F','fahrenheit':'F','%':'%',
       'ppm':'ppm','ph':'pH','ms/cm':'mS/cm','us/cm':'uS/cm','Ã‚Âµs/cm':'uS/cm','ds/m':'dS/m',
       'Ã‚Âµmol/mÃ‚Â²/s':'umol/m2/s','umol/m2/s':'umol/m2/s','Ã‚Âµmol/m2/s':'umol/m2/s'}
METRICS={'temperature':'temperature','air temperature':'temperature','relative humidity':'relative_humidity',
         'humidity':'relative_humidity','co2':'co2','carbon dioxide':'co2','ppfd':'ppfd',
         'substrate temperature':'substrate_temperature','electrical conductivity':'substrate_ec',
         'volumetric water content':'substrate_vwc'}

class AranetCloud:
    def __init__(self,api_key,config=None,http=None):
        if not isinstance(api_key,str) or len(api_key)!=32 or not api_key.isascii() or not api_key.isprintable():
            raise NetworkError('invalid_credential')
        self._key=api_key
        self.http=http or ReadOnlyHttp()

    def _get(self,path,params=None):
        data=object_value(self.http.get('aranet.cloud','/api/v1/'+path,{'ApiKey':self._key},params))
        if data.get('error'):raise NetworkError('provider_response_error')
        return data

    def metadata(self):
        metrics={}
        for row in bounded_rows(self._get('metrics').get('metrics')):
            mid=identity(row.get('id'))
            units={identity(unit.get('id')):display(unit.get('name'),'') for unit in bounded_rows(row.get('units',[]),40)}
            if mid in metrics:raise NetworkError('duplicate_source_identity')
            metrics[mid]={'name':display(row.get('name'),mid),'units':units}
        return metrics

    def discover(self):
        metadata=self.metadata()
        sensors=bounded_rows(self._get('sensors').get('sensors'))
        # Preview only. No local device or telemetry exists until operator approval.
        readings=bounded_rows(self._get('measurements/last').get('readings'),5000)
        by_sensor={}
        for reading in readings:
            sid=identity(reading.get('sensor'))
            mid=identity(reading.get('metric'));uid=identity(reading.get('unit'))
            metric=metadata.get(mid)
            probe=reading.get('probe',0)
            if type(probe) is not int or not 0<=probe<=1000:raise NetworkError('invalid_probe')
            label=metric['units'].get(uid,'') if metric else ''
            unit=UNITS.get(label.casefold())
            channel='p'+str(probe)+'.'+mid+'.u'+fingerprint(uid)[:12]
            descriptor={'source_channel':identity(channel),'source_metric':mid,'source_unit_id':uid,
                'source_unit_label':label,'unit':unit,'probe':probe,
                'label':metric['name'] if metric else mid,
                'suggested_metric':METRICS.get(metric['name'].casefold()) if metric else None,
                'sample_value':reading.get('value') if type(reading.get('value')) in (int,float) and math.isfinite(reading['value']) else None,'sample_at':reading.get('time') if isinstance(reading.get('time'),str) else None}
            by_sensor.setdefault(sid,{})[channel]=descriptor
        result=[];seen=set()
        for row in sensors:
            sid=identity(row.get('id'))
            if sid in seen:raise NetworkError('duplicate_source_identity')
            seen.add(sid)
            streams=list(by_sensor.get(sid,{}).values())
            if len(streams)>32:raise NetworkError('sensor_stream_limit')
            result.append({'id':sid,'name':display(row.get('name'),sid),'streams':streams,
                'status':'review_units' if any(not x['unit'] for x in streams) else 'ready' if streams else 'waiting_for_sample'})
        return {'devices':result[:100],'truncated':len(result)>100,
                'adapter':'aranet_cloud','transport':'cloud_poll','history_recovery_supported':False}

    def latest(self,devices):
        ids=sorted({identity(device['source_id']) for device in devices})
        if not ids or len(ids)>100:raise NetworkError('device_limit')
        readings=bounded_rows(self._get('measurements/last',{'sensor':','.join(ids)}).get('readings'),5000)
        return self.convert(readings,devices,self.metadata())

    @staticmethod
    def convert(readings,devices,metadata):
        selected={device['source_id']:device for device in devices}
        output=[];unknown=0
        for row in readings:
            if row.get('sensor') not in selected:
                unknown+=1;continue
            sid=identity(row['sensor']);mid=identity(row.get('metric'));uid=identity(row.get('unit'))
            probe=row.get('probe',0)
            streams=selected[sid]['streams']
            matching=[s for s in streams if s['source_metric']==mid and s['probe']==probe and s['source_unit_id']==uid]
            if len(matching)!=1:
                unknown+=1;continue
            stream=matching[0]
            current=metadata.get(mid,{}).get('units',{}).get(uid)
            if current!=stream['source_unit_label']:raise NetworkError('source_units_changed')
            at=stamp(row.get('time'))
            value=row.get('value')
            valid=type(value) in (int,float) and math.isfinite(value)
            output.append({'event_id':fingerprint(['aranet',sid,mid,probe,at]),
                'source_device_id':'aranet:'+sid,'source_channel':stream['source_channel'],
                'source_metric':mid,'unit':stream['unit'],'value':value if valid else None,
                'quality':'valid' if valid else 'invalid','observed_at':at,'timestamp_basis':'provider_observation'})
        return {'readings':output,'unmapped_readings':unknown}
