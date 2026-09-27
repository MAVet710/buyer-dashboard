"""Small explicit wire contracts; no vendor guessing or generic network scanner."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from ..edge_store import validate_source_identity

class NetworkError(ValueError):
    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.code, self.retry_after = code, retry_after

def object_value(value):
    if not isinstance(value,dict):raise NetworkError('malformed_response')
    return value

def bounded_rows(value,limit=1000):
    if not isinstance(value,list) or len(value)>limit:raise NetworkError('response_limit')
    return [object_value(row) for row in value]

def identity(value):
    try:return validate_source_identity(value)
    except ValueError:raise NetworkError('invalid_source_identity') from None

def stamp(value):
    if not isinstance(value,str) or len(value)>40:raise NetworkError('invalid_timestamp')
    try:at=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise NetworkError('invalid_timestamp') from None
    if at.tzinfo is None or at.utcoffset() is None:raise NetworkError('invalid_timestamp')
    if not 0<=at.timestamp()<=4102444800:raise NetworkError('invalid_timestamp')
    return at.astimezone(timezone.utc).isoformat()

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def display(value,fallback='Sensor'):
    if not isinstance(value,str):return fallback
    return ''.join(c for c in value[:160] if c.isprintable() and c not in '<>') or fallback

def tts_addresses(config):
    region=config.get('region')
    deployment=config.get('deployment')
    tenant=config.get('tenant','')
    if region not in {'eu1','nam1','au1'}:raise NetworkError('unsupported_region')
    if deployment=='ttn':
        return 'eu1.cloud.thethings.network',f'{region}.cloud.thethings.network','ttn'
    if deployment=='tti' and isinstance(tenant,str) and re.fullmatch('[a-z0-9][a-z0-9-]{1,34}[a-z0-9]',tenant):
        return f'{tenant}.eu1.cloud.thethings.industries',f'{tenant}.{region}.cloud.thethings.industries',tenant
    raise NetworkError('unsupported_network')

def tts_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9](?:[-]?[a-z0-9]){2,35}',value):
        raise NetworkError('invalid_application_identity')
    return value
