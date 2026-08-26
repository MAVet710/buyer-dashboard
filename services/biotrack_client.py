"""State-scoped BioTrack integration primitives.

BioTrack state APIs are not one universal contract. This client deliberately
supports an explicit login contract and never guesses production endpoints.
Credentials are supplied by the encrypted integration store and are never
returned in result payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


class BioTrackError(RuntimeError):
    pass


@dataclass(frozen=True)
class BioTrackSession:
    session_id: str
    training: bool
    base_url: str


def _base_url(value: str) -> str:
    clean = str(value or "").strip().rstrip("/") + "/"
    parsed = urlparse(clean)
    if parsed.scheme != "https" or not parsed.netloc:
        raise BioTrackError("BioTrack production/sandbox base URL must use HTTPS.")
    return clean


def login_biotrack(
    *,
    base_url: str,
    username: str,
    password: str,
    license_number: str,
    training: bool,
    timeout: int = 20,
    login_path: str = "/v1/login",
) -> BioTrackSession:
    if not all(str(value or "").strip() for value in (username, password, license_number)):
        raise BioTrackError("BioTrack username, password, and license are required.")
    url = urljoin(_base_url(base_url), login_path.lstrip("/"))
    try:
        response = requests.post(
            url,
            json={
                "username": str(username).strip(),
                "password": str(password),
                "license": str(license_number).strip(),
                "training": bool(training),
            },
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise BioTrackError(f"BioTrack login request failed: {exc}") from exc
    if response.status_code in {401, 403}:
        raise BioTrackError("BioTrack rejected the saved credentials or license access.")
    if response.status_code == 429:
        raise BioTrackError("BioTrack rate limited the connection test.")
    if not response.ok:
        raise BioTrackError(f"BioTrack login failed with HTTP {response.status_code}.")
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise BioTrackError("BioTrack returned a non-JSON login response.") from exc
    if isinstance(payload, dict):
        session_id = str(payload.get("sessionid") or payload.get("session_id") or payload.get("sessionId") or "").strip()
    else:
        session_id = ""
    if not session_id:
        raise BioTrackError("BioTrack login succeeded but did not return a session ID.")
    return BioTrackSession(session_id=session_id, training=bool(training), base_url=_base_url(base_url))


def biotrack_get(
    session: BioTrackSession,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    clean_path = str(path or "").strip()
    if not clean_path.startswith("/"):
        raise BioTrackError("BioTrack resource paths must be explicit absolute API paths.")
    try:
        response = requests.get(
            urljoin(session.base_url, clean_path.lstrip("/")),
            params=params or {},
            headers={"Accept": "application/json", "x-api-key": session.session_id},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise BioTrackError(f"BioTrack request failed: {exc}") from exc
    if response.status_code == 429:
        raise BioTrackError("BioTrack rate limited the request.")
    if response.status_code in {401, 403}:
        raise BioTrackError("BioTrack session is unauthorized for this resource.")
    if not response.ok:
        raise BioTrackError(f"BioTrack request failed with HTTP {response.status_code}.")
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise BioTrackError("BioTrack returned a non-JSON response.") from exc


def test_biotrack_connection(**kwargs: Any) -> dict[str, Any]:
    try:
        session = login_biotrack(**kwargs)
        return {
            "ok": True,
            "message": "BioTrack login validated for the configured license.",
            "training": session.training,
        }
    except BioTrackError as exc:
        return {"ok": False, "message": str(exc)}
