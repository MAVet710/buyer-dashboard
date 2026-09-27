"""Fixed-host GET-only transport. Credentials never follow redirects or proxies."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
import json
import re
import requests
from .contracts import NetworkError

MAX_BYTES=2097152

def retry_delay(header):
    try:
        value=int(header)
    except (TypeError,ValueError):
        try:value=int((parsedate_to_datetime(header)-datetime.now(timezone.utc)).total_seconds())
        except (TypeError,ValueError,OverflowError):return 300
    return max(1,value)  # Never retry sooner by clamping a vendor's long delay.

class ReadOnlyHttp:
    def get(self,host,path,headers,params=None):
        if not isinstance(host,str) or not (host=='aranet.cloud' or re.fullmatch(r'(eu1|nam1|au1)\.cloud\.thethings\.network',host) or re.fullmatch(r'[a-z0-9][a-z0-9-]{1,34}[a-z0-9]\.(eu1|nam1|au1)\.cloud\.thethings\.industries',host)):
            raise NetworkError('unsupported_host')
        if not path.startswith('/api/') or '?' in path or '..' in path:
            raise NetworkError('unsupported_path')
        started=monotonic()
        try:
            with requests.Session() as session:
                session.trust_env=False
                with session.get('https://'+host+path,headers=headers,params=params,
                    timeout=(5,10),allow_redirects=False,stream=True) as response:
                    if response.status_code in (401,403):raise NetworkError('authorization_failed')
                    if response.status_code==429:raise NetworkError('rate_limited',retry_delay(response.headers.get('Retry-After')))
                    if response.status_code!=200:raise NetworkError('provider_unavailable')
                    if 'json' not in response.headers.get('Content-Type','').lower():raise NetworkError('malformed_response')
                    data=bytearray()
                    for chunk in response.iter_content(16384):
                        data.extend(chunk)
                        if len(data)>MAX_BYTES or monotonic()-started>20:raise NetworkError('response_limit')
                    try:
                        return json.loads(data,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    except (ValueError,UnicodeDecodeError,RecursionError):raise NetworkError('malformed_response') from None
        except requests.RequestException:
            raise NetworkError('connection_unavailable') from None
