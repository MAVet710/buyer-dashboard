"""Real machine HTTP retries preserve every admitted identifier exactly."""
from datetime import datetime, timedelta, timezone
import pytest
from modules.cultivation.edge_store import Scope
from tests.test_cultivation_ingress import h, envelope, post, setup
from backend.app.routers import cultivation_ingress as route

FIELDS = ['event_id', 'source_device_id', 'source_channel', 'source_metric', 'batch_id']

@pytest.mark.parametrize('field', FIELDS)
def test_supported_identity_alphabet_replays_without_quarantine_identity_loss(h, field):
    scope = Scope('o1', 'f1', h.c['id'])
    for index, value in enumerate(['sensor@1', 'A_Z.9:sample-1', 'x'*120]):
        body = envelope(event_id='example-'+str(index))
        if field == 'batch_id':body[field] = value
        else:body['readings'][0][field] = value
        first = post(h, body)
        assert first.status_code == 200 and first.json()['pending'] == 1, first.text
        retry = post(h, body)
        assert retry.status_code == 200 and retry.json()['duplicates'] == 1, retry.text
        assert retry.json()['items'][0]['identity'] == first.json()['items'][0]['identity']
        if field != 'batch_id':
            raw = next(r['raw'] for r in h.s.edge().evidence(scope)['items'] if r['identity'] == first.json()['items'][0]['identity'])
            assert raw[field] == value
    assert len(h.s.edge().evidence(scope)['items']) == 3
    rotated = h.grants.issue_grant(h.c['id'], {'version':2, 'label':'Rotation', 'expires_at':datetime.now(timezone.utc)+timedelta(days=1)})
    h.headers = {'Authorization':'Bearer '+rotated['token']}
    body['batch_id'] = 'split@batch'
    assert post(h, body).json()['duplicates'] == 1
    assert len(h.s.edge().evidence(scope)['items']) == 3


@pytest.mark.parametrize('field', FIELDS)
def test_unsafe_identity_rejects_whole_batch_before_evidence_or_transport(h, monkeypatch, field):
    scope = Scope('o1', 'f1', h.c['id'])
    assert post(h).status_code == 200
    store = h.s.edge()
    before = store.evidence(scope)
    transport = store.transport_status(scope)
    monkeypatch.setattr(route, 'edge_factory', lambda:pytest.fail('Unsafe source identity reached local storage'))
    for value in ['secret-1', 'password-1', 'api_key-1', 'access_token-1', '../unsafe', 'x'*121]:
        body = envelope(event_id='new-valid')
        if field == 'batch_id':body[field] = value
        else:
            invalid = dict(body['readings'][0], event_id='invalid')
            invalid[field] = value
            body['readings'].append(invalid)
        response = post(h, body)
        assert response.status_code == 422 and response.json() == {'detail':'invalid_identity'}
        assert value not in response.text
    assert store.evidence(scope) == before
    assert store.transport_status(scope) == transport
