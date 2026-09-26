"""Final domain/gateway integration through real HTTP and isolated local stores."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from unittest.mock import patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.test_cultivation_intelligence_foundation import setup, configure, cycle, client, AT
from modules.cultivation.intelligence_models import CropCycleRoom, CultivationRecipeTarget
from modules.cultivation.intelligence_service import RecipeTargetInput
from modules.cultivation.telemetry import TelemetryConflict
from modules.cultivation.edge_store import Scope
from backend.app.routers.cultivation_intelligence_workspace import service as dependency

PREFIX='/api/v1/cultivation-intelligence'


def http_for(engine,s):
    http=client(engine)
    http.app.dependency_overrides[dependency]=lambda:s
    return http


def approved(s,threshold=900,stages=1):
    target={'metric':'temperature','unit':'C','minimum':20,'maximum':25,'threshold_seconds':threshold}
    body={'name':'Duration standard','stages':[{'stage_key':f's{i}','display_name':f'Stage {i}','sequence':i,'targets':[target]} for i in range(stages)]}
    r=s.create_recipe(body)
    class ApprovalClock(datetime):
        @classmethod
        def now(cls,tz=None):return AT-timedelta(days=1)
    with patch('modules.cultivation.intelligence_service.datetime',ApprovalClock):
        return s.approve_recipe(r['id'],{'version':r['version']})


def series(s,payload,connection,at,values):
    raw=json.loads(payload['content'])[0]
    p={**payload,'content':json.dumps([{**raw,'event_id':str(i),'observed_at':(at+timedelta(seconds=seconds)).isoformat(),'value':value} for i,(seconds,value) in enumerate(values)])}
    preview=s.preview(connection['id'],p)
    return s.import_content(connection['id'],{**p,'digest':preview['digest']})


@pytest.mark.parametrize('threshold',[0,-1,2678401,True,1.5])
def test_threshold_validation(threshold):
    with pytest.raises(ValueError):RecipeTargetInput(metric='temperature',unit='C',maximum=25,threshold_seconds=threshold)


def test_threshold_http_versions_database_bounds_and_immutable_guard(setup):
    engine,s=setup;http=http_for(engine,s)
    body={'name':'HTTP duration','stages':[{'stage_key':'custom','display_name':'Custom','sequence':0,'targets':[{'metric':'temperature','unit':'C','maximum':25,'threshold_seconds':900}]}]}
    response=http.post(PREFIX+'/recipes',json=body)
    assert response.status_code==200,response.text
    recipe=response.json()
    assert recipe['stages'][0]['targets'][0]['threshold_seconds']==900
    assert http.post(PREFIX+f"/recipes/{recipe['id']}/approve",json={'version':1}).status_code==200
    body['stages'][0]['targets'][0]['threshold_seconds']=30
    new=http.post(PREFIX+'/recipes',json=body).json()
    assert new['version']==2 and new['id']!=recipe['id']
    recipes=http.get(PREFIX+'/recipes').json()['recipes']
    assert next(r for r in recipes if r['id']==recipe['id'])['stages'][0]['targets'][0]['threshold_seconds']==900
    migration=importlib.import_module('migrations.versions.0086_cultivation_intelligence')
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):migration._recipe_guards()
    with pytest.raises(IntegrityError,match='approved_recipe_immutable'),engine.begin() as connection:
        connection.execute(text('UPDATE cultivation_recipe_targets SET threshold_seconds=1 WHERE stage_id=:stage'),{'stage':recipe['stages'][0]['id']})
    with pytest.raises(IntegrityError,match='ck_ci_target_threshold'),engine.begin() as connection:
        connection.execute(text('UPDATE cultivation_recipe_targets SET threshold_seconds=0 WHERE stage_id=:stage'),{'stage':new['stages'][0]['id']})
    # A draft child must not be moved into an approved version either.
    with pytest.raises(IntegrityError,match='approved_recipe_immutable'),engine.begin() as connection:
        connection.execute(text('UPDATE cultivation_recipe_targets SET stage_id=:approved, metric=:metric WHERE stage_id=:draft'),{'approved':recipe['stages'][0]['id'],'draft':new['stages'][0]['id'],'metric':'humidity'})


@pytest.mark.parametrize('threshold,values,above,alerts',[
    (900,[(0,86),(30,77)],30,0),
    (900,[(0,86),(300,86),(600,77),(900,86),(1200,86),(1500,77)],1200,0),
    (900,[(0,86),(300,86),(600,86),(900,77)],900,1),
    (None,[(0,86),(30,77)],30,0),
])
def test_actual_gateway_continuous_not_cumulative_thresholds(setup,threshold,values,above,alerts):
    engine,s=setup;connection,device,payload=configure(s);r=approved(s,threshold)
    at=AT
    c=cycle(s,recipe_id=r['id'])
    s.occupancy(c['id'],{'version':1,'room_id':'r1','stage_id':r['stages'][0]['id'],'entered_at':at})
    assert series(s,payload,connection,at,values)['accepted']==len(values)
    s.rollup(connection['id'],{'start':at,'end':at+timedelta(hours=1)})
    room=s.room('r1',at,at+timedelta(hours=1));stream=room['edge_summary']['streams'][0]
    assert stream['above_seconds']==above
    assert len(stream['deviations'])==alerts
    assert stream['unknown_seconds']>0
    assert stream['alert_threshold_status']==('configured' if threshold else 'not_configured')
    assert stream['threshold_semantics']=='continuous_same_direction'
    assert s.cycle(c['id'],at,at+timedelta(hours=1))['approved_recipe']['stages'][0]['targets'][0]['threshold_seconds']==threshold


def test_threshold_stage_boundaries_and_room_target_payload(setup):
    engine,s=setup;connection,device,payload=configure(s);r=approved(s,900,2)
    at=AT
    c=cycle(s,recipe_id=r['id'])
    s.occupancy(c['id'],{'version':1,'room_id':'r1','stage_id':r['stages'][0]['id'],'entered_at':at,'exited_at':at+timedelta(seconds=450)})
    s.occupancy(c['id'],{'version':2,'room_id':'r1','stage_id':r['stages'][1]['id'],'entered_at':at+timedelta(seconds=450)})
    series(s,payload,connection,at,[(0,86),(300,86),(450,86),(750,86),(1050,77)])
    s.rollup(connection['id'],{'start':at,'end':at+timedelta(hours=1)})
    streams=s.room('r1',at,at+timedelta(hours=1))['edge_summary']['streams']
    assert len(streams)==2 and sum(v['above_seconds'] for v in streams)==1050
    assert all(not v['deviations'] for v in streams)
    current=cycle(s,'current',recipe_id=r['id'])
    s.occupancy(current['id'],{'version':1,'room_id':'r1','stage_id':r['stages'][0]['id'],'entered_at':datetime.now(timezone.utc)-timedelta(minutes=1)})
    assert s.room('r1')['approved_targets'][0]['threshold_seconds']==900


def test_preview_binds_temporal_attribution_and_retries_preserve_first_snapshot(setup):
    engine,s=setup;connection,device,payload=configure(s);scope=Scope('o1','f1',connection['id'])
    first=s.preview(connection['id'],payload)
    assert s.import_content(connection['id'],{**payload,'digest':first['digest']})['accepted']==1
    snapshot=s.edge().evidence(scope)['items'][0]['snapshot']
    version=s.health(connection['id'])['connection']['version']
    c=cycle(s);s.occupancy(c['id'],{'version':1,'room_id':'r1','entered_at':AT})
    assert s.health(connection['id'])['connection']['version']==version
    with pytest.raises(TelemetryConflict,match='preview again'):s.import_content(connection['id'],{**payload,'digest':first['digest']})
    second=s.preview(connection['id'],payload)
    assert second['context_fingerprint']!=first['context_fingerprint']
    assert s.import_content(connection['id'],{**payload,'digest':second['digest']})['duplicates']==1
    assert s.edge().evidence(scope)['items'][0]['snapshot']==snapshot
    # A context mutation outside these observation times is equivalent.
    other=cycle(s,'future')
    s.occupancy(other['id'],{'version':1,'room_id':'r1','entered_at':AT+timedelta(days=2)})
    assert s.preview(connection['id'],payload)['digest']==second['digest']


def test_close_occupancy_invalidates_preview_before_edge_write_http(setup,monkeypatch):
    engine,s=setup;connection,device,payload=configure(s);http=http_for(engine,s)
    at=datetime.now(timezone.utc)+timedelta(hours=2)
    raw=json.loads(payload['content'])[0];raw['observed_at']=at.isoformat();payload={**payload,'content':json.dumps([raw])}
    c=cycle(s);o=s.occupancy(c['id'],{'version':1,'room_id':'r1','entered_at':AT})
    preview=http.post(PREFIX+f"/connections/{connection['id']}/imports/preview",json=payload).json()
    closed=http.post(PREFIX+f"/cycles/{c['id']}/occupancy/{o['id']}/close",json={'version':2,'exited_at':(at-timedelta(hours=1)).isoformat()})
    assert closed.status_code==200,closed.text
    writes=[];monkeypatch.setattr(s.edge(),'ingest',lambda *a,**kw:writes.append(a))
    result=http.post(PREFIX+f"/connections/{connection['id']}/imports",json={**payload,'digest':preview['digest']})
    assert result.status_code==409 and not writes
    next_o=http.post(PREFIX+f"/cycles/{c['id']}/occupancy",json={'version':3,'room_id':'r1','entered_at':(at-timedelta(hours=1)).isoformat()})
    assert next_o.status_code==200,next_o.text
    intervals=s.cycle(c['id'])['occupancy']
    assert len(intervals)==2 and intervals[0]['exited_at']==intervals[1]['entered_at']


def test_pending_mapping_requires_new_preview_and_explicit_drain(setup):
    engine,s=setup;connection,device,payload=configure(s)
    raw=json.loads(payload['content'])[0];raw['source_device_id']='pending'
    payload={**payload,'content':json.dumps([raw])}
    preview=s.preview(connection['id'],payload)
    assert preview['unknown_channels']==[0]
    assert s.import_content(connection['id'],{**payload,'digest':preview['digest']})['queued_for_mapping']==1
    d=s.create_device(connection['id'],{'version':s.health(connection['id'])['connection']['version'],'source_device_id':'pending'})
    s.map_device(d['id'],{'version':1,'room_id':'r1','effective_at':AT})
    s.create_sensor(d['id'],{'version':2,'source_channel':'air','source_metric':'temp','source_unit':'F','metric':'temperature'})
    with pytest.raises(TelemetryConflict):s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    assert s.preview(connection['id'],payload)['context_fingerprint']!=preview['context_fingerprint']
    assert s.drain(connection['id'],{'limit':10})['processed']==1


def test_http_existing_zone_sensor_mapping_shapes_and_workspace_counts(setup):
    engine,s=setup;connection,device,payload=configure(s);http=http_for(engine,s)
    zone=http.post(PREFIX+'/rooms/r1/zones',json={'zone_code':'A','display_name':'Bench A'})
    assert zone.status_code==200,zone.text
    assert http.get(PREFIX+'/rooms/r1/zones').json()['zones'][0]['id']==zone.json()['id']
    assert http.get(PREFIX+f"/devices/{device['id']}/mapping").json()['mappings'][0]['room_id']=='r1'
    assert http.get(PREFIX+f"/devices/{device['id']}/sensors").json()['sensors'][0]['source_unit']=='F'
    r=approved(s);c=cycle(s,recipe_id=r['id'])
    s.occupancy(c['id'],{'version':1,'room_id':'r1','stage_id':r['stages'][0]['id'],'entered_at':AT})
    card=http.get(PREFIX+'/workspace').json()['rooms'][0]
    assert card['plant_count']==1 and card['current_cycle_ids']==[c['id']]
    assert card['current_stage']['stage_key']=='s0' and not card['context_truncated']
    other=cycle(s,'ambiguous');s.occupancy(other['id'],{'version':1,'room_id':'r1','entered_at':AT})
    assert s.workspace()['rooms'][0]['current_stage'] is None


def test_plant_memberships_are_real_but_not_individual_exposure(setup):
    engine,s=setup;c=cycle(s)
    s.members(c['id'],{'version':1,'plant_ids':['p1'],'action':'add','effective_at':AT})
    s.occupancy(c['id'],{'version':2,'room_id':'r1','entered_at':AT})
    result=http_for(engine,s).get(PREFIX+'/plants/p1/exposure').json()
    assert result['memberships'][0]['cycle_id']==c['id']
    assert result['cohort_occupancy'][0]['room_id']=='r1'
    assert result['cohort_occupancy'][0]['evidence_basis']=='cycle_occupancy_not_individual_movement'
    assert result['exposure_status']=='unknown' and result['intervals']==[]


def test_historical_http_rollup_raw_read_and_retention_protection(setup,monkeypatch):
    engine,s=setup;connection,device,payload=configure(s);http=http_for(engine,s)
    preview=http.post(PREFIX+f"/connections/{connection['id']}/imports/preview",json=payload).json()
    assert http.post(PREFIX+f"/connections/{connection['id']}/imports",json={**payload,'digest':preview['digest']}).json()['accepted']==1
    root=PREFIX+f"/connections/{connection['id']}"
    body={'start':AT.isoformat(),'end':(AT+timedelta(hours=1)).isoformat()}
    result=http.post(root+'/rollup',json=body)
    assert result.status_code==200,result.text
    assert result.json()['rebuilt']==1 and not result.json()['receiver_acknowledged']
    summary=http.get(PREFIX+'/rooms/r1',params=body).json()['edge_summary']
    assert summary['streams'][0]['sample_count']==1
    assert summary['streams'][0]['attribution_intervals']
    assert http.get(root+'/evidence').json()['items'][0]['raw']['value']==77
    status=http.get(root+'/maintenance').json()
    assert status['retention_blocker']=='durable_aggregate_receiver_not_configured'
    cutoff=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert http.post(root+'/retention',json={'before':cutoff}).json()['eligible'] is None
    # Supply receipt clock deterministically, without sleeping or changing source data.
    with s.edge()._db(write=True) as db:db.execute('UPDATE evidence SET received=?',(AT.timestamp(),))
    retained=http.post(root+'/retention',json={'before':cutoff,'execute':True}).json()
    assert retained['purged']==0 and retained['protected']==1
    assert s.edge().pending_aggregates(Scope('o1','f1',connection['id']))['items']
    assert http.get(root+'/evidence').json()['items'][0]['raw'] is not None
    freshness=http.get(root+'/health').json()['freshness']
    assert not freshness['live_connected'] and freshness['last_valid_observed_at'].startswith('2026-01-02')
    assert freshness['sensor_freshness_status']=='unknown'
    assert http.post(root+'/rollup',json={**body,'start':(AT+timedelta(seconds=1)).isoformat()}).status_code==422
    assert http.get(PREFIX+'/rooms/r1',params={'start':AT.isoformat()}).status_code==422
    assert client(engine,'operator').post(root+'/rollup',json=body).status_code==403
    assert client(engine,'operator').get(root+'/evidence').status_code==403
    assert client(engine,org='o2',facility='f2',user='b').get(root+'/maintenance').status_code==404


def test_context_resolution_queries_do_not_scale_with_rows(setup):
    engine,s=setup;connection,device,payload=configure(s)
    raw=json.loads(payload['content'])[0]
    queries=[]
    def count(*args):queries.append(args[2])
    event.listen(engine,'before_cursor_execute',count)
    try:
        s.preview(connection['id'],payload);single=len(queries);queries.clear()
        s.preview(connection['id'],{**payload,'content':json.dumps([{**raw,'event_id':str(i)} for i in range(100)])})
        assert len(queries)==single
    finally:event.remove(engine,'before_cursor_execute',count)


def test_proven_parent_group_harvest_references_and_scope(setup):
    from modules.cultivation.batch_models import CultivationPlantGroup, CultivationPlantGroupMember, CultivationPlantParentLink
    from modules.cultivation.models import CultivationPlant, CultivationHarvestPlant
    from modules.cultivation.intelligence_models import CultivationHarvest
    engine,s=setup;scope={'organization_id':'o1','facility_id':'f1'}
    with Session(engine) as db,db.begin():
        db.add(CultivationPlant(id='mother',**scope,plant_tag='M',strain_name='S',phase='vegetative'))
        db.add(CultivationPlantGroup(id='group',**scope,group_code='G',group_type='nursery',strain_name='S',created_by='a'))
        db.add(CultivationHarvest(id='harvest',**scope,harvest_code='H',strain='S',created_by='a'));db.flush()
        db.add(CultivationPlantParentLink(id='parent',**scope,child_plant_id='p1',parent_plant_id='mother',relationship='mother',linked_by='a'))
        db.add(CultivationPlantGroupMember(id='group-member',**scope,group_id='group',plant_id='p1',added_by='a'))
        db.add(CultivationHarvestPlant(id='harvest-member',**scope,harvest_id='harvest',plant_id='p1',assigned_by='a'))
    result=s.exposure('p1')['relationships']
    assert result['mother_plant_id']=='mother' and result['group_ids']==['group'] and result['harvest_ids']==['harvest']
    # Legacy FK relationships alone do not establish a same-facility parent.
    with Session(engine) as db,db.begin():db.get(CultivationPlantParentLink,'parent').parent_plant_id='p2'
    assert s.exposure('p1')['relationships']['mother_plant_id'] is None


def test_quarantine_disposition_and_no_false_sensor_freshness(setup):
    engine,s=setup;connection,device,payload=configure(s)
    raw=json.loads(payload['content'])[0];raw['observed_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    payload={**payload,'content':json.dumps([raw])}
    preview=s.preview(connection['id'],payload)
    result=s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    assert result['accepted']==0 and result['quarantined']==1
    assert result['dispositions'][0]['status']=='quarantined'
    assert result['dispositions'][0]['reason']=='future_observation'
    health=s.health(connection['id'])
    assert health['freshness']['last_received_at'] and health['freshness']['last_valid_observed_at'] is None
    assert not health['freshness']['live_connected']


def test_configured_maintenance_window_and_recipe_approval_boundary(setup):
    engine,s=setup;connection,device,payload=configure(s);r=approved(s)
    # The controlled approval clock is AT minus one day. A preceding observation
    # cannot carry its no-target context past the approval boundary.
    c=cycle(s,recipe_id=r['id'])
    before=AT-timedelta(days=1,seconds=30)
    s.occupancy(c['id'],{'version':1,'room_id':'r1','stage_id':r['stages'][0]['id'],'entered_at':before})
    raw=json.loads(payload['content'])[0];raw['observed_at']=before.isoformat()
    # The fixture device mapping begins at AT minus one day, so use a bounded
    # synthetic earlier initial mapping on a separate registered device.
    d=s.create_device(connection['id'],{'version':s.health(connection['id'])['connection']['version'],'source_device_id':'earlier'})
    s.map_device(d['id'],{'version':1,'room_id':'r1','effective_at':before})
    s.create_sensor(d['id'],{'version':2,'source_channel':'air','source_metric':'temp','source_unit':'F','metric':'temperature'})
    raw['source_device_id']='earlier'
    with Session(engine) as db:snapshot=s._resolver(db,connection['id'])(Scope('o1','f1',connection['id']),raw)
    assert datetime.fromisoformat(snapshot['effective_to'])==AT-timedelta(days=1)
    assert 'target_max' not in snapshot
    s.edge().max_window_seconds=3600
    start,end=s._window()
    assert (end-start).total_seconds()==3600
    with pytest.raises(ValueError):s.rollup(connection['id'],{'start':AT,'end':AT+timedelta(hours=2)})


def test_explicit_verified_local_archive_enables_retention_http(setup,tmp_path):
    engine,s=setup;connection,device,payload=configure(s);http=http_for(engine,s)
    root=PREFIX+f"/connections/{connection['id']}"
    assert http.post(root+'/archive',json={'limit':100}).status_code==503
    directory=tmp_path/'verified-archive';directory.mkdir();s._archive_dir=str(directory)
    preview=s.preview(connection['id'],payload)
    s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    s.rollup(connection['id'],{'start':AT,'end':AT+timedelta(hours=1)})
    response=http.post(root+'/archive',json={'limit':100})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['archived']==1 and result['acknowledged']==1 and result['stale']==0
    assert not result['cloud_publication']
    artifacts=list(directory.rglob('*.json'))
    assert len(artifacts)==1
    artifact=json.loads(artifacts[0].read_text(encoding='utf-8'))
    assert artifact['scope']=={'organization_id':'o1','facility_id':'f1','connection_id':connection['id']}
    assert 'raw' not in artifact['payload']
    with s.edge()._db(write=True) as db:db.execute('UPDATE evidence SET received=?',(AT.timestamp(),))
    retained=http.post(root+'/retention',json={'before':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),'execute':True}).json()
    assert retained['purged']==1 and retained['protected']==0 and retained['blocker'] is None
    scope=Scope('o1','f1',connection['id'])
    assert s.edge().evidence(scope)['items'][0]['raw'] is None
    assert s.import_content(connection['id'],{**payload,'digest':preview['digest']})['duplicates']==1
    assert client(engine,'operator').post(root+'/archive',json={'limit':100}).status_code==403
    assert http.post(root+'/archive',json={'limit':100,'archive_dir':'untrusted'}).status_code==422
