"""0087 fresh/upgrade/rollback contracts on disposable SQLite only."""
from pathlib import Path
import os
import subprocess
import sys
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

ROOT=Path(__file__).resolve().parents[1]


def test_one_head():
    assert ScriptDirectory.from_config(Config(str(ROOT/'alembic.ini'))).get_heads()==['0090_security_guard']


def test_real_chain_preserves_existing_connection_and_refuses_evidence_downgrade(tmp_path):
    url='sqlite:///'+(tmp_path/'m.db').as_posix()
    env=dict(os.environ,APP_ENV='test',DATABASE_URL=url,COMAN_DATABASE_URL=url,AI_ALLOW_CLOUD_FALLBACK='false',PYTHON_DOTENV_DISABLED='1',SANDBOX_STARTUP_SEED_ENABLED='false',PYTHONPATH=str(ROOT))
    env.pop('DOOBIELOGIC_TEST_POSTGRES_URL',None);env.pop('DOOBIELOGIC_PG_RELEASE_TEST',None)
    def run(*args,success=True):
        result=subprocess.run([sys.executable,'-m','alembic',*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        assert (result.returncode==0)==success,(result.stdout+result.stderr)[-5000:]
        return result
    run('upgrade','0086_cultivation_intelligence')
    engine=create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO coman_organizations (id,name,slug,active,created_at,updated_at) VALUES ('o','Synthetic','synthetic',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        c.execute(text("INSERT INTO coman_facilities (id,organization_id,name,code,timezone_name,license_number,license_type,retail_enabled,production_enabled,cultivation_enabled,commercial_enabled,active,created_at,updated_at) VALUES ('f','o','Synthetic','F','UTC','','',0,0,1,0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        # Use an existing synthetic actor schema through ORM for its additive defaults.
    from modules.coman.models import AppUser
    from sqlalchemy.orm import Session
    with Session(engine) as s,s.begin():s.add(AppUser(id='a',organization_id='o',username='a',normalized_username='a',password_hash='synthetic',role='admin'))
    with engine.begin() as c:
        c.execute(text("INSERT INTO cultivation_telemetry_connections (id,organization_id,facility_id,provider,label,mode,status,version,created_by,created_at,updated_at) VALUES ('c','o','f','json','Preserved','file','configured',1,'a',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    run('upgrade','0087_cultivation_push')
    with engine.begin() as c:
        assert c.scalar(text('SELECT label FROM cultivation_telemetry_connections'))=='Preserved'
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0087_cultivation_push'
        fk=inspect(c).get_foreign_keys('cultivation_ingress_grants')
        assert any(r['referred_table']=='service_accounts' and r['constrained_columns']==['organization_id','facility_id','service_account_id'] for r in fk)
    run('downgrade','0086_cultivation_intelligence')
    run('upgrade','0087_cultivation_push')
    with engine.begin() as c:c.execute(text("UPDATE cultivation_telemetry_connections SET mode='push' WHERE id='c'"))
    result=run('downgrade','0086_cultivation_intelligence',success=False)
    assert 'preserve it before rollback' in result.stderr
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0087_cultivation_push'
        assert c.scalar(text('SELECT mode FROM cultivation_telemetry_connections'))=='push'
    engine.dispose()


def test_fresh_head(tmp_path):
    url='sqlite:///'+(tmp_path/'fresh.db').as_posix()
    env=dict(os.environ,APP_ENV='test',DATABASE_URL=url,COMAN_DATABASE_URL=url,AI_ALLOW_CLOUD_FALLBACK='false',PYTHON_DOTENV_DISABLED='1',PYTHONPATH=str(ROOT))
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,(result.stdout+result.stderr)[-5000:]
    engine=create_engine(url)
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0090_security_guard'
        assert 'cultivation_ingress_grants' in inspect(c).get_table_names()
    engine.dispose()
