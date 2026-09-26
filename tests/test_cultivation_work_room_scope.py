"""One room's unfinished feed must not suppress another room's reviewed Work."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from modules.cultivation.edge_store import Scope
from modules.cultivation.gateway import TelemetryGatewayService
from modules.cultivation.intelligence_models import TelemetryConnection, CultivationDevice, CultivationSensor, DeviceMapping
from modules.cultivation.models import CultivationRoom
from tests.test_cultivation_edge_work import bridge, acquire, listing, create, counts
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


def second_feed(h, *, same_room=False):
    values={'organization_id':h.own.org,'facility_id':h.own.facility}
    with Session(h.engine) as s,s.begin():
        room_id=h.own.room
        if not same_room:
            room=CultivationRoom(**values,room_code=str(uuid4()),display_name='Other room',phase='flowering')
            s.add(room);s.flush();room_id=room.id
        connection=TelemetryConnection(**values,provider='json',label=str(uuid4()),created_by=h.own.user)
        s.add(connection);s.flush()
        device=CultivationDevice(**values,connection_id=connection.id,source_device_id='other-device')
        s.add(device);s.flush()
        s.add_all([CultivationSensor(**values,device_id=device.id,source_channel='temp',source_metric='vendor_temp',source_unit='F',metric='temperature',unit='C'),
                   DeviceMapping(**values,device_id=device.id,room_id=room_id,effective_at=h.history.start-timedelta(days=1),created_by=h.own.user)])
        s.flush();identity=connection.id
    scope=Scope(h.own.org,h.own.facility,identity)
    row=dict(event_id='other-first',source_device_id='other-device',source_channel='temp',source_metric='vendor_temp',value=77,unit='F',quality='valid',observed_at=h.history.start.isoformat())
    gateway=TelemetryGatewayService(h.engine,h.state['context'],edge=h.edge)
    with Session(h.engine) as s:
        resolver=gateway._resolver(s,identity)
        resolved=resolver(scope,row)
    assert resolved and resolved['room_id']==room_id
    assert h.edge.ingest(scope,[row],resolved=[resolved])['accepted']==1
    h.edge.rollup(scope,h.history.start,h.history.end)
    def make_dirty():
        changed=dict(row,event_id='other-late',observed_at=(h.history.start+timedelta(seconds=100)).isoformat())
        assert h.edge.ingest(scope,[changed],resolved=[resolved])['accepted']==1
    return identity,scope,make_dirty


@pytest.mark.parametrize('revoked',[False,True])
def test_unrelated_dirty_feed_does_not_block_exact_room_work(bridge,revoked):
    h=bridge;acquire(h)
    original,=listing(h)['items']
    identity,scope,make_dirty=second_feed(h)
    make_dirty()
    if revoked:
        with Session(h.engine) as s,s.begin():
            row=s.get(TelemetryConnection,identity);row.status='revoked';row.revoked_at=h.history.end
    result=listing(h)
    assert not result['truncated']
    item,=result['items']
    assert item['exception_id']==original['exception_id']
    created=create(h,item['exception_id'])
    assert created.status_code==200,created.text
    repeated=create(h,item['exception_id']).json()
    assert repeated['existing'] and repeated['work_item_id']==created.json()['work_item_id']
    assert counts(h)[0]==1
    with h.edge._db() as db:
        assert db.execute('SELECT dirty FROM buckets WHERE scope=?',(scope.key,)).fetchone()[0]==1


def test_unrelated_arrival_between_selection_and_creation_does_not_invalidate_work(bridge):
    h=bridge;acquire(h)
    _,_,make_dirty=second_feed(h)
    item,=listing(h)['items'];changed=[]
    def arrive(conn,cursor,statement,*args):
        if not changed and 'work_items' in statement.lower() and statement.lstrip().upper().startswith('SELECT'):
            changed.append(True);make_dirty()
    event.listen(h.engine,'before_cursor_execute',arrive)
    try:
        response=create(h,item['exception_id'])
        assert response.status_code==200,response.text
    finally:event.remove(h.engine,'before_cursor_execute',arrive)
    assert changed and counts(h)[0]==1


@pytest.mark.parametrize('revoked',[False,True])
def test_dirty_feed_for_the_same_room_still_blocks_review(bridge,revoked):
    h=bridge;acquire(h)
    item,=listing(h)['items']
    identity,_,make_dirty=second_feed(h,same_room=True);make_dirty()
    if revoked:
        with Session(h.engine) as s,s.begin():
            row=s.get(TelemetryConnection,identity);row.status='revoked';row.revoked_at=h.history.end
    assert listing(h)['items']==[] and listing(h)['truncated']
    assert create(h,item['exception_id']).status_code==409
    assert counts(h)[0]==0


def test_connection_scope_overflow_is_explicit_not_silently_ignored(bridge,monkeypatch):
    h=bridge;acquire(h)
    item,=listing(h)['items']
    second_feed(h,same_room=True)
    monkeypatch.setattr('modules.cultivation.edge_work.MAX_ITEMS',1)
    result=listing(h)
    assert result['truncated'] and result['items']==[]
    assert create(h,item['exception_id']).status_code==409
    assert counts(h)[0]==0
