#!/usr/bin/env python3
"""Diagnose local DoobieLogic username login without exposing credentials.

This script is intentionally local-first. It does not reset a password, create a
user, change Supabase Auth, or print an email/key/token. It verifies the layers
that must line up for username login to work:

1. local FastAPI health and username-login route registration;
2. durable AppUser username/active state;
3. durable AppUser id <-> Supabase auth.users id linkage;
4. server-side normal Supabase Auth configuration;
5. presence (not values) of frontend local Supabase/API variables.

The PC-hosted production chain is Cloudflare Tunnel -> Caddy on loopback 8080 ->
FastAPI on loopback 8010. This diagnostic talks directly to FastAPI on 8010 so it
can distinguish the backend from the Caddy edge. Port 8000 is not part of the
active DoobieLogic PC-hosting contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.database import get_engine
from modules.coman.models import AppUser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_API_URL = "http://127.0.0.1:8010"


def _http_json(url: str, timeout: float = 3.0) -> tuple[int, object | None]:
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return int(getattr(response, "status", 200) or 200), json.loads(payload) if payload else None
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        return int(exc.code), payload
    except (URLError, TimeoutError, OSError):
        return 0, None


def _env_keys(path: Path) -> set[str]:
    if not path.exists() or not path.is_file():
        return set()
    found: set[str] = set()
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _value = line.split("=", 1)
            if key.strip():
                found.add(key.strip())
    except OSError:
        return set()
    return found


def _frontend_env_presence() -> dict[str, object]:
    candidates = [
        ROOT / "frontend" / ".env.local",
        ROOT / "frontend" / ".env",
        ROOT / ".env.local",
        ROOT / ".env",
    ]
    keys: set[str] = set()
    files_seen: list[str] = []
    for path in candidates:
        current = _env_keys(path)
        if current:
            keys.update(current)
            files_seen.append(str(path.relative_to(ROOT)))
    return {
        "files_seen": files_seen,
        "vite_api_url_present": "VITE_API_URL" in keys,
        "vite_supabase_url_present": "VITE_SUPABASE_URL" in keys,
        "vite_supabase_client_key_present": bool(
            {"VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY"} & keys
        ),
    }


def diagnose(username: str, api_url: str) -> dict[str, object]:
    normalized = str(username or "").strip().casefold()
    report: dict[str, object] = {
        "username_supplied": bool(normalized),
        "username_normalized": normalized,
        "password_read": False,
        "password_changed": False,
        "user_created": False,
        "pc_hosting": {
            "caddy_url": "http://127.0.0.1:8080",
            "fastapi_url": "http://127.0.0.1:8010",
            "supabase_auth_url": "http://127.0.0.1:54321",
        },
    }

    base = str(api_url or DEFAULT_LOCAL_API_URL).rstrip("/")
    health_status, health_payload = _http_json(f"{base}/health")
    report["local_api_url"] = base
    report["local_api_health_status"] = health_status
    report["local_api_healthy"] = bool(
        health_status == 200 and isinstance(health_payload, dict) and health_payload.get("status") == "ok"
    )

    openapi_status, openapi = _http_json(f"{base}/openapi.json")
    paths = openapi.get("paths") if isinstance(openapi, dict) else {}
    report["openapi_status"] = openapi_status
    report["username_login_route_registered"] = bool(
        isinstance(paths, dict) and "/api/v1/account/username-login" in paths
    )

    settings = Settings()
    report["server_database_configured"] = settings.database_is_configured
    report["server_supabase_url_configured"] = bool(settings.supabase_url.strip())
    report["server_supabase_normal_auth_key_configured"] = bool(settings.supabase_auth_api_key)
    report["frontend_env"] = _frontend_env_presence()

    if not normalized or not settings.database_is_configured:
        report["app_user_found"] = False
        report["auth_identity_found"] = False
        report["identity_id_match"] = False
        return report

    try:
        engine = get_engine()
        with Session(engine) as session:
            user = session.scalar(select(AppUser).where(AppUser.normalized_username == normalized))
            if not user:
                report["app_user_found"] = False
                report["auth_identity_found"] = False
                report["identity_id_match"] = False
                return report
            report["app_user_found"] = True
            report["app_user_active"] = bool(user.active)
            app_user_id = str(user.id)

        with engine.connect() as connection:
            auth_row = connection.execute(
                text("select id::text as id from auth.users where id::text = :id and deleted_at is null"),
                {"id": app_user_id},
            ).mappings().first()
        report["auth_identity_found"] = bool(auth_row)
        report["identity_id_match"] = bool(auth_row and str(auth_row.get("id") or "") == app_user_id)
    except Exception as exc:  # diagnostic boundary: return class only, never connection/secret text
        report["database_check_error"] = type(exc).__name__
        report.setdefault("app_user_found", False)
        report.setdefault("auth_identity_found", False)
        report.setdefault("identity_id_match", False)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose the local DoobieLogic username-login path safely.")
    parser.add_argument("--username", default="God")
    parser.add_argument("--api-url", default=DEFAULT_LOCAL_API_URL)
    args = parser.parse_args()
    report = diagnose(args.username, args.api_url)
    print(json.dumps(report, indent=2, sort_keys=True))

    healthy = bool(
        report.get("local_api_healthy")
        and report.get("username_login_route_registered")
        and report.get("app_user_found")
        and report.get("app_user_active")
        and report.get("auth_identity_found")
        and report.get("identity_id_match")
        and report.get("server_supabase_url_configured")
        and report.get("server_supabase_normal_auth_key_configured")
    )
    raise SystemExit(0 if healthy else 2)


if __name__ == "__main__":
    main()
