"""Scoped maintenance discovery on the existing opt-in disposable PostgreSQL gate."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

from tests.test_cultivation_intelligence_postgres import pg, fixture_rows
from backend.app.services.cultivation_maintenance_runtime import _discover
from modules.cultivation.local_maintenance import MaintenanceConfig
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.cultivation.ingress_models import CultivationIngressGrant
from modules.operational_moats.models import ServiceAccount


def test_runtime_scoped_discovery_handles_new_expired_and_revoked_connections(pg, fixture_rows, tmp_path):
    f = fixture_rows
    config = MaintenanceConfig(enabled=True, organization_id=f['org'], facility_id=f['facility'],
                               connection_ids=('discovery',), database_path=str(tmp_path/'unused.db'))
    with Session(bind=pg, join_transaction_mode='create_savepoint') as session, session.begin():
        connections = [TelemetryConnection(organization_id=f['org'], facility_id=f['facility'],
            provider='json', label=str(uuid4()), mode=mode, status='configured', created_by=f['user'])
            for mode in ('file', 'push', 'push')]
        session.add_all(connections)
        session.flush()
        grants = []
        for index, conn in enumerate(connections[1:]):
            account = ServiceAccount(organization_id=f['org'], facility_id=f['facility'], name=str(uuid4()),
                token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                scopes_json=json.dumps(['cultivation:ingest']), active=True, created_by=f['user'])
            session.add(account)
            session.flush()
            grant = CultivationIngressGrant(organization_id=f['org'], facility_id=f['facility'],
                connection_id=conn.id, service_account_id=account.id, label='Fixture', created_by=f['user'],
                expires_at=datetime.now(timezone.utc)+timedelta(hours=1 if index == 0 else -1))
            session.add(grant)
            grants.append(grant)
        session.flush()
        ids, grant_id = [row.id for row in connections], grants[0].id
    # The disposable role has only grants introduced by the tested migrations.
    # Production's pre-existing base SELECT grants were verified separately.
    # Model only the required columns here, transactionally in the guarded test
    # database. No application migration or production privilege is expanded.
    for table, columns in (
        ('coman_facilities', 'id,organization_id,active,cultivation_enabled'),
        ('coman_organizations', 'id,active'),
        ('service_accounts', 'id,organization_id,facility_id,active,scopes_json'),
    ):
        pg.exec_driver_sql(f'GRANT SELECT ({columns}) ON {table} TO doobielogic_render_runtime')
    pg.exec_driver_sql('SET LOCAL ROLE doobielogic_render_runtime')
    assert set(_discover(pg, config)) == set(ids[:2])
    pg.execute(text('UPDATE cultivation_ingress_grants SET revoked_at=now() WHERE id=:id'), {'id': grant_id})
    assert _discover(pg, config) == (ids[0],)
    pg.exec_driver_sql('RESET ROLE')
    assert not (tmp_path/'unused.db').exists()
