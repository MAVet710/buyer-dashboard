"""Read-only customer network setup through real migrated API and EdgeStore."""
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from dataclasses import replace
from queue import Queue
import json,time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.test_guided_metrc_setup import setup as facility_setup,schema_file
from backend.app.routers import cultivation_networks as routes
from modules.cultivation.network.config import NetworkHostConfig
from modules.cultivation.network.service import NetworkService
from modules.cultivation.network.runtime import NetworkRuntime
from modules.cultivation.network.things_stack import normalized_uplink
from modules.cultivation.network.contracts import NetworkError,tts_addresses
from modules.cultivation.edge_store import EdgeStore,Scope
from modules.cultivation.models import CultivationRoom
from modules.cultivation.intelligence_models import CultivationDevice,TelemetryConnection
from modules.integrations.models import IntegrationConfiguration
from modules.cultivation.metrics import normalize_metric_value

BASE='/api/v1/cultivation-networks'

class FakeHttp:
    def __init__(self):
        self.calls=[];self.value=77;self.at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    def get(self,host,path,headers,params=None):
        self.calls.append((host,path,params))
        if path.endswith('/metrics'):
            return {'metrics':[{'id':'temperature','name':'Temperature','units':[{'id':'degf','name':'Fahrenheit'}]}]}
        if path.endswith('/sensors'):return {'sensors':[{'id':'sensor-1','name':'Flower Room sensor'}]}
        if path.endswith('/measurements/last'):
            return {'readings':[{'sensor':'sensor-1','metric':'temperature','unit':'degf','probe':0,'time':self.at,'value':self.value}]}
        if path.endswith('/devices'):
            return {'end_devices':[{'ids':{'device_id':'sensor-1','application_ids':{'application_id':'grow-app'}},'name':'Grow sensor'}]}
        raise AssertionError('Unexpected provider read')

class FakeCapture:
    def __init__(self,*args):
        self.queue=Queue();self.ready=True;self.failed=False;self.error=None;self.dropped=0;self.running=False
    def start(self):self.running=True;return self
    def stop(self):self.running=False
    def alive(self):return self.running

@pytest.fixture
def net(facility_setup,tmp_path):
    h=facility_setup
    with Session(h.engine) as s,s.begin():
        s.add(CultivationRoom(id='room',organization_id='org',facility_id='facility',room_code='ROOM',display_name='Flower room'))
    edge=EdgeStore(tmp_path/'edge.sqlite3')
    http=FakeHttp();config=NetworkHostConfig((('org','facility'),))
    runtime=NetworkRuntime(h.engine,config,h.settings.integration_encryption_key,edge=edge,http=http,capture_factory=FakeCapture)
    app=FastAPI();app.include_router(routes.router,prefix='/api/v1')
    app.dependency_overrides[routes.service]=lambda:NetworkService(h.engine,h.state['context'],h.settings.integration_encryption_key,runtime)
    with TestClient(app) as client:
        yield SimpleNamespace(**vars(h),net_client=client,edge=edge,http=http,runtime=runtime)
    runtime.stop()

def post(h,path,body,status=200):
    result=h.net_client.post(BASE+path,json=body)
    assert result.status_code==status,result.text
    return result.json()

def create(h,adapter='aranet_cloud'):
    import secrets
    return post(h,'/connections',{'adapter':adapter,'label':'Test '+adapter,'api_key':secrets.token_hex(16),
        'options':{} if adapter=='aranet_cloud' else {'deployment':'ttn','region':'nam1','application_id':'grow-app'}},201)

def discover(h,connection):
    result=post(h,'/'+connection['id']+'/discover',{},202)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        preview=h.net_client.get(BASE+'/'+connection['id']+'/previews/'+result['id'])
        assert preview.status_code==200,preview.text
        if preview.json()['state']!='connecting':return preview.json()
        time.sleep(.02)
    pytest.fail('Discovery did not complete')


def approve(h,connection,preview):
    device=preview['devices'][0];stream=device['streams'][0]
    return post(h,'/'+connection['id']+'/approve',{'preview_id':preview['id'],'confirmed':True,
        'devices':[{'source_id':device['id'],'room_id':'room','streams':[{'source_channel':stream['source_channel'],'metric':'temperature'}]}]})


def test_aranet_discover_confirm_receive_deduplicate_and_stop(net):
    h=net;connection=create(h)
    assert h.http.calls==[]
    preview=discover(h,connection)
    assert preview['state']=='complete' and preview['devices'][0]['streams'][0]['unit']=='F'
    with Session(h.engine) as s:assert s.scalar(select(func.count()).select_from(CultivationDevice))==0
    linked=approve(h,connection,preview)
    scope=Scope('org','facility',connection['id'])
    assert h.edge.evidence(scope)['items']==[]
    control=h.runtime.control(connection['id'])
    h.runtime._poll(control)
    assert not h.runtime.backlog  # Preview sample predates approval; never silently imported.
    h.http.at=datetime.now(timezone.utc).isoformat()
    h.runtime._poll(control);h.runtime._persist(h.runtime.control(connection['id']))
    latest=h.edge.latest('org','facility','room')['readings'][0]
    assert latest['value']==25 and latest['original_value']==77 and latest['original_unit']=='F'
    assert h.runtime.health(connection['id'])['status']=='receiving'
    h.runtime._poll(control);h.runtime._persist(h.runtime.control(connection['id']))
    assert len(h.edge.evidence(scope)['items'])==1
    post(h,'/'+connection['id']+'/active',{'version':linked['version'],'enabled':False})
    h.runtime.tick()
    assert h.net_client.get(BASE).json()['connections'][0]['status']=='disabled'
    assert len(h.edge.evidence(scope)['items'])==1


def test_network_authorization_and_preview_owner_are_enforced(net):
    h=net;connection=create(h);preview=discover(h,connection)
    h.state['context']=replace(h.context,role='read_only')
    assert h.net_client.post(BASE+'/connections',content='invalid secret body').status_code==403
    assert h.net_client.post(BASE+'/'+connection['id']+'/discover',json={}).status_code==403
    h.state['context']=replace(h.context,organization_id='other',facility_id='foreign')
    assert h.net_client.get(BASE+'/'+connection['id']+'/previews/'+preview['id']).status_code in (403,409)


def test_aranet_changed_unit_metadata_or_invalid_value_never_silently_changes_data(net):
    h=net;connection=create(h);preview=discover(h,connection);approve(h,connection,preview)
    control=h.runtime.control(connection['id'])
    h.http.at=datetime.now(timezone.utc).isoformat();h.http.value='invalid'
    h.runtime._poll(control);h.runtime._persist(h.runtime.control(connection['id']))
    latest=h.edge.latest('org','facility','room')['readings'][0]
    assert latest['value'] is None and latest['state']=='quarantined'
    assert h.runtime.health(connection['id'])['status']=='needs_review'


def sample_uplink(at=None):
    return {'end_device_ids':{'device_id':'sensor-1','application_ids':{'application_id':'grow-app'}},
        'received_at':at or datetime.now(timezone.utc).isoformat(),
        'uplink_message':{'session_key_id':'opaque-session-id','f_cnt':1,
        'normalized_payload':[{'air':{'temperature':25,'relativeHumidity':55},'soil':{'ec':3.2,'moisture':60}}]}}


def test_things_stack_standardized_units_and_replay_identity():
    value=sample_uplink()
    parsed=normalized_uplink(value,'grow-app','v3/grow-app@ttn/devices/sensor-1/up','grow-app@ttn')
    assert len(parsed['readings'])==3
    assert all('moisture' not in row['source_metric'] for row in parsed['readings'])
    ec=parsed['readings'][2]
    assert normalize_metric_value('substrate_ec',ec['value'],ec['unit'])==('substrate_ec',3.2,'mS/cm')
    old=parsed['readings'][0]['event_id']
    value['uplink_message']['normalized_payload'][0]['air']['temperature']=26
    assert normalized_uplink(value,'grow-app')['readings'][0]['event_id']==old
    with pytest.raises(NetworkError,match='scope'):
        normalized_uplink(value,'wrong-app')


def test_things_stack_connects_only_after_real_standardized_preview(net,monkeypatch):
    h=net
    monkeypatch.setattr(NetworkHostConfig,'verify_mqtt',lambda self:None)
    connection=create(h,'things_stack');preview=discover(h,connection)
    assert preview['state']=='listening' and preview['devices'][0]['streams']==[]
    h.runtime.tick()
    capture=h.runtime.captures[connection['id']][0]
    capture.queue.put({'topic':'v3/grow-app@ttn/devices/sensor-1/up','payload':sample_uplink()})
    h.runtime.tick()
    preview=h.net_client.get(BASE+'/'+connection['id']+'/previews/'+preview['id']).json()
    linked=approve(h,connection,preview)
    scope=Scope('org','facility',connection['id'])
    assert h.edge.evidence(scope)['items']==[]
    h.runtime.tick()
    payload=sample_uplink();payload['uplink_message']['f_cnt']=2
    h.runtime.captures[connection['id']][0].queue.put({'topic':'v3/grow-app@ttn/devices/sensor-1/up','payload':payload})
    h.runtime.tick();h.runtime.tick()
    evidence=h.edge.evidence(scope)['items']
    assert len(evidence)==1  # Humidity and EC were not approved in this connection.
    assert h.edge.latest('org','facility','room')['readings'][0]['value']==25
    post(h,'/'+connection['id']+'/active',{'version':linked['version'],'enabled':False})
    assert not h.runtime.captures


@pytest.mark.parametrize('options',[
    {'deployment':'ttn','region':'localhost'},
    {'deployment':'tti','region':'nam1','tenant':'example.com/redirect'},
    {'deployment':'tti','region':'nam1','tenant':'localhost:443'},
])
def test_network_endpoints_are_not_arbitrary_server_requests(options):
    with pytest.raises(NetworkError):tts_addresses(options)


def test_replacing_a_network_key_pauses_and_requires_fresh_discovery(net):
    h=net;connection=create(h);preview=discover(h,connection);linked=approve(h,connection,preview)
    old=h.runtime.control(connection['id'])['ciphertext']
    replacement='1'*32
    result=post(h,'/'+connection['id']+'/credential',{'version':linked['version'],'api_key':replacement})
    assert result['enabled'] is False and result['requires_rediscovery']
    current=h.runtime.control(connection['id'])
    assert current['ciphertext']!=old and replacement not in current['ciphertext']
    denied=h.net_client.post(BASE+'/'+connection['id']+'/active',json={'version':result['version'],'enabled':True})
    assert denied.status_code==409
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(CultivationDevice))==1
    new_preview=discover(h,connection)
    relinked=approve(h,connection,new_preview)
    assert relinked['enabled']
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(CultivationDevice))==1


def test_timestamp_basis_is_preserved_without_changing_old_reading_fingerprints(net):
    h=net
    reading={'event_id':'old-event','source_device_id':'old-device','source_channel':'temperature',
        'source_metric':'temperature','value':25,'unit':'C','quality':'valid',
        'observed_at':datetime.now(timezone.utc).isoformat(),'received_at':datetime.now(timezone.utc).isoformat()}
    old,_,_=h.edge._raw(reading)
    assert 'timestamp_basis' not in old
    assert old==reading
    for basis in ('provider_observation','provider_normalized_sample','provider_receipt','receiver_time'):
        raw,_,reason=h.edge._raw({**reading,'timestamp_basis':basis})
        assert raw['timestamp_basis']==basis and reason==''
    raw,_,reason=h.edge._raw({**reading,'timestamp_basis':'unreviewed-clock'})
    assert reason=='unsafe_timestamp_basis'


def test_retry_after_is_never_shortened():
    from modules.cultivation.network.http import retry_delay
    assert retry_delay('3600')==3600
    assert retry_delay('bogus')==300


def test_multi_sample_or_simulated_uplink_does_not_invent_sensor_history():
    value=sample_uplink()
    value['uplink_message']['normalized_payload'].append({'air':{'temperature':26}})
    with pytest.raises(NetworkError,match='multi_sample_profile_required'):
        normalized_uplink(value,'grow-app')


def test_explicit_simulated_vendor_message_is_not_live_sensor_evidence():
    value=sample_uplink();value['simulated']=True
    with pytest.raises(NetworkError,match='simulated_source_not_live'):
        normalized_uplink(value,'grow-app')


def test_network_discovery_fits_the_actual_two_connection_api_pool(net):
    from sqlalchemy import create_engine
    h=net;connection=create(h)
    bounded=create_engine(h.engine.url,pool_size=2,max_overflow=0,pool_timeout=.1,
                         connect_args={'check_same_thread':False})
    previous=h.runtime.engine
    h.runtime.engine=bounded
    try:
        service=NetworkService(bounded,h.context,h.settings.integration_encryption_key,h.runtime)
        preview=service.discover(connection['id'])
        assert preview['state']=='connecting'
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and connection['id'] in h.runtime.busy:time.sleep(.02)
        assert service.preview(connection['id'],preview['id'])['state']=='complete'
        assert bounded.pool.checkedout()==0
    finally:
        h.runtime.engine=previous
        bounded.dispose()
