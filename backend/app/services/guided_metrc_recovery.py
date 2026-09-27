"""Observe the import guard without acquiring a long-lived pooled session."""
import hashlib
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def import_active_elsewhere(engine, organization_id, facility_id):
    if engine.dialect.name != 'postgresql':
        return False
    key='wizard-metrc|'+organization_id+'|'+facility_id
    identity=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big',signed=True)
    observer=create_engine(engine.url,poolclass=NullPool,hide_parameters=True,
        connect_args={'connect_timeout':3,'options':'-c statement_timeout=3000'})
    try:
        with observer.connect() as connection:
            acquired=connection.scalar(text('SELECT pg_try_advisory_xact_lock(:id)'),{'id':identity})
            connection.rollback()
            return acquired is not True
    finally:
        observer.dispose()
