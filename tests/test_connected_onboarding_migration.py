"""0089 is additive and cannot discard configured production/network evidence."""
from pathlib import Path
import os,subprocess,sys
import pytest
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.orm import Session
from modules.coman.models import Organization,Facility,AppUser
from modules.integrations.models import IntegrationConfiguration

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def migrated(tmp_path):
    url='sqlite:///'+(tmp_path/'migration.sqlite3').as_posix()
    env=dict(os.environ,APP_ENV='test',DATABASE_URL=url,COMAN_DATABASE_URL=url,
        PYTHON_DOTENV_DISABLED='1',AI_ALLOW_CLOUD_FALLBACK='false')
    def run(action,target,ok=True):
        result=subprocess.run([sys.executable,'-m','alembic',action,target],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        assert (result.returncode==0)==ok,(result.stdout+result.stderr)[-3000:]
        return result
    run('upgrade','0088_cultivation_radio')
    engine=create_engine(url)
    with Session(engine) as s,s.begin():
        s.add(Organization(id='org',name='Fixture',slug='fixture'));s.flush()
        s.add(Facility(id='f',organization_id='org',name='Fixture',code='F'));s.flush()
        s.add(AppUser(id='a',organization_id='org',username='a',normalized_username='a',password_hash='unusable',role='admin'))
    yield engine,run
    engine.dispose()


def test_upgrade_and_empty_downgrade_preserve_existing_records(migrated):
    engine,run=migrated
    run('upgrade','head')
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0090_security_guard'
        assert c.scalar(text('SELECT name FROM coman_facilities WHERE id=\'f\''))=='Fixture'
    run('downgrade','0088_cultivation_radio')
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM app_users'))==1
    run('upgrade','head')


@pytest.mark.parametrize('kind',['production','network'])
def test_downgrade_refuses_operational_configuration(migrated,kind):
    engine,run=migrated;run('upgrade','head')
    with engine.begin() as c:
        if kind=='production':
            c.execute(text("INSERT INTO alpha_operating_modes (id,organization_id,facility_id,mode,updated_by,created_at,updated_at) VALUES ('mode','org','f','metrc_production','a',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        else:
            c.execute(text("INSERT INTO integration_configurations (id,organization_id,facility_id,scope_type,scope_key,provider,configuration_json,encrypted_secret,secret_hint,status,last_error,updated_by,created_at,updated_at) VALUES ('network','org','f','facility','network','cultivation_network','{}','','','configured','','a',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    result=run('downgrade','0088_cultivation_radio',ok=False)
    assert 'Preserve the additive schema' in result.stderr
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0090_security_guard'
