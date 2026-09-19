"""Manage advisory leads through authenticated API calls; never bypass API authorization.

Examples:
  python scripts/advisory_admin.py list --status NEW
  python scripts/advisory_admin.py show LEAD_UUID
  python scripts/advisory_admin.py set-status LEAD_UUID CONTACTED --version 1

Read ADVISORY_API_TOKEN from the environment, not CLI arguments/history.
ADVISORY_API_BASE defaults to https://ops.doobielogic.io.
ADVISORY_CONTEXT_ORGANIZATION_ID and ADVISORY_CONTEXT_FACILITY_ID identify an
existing valid authenticated context. API access still requires platform DEV.
"""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list'); listing.add_argument('--status'); listing.add_argument('--limit', type=int, default=25)
    show = commands.add_parser('show'); show.add_argument('reference')
    change = commands.add_parser('set-status'); change.add_argument('reference'); change.add_argument('status', choices=['NEW','CONTACTED','QUALIFIED','CONSULTATION_BOOKED','PROPOSAL_SENT','CLIENT','CLOSED_LOST']); change.add_argument('--version', required=True, type=int); change.add_argument('--note', default='')
    commands.add_parser('metrics')
    args = parser.parse_args()
    token = os.environ.get('ADVISORY_API_TOKEN', '')
    if not token:
        parser.error('Set ADVISORY_API_TOKEN to an authenticated platform DEV access token.')
    base = os.environ.get('ADVISORY_API_BASE', 'https://ops.doobielogic.io').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1','localhost'}):
        parser.error('Use HTTPS, or HTTP loopback for local testing.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error('API base must be an origin without credentials, query, or fragment.')
    route = '/api/v1/advisory/admin/'
    body = None
    if args.command == 'list':
        route += 'leads?' + urlencode({k:v for k,v in {'status':args.status, 'limit':args.limit}.items() if v is not None})
    elif args.command == 'metrics': route += 'metrics'
    else:
        from uuid import UUID
        try: reference = str(UUID(args.reference))
        except ValueError: parser.error('Reference must be a UUID.')
        route += f'leads/{reference}'
        if args.command == 'set-status': body = json.dumps({'status':args.status,'expected_version':args.version,'note':args.note}).encode()
    headers = {'Authorization':f'Bearer {token}', 'Content-Type':'application/json'}
    for env, header in [('ADVISORY_CONTEXT_ORGANIZATION_ID','X-Organization-Id'),('ADVISORY_CONTEXT_FACILITY_ID','X-Facility-Id')]:
        if os.environ.get(env): headers[header] = os.environ[env]
    request = Request(base + route, data=body, headers=headers, method='PATCH' if body else 'GET')
    try:
        with urlopen(request, timeout=20) as response: data = json.load(response)
    except HTTPError as exc:
        print(f'Advisory API rejected request (HTTP {exc.code}). Check permissions, configuration, and expected version.', file=sys.stderr); return 1
    except URLError:
        print('Advisory API could not be reached.', file=sys.stderr); return 1
    if args.command == 'list':
        print(f"{'Reference':36}  {'Status':14} {'Ver':3}  Company")
        for row in data['items']: print(f"{row['id']:36}  {row['status']:14} {row['version']:3}  {row['company']}")
        print(f"Showing {len(data['items'])} of {data['total']} leads. Use show REFERENCE for contact details.")
    else: print(json.dumps(data, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
