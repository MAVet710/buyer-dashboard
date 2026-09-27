"""One explicit read-only import worker per PC. Durable progress stays canonical.

No credentials are queued to disk. A restarted process exposes an interrupted run
and the operator resumes existing provider page checkpoints instead of losing work.
"""
from datetime import datetime, timezone
from threading import Lock, Thread
from uuid import uuid4
from fastapi import HTTPException

_LOCK=Lock()
_JOBS={}


def is_local_active(organization_id,facility_id):
    with _LOCK:
        return (organization_id,facility_id) in _JOBS


def start_import(service):
    service.authorize(write=True)
    key=(service.org,service.facility)
    identity=str(uuid4())
    with _LOCK:
        if _JOBS:
            raise HTTPException(409,'A facility import is already running on this host. Its progress is saved.')
        _JOBS[key]=identity
    try:
        service.require_import_context()
        from .guided_metrc_setup import single_setup
        with single_setup(service.engine,*key):
            run={'id':identity,'status':'pending','started_at':datetime.now(timezone.utc).isoformat(),
                 'environment':service.environment(),'provider_mutations':0,'error_code':None}
            service._run_note(run)
        def work():
            try:
                service.import_records(run_id=identity)
            except Exception:
                # No raw transport/SQL errors or credentials enter the receipt.
                run.update(status='interrupted',error_code='import_requires_review',
                           completed_at=datetime.now(timezone.utc).isoformat())
                try:service._run_note(run,expected_id=identity)
                except Exception:pass
            finally:
                with _LOCK:
                    if _JOBS.get(key)==identity:_JOBS.pop(key,None)
        Thread(target=work,name='guided-metrc-import',daemon=True).start()
        return {'id':identity,'status':'pending','provider_mutations':0,'progress_path':'/api/v1/integration-wizard/metrc-setup'}
    except Exception:
        with _LOCK:
            if _JOBS.get(key)==identity:_JOBS.pop(key,None)
        raise
