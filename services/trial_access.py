from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

TRIAL_SECONDS = 24 * 60 * 60


def _key(secret: str) -> bytes:
    value = str(secret or "").encode("utf-8")
    return hashlib.sha256(b"buyer-dash:trial:v1:" + value).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_trial_token(*, secret: str, organization_id: str, facility_id: str, duration_seconds: int = TRIAL_SECONDS) -> tuple[str, int]:
    now = int(time.time())
    expires = now + max(60, int(duration_seconds))
    payload = {
        "v": 1,
        "kind": "trial",
        "sub": f"trial:{hashlib.sha256(f'{organization_id}:{facility_id}:{now}'.encode()).hexdigest()[:20]}",
        "organization_id": organization_id,
        "facility_id": facility_id,
        "role": "trial",
        "iat": now,
        "exp": expires,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64(hmac.new(_key(secret), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}", expires


def verify_trial_token(token: str, *, secret: str, now: int | None = None) -> dict[str, Any] | None:
    try:
        body, signature = str(token or "").split(".", 1)
        expected = _b64(hmac.new(_key(secret), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(body).decode("utf-8"))
        current = int(time.time()) if now is None else int(now)
        if payload.get("kind") != "trial" or int(payload.get("exp") or 0) <= current:
            return None
        if not payload.get("organization_id") or not payload.get("facility_id") or not payload.get("sub"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
