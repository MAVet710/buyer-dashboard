from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.coman.db import create_coman_engine
from services.web_parity import run_web_parity


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Buyer Dash FastAPI projections with durable SQL read models.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL") or os.environ.get("COMAN_DATABASE_URL") or "")
    parser.add_argument("--api-url", default=os.environ.get("BUYER_DASH_API_URL") or "http://127.0.0.1:8000")
    parser.add_argument("--organization-id", default=os.environ.get("BUYER_DASH_ORGANIZATION_ID") or "")
    parser.add_argument("--facility-id", default=os.environ.get("BUYER_DASH_FACILITY_ID") or "")
    parser.add_argument("--token", default=os.environ.get("BUYER_DASH_ACCESS_TOKEN") or "")
    parser.add_argument("--user-id", default="parity-check")
    parser.add_argument("--role", default="dev")
    args = parser.parse_args()
    if not args.database_url or not args.organization_id or not args.facility_id:
        parser.error("database URL, organization ID, and facility ID are required")

    headers = {"X-Organization-Id": args.organization_id, "X-Facility-Id": args.facility_id}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    else:
        headers.update({"X-User-Id": args.user_id, "X-User-Role": args.role})
    session = requests.Session()

    def get_json(path: str):
        response = session.get(f"{args.api_url.rstrip('/')}{path}", headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    report = run_web_parity(create_coman_engine(args.database_url), args.organization_id, args.facility_id, get_json)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
