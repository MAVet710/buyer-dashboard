from __future__ import annotations

import os
from typing import Any

import requests


STATE_HOSTS = {
    "AL": "https://api-al.metrc.com",
    "AK": "https://api-ak.metrc.com",
    "CA": "https://api-ca.metrc.com",
    "CO": "https://api-co.metrc.com",
    "DC": "https://api-dc.metrc.com",
    "GU": "https://api-gu.metrc.com",
    "IL": "https://api-il.metrc.com",
    "KY": "https://api-ky.metrc.com",
    "LA": "https://api-la.metrc.com",
    "ME": "https://api-me.metrc.com",
    "MD": "https://api-md.metrc.com",
    "MA": "https://api-ma.metrc.com",
    "MI": "https://api-mi.metrc.com",
    "MN": "https://api-mn.metrc.com",
    "MS": "https://api-ms.metrc.com",
    "MO": "https://api-mo.metrc.com",
    "MT": "https://api-mt.metrc.com",
    "NV": "https://api-nv.metrc.com",
    "NJ": "https://api-nj.metrc.com",
    "NY": "https://api-ny.metrc.com",
    "OH": "https://api-oh.metrc.com",
    "OK": "https://api-ok.metrc.com",
    "OR": "https://api-or.metrc.com",
    "RI": "https://api-ri.metrc.com",
    "SD": "https://api-sd.metrc.com",
    "VI": "https://api-vi.metrc.com",
    "VA": "https://api-va.metrc.com",
    "WV": "https://api-wv.metrc.com",
}

STATE_NAMES = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "DISTRICT OF COLUMBIA": "DC",
    "WASHINGTON DC": "DC",
    "WASHINGTON D.C.": "DC",
    "GUAM": "GU",
    "ILLINOIS": "IL",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEVADA": "NV",
    "NEW JERSEY": "NJ",
    "NEW YORK": "NY",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "RHODE ISLAND": "RI",
    "SOUTH DAKOTA": "SD",
    "US VIRGIN ISLANDS": "VI",
    "U.S. VIRGIN ISLANDS": "VI",
    "VIRGIN ISLANDS": "VI",
    "VIRGINIA": "VA",
    "WEST VIRGINIA": "WV",
}


def get_default_metrc_integrator_key() -> dict[str, str]:
    key = str(
        os.environ.get("METRC_INTEGRATOR_API_KEY")
        or os.environ.get("METRC_SOFTWARE_API_KEY")
        or ""
    ).strip()
    return {
        "api_key": key,
        "source": "env" if key else "unavailable",
    }


def resolve_metrc_base_url(state_or_url: str) -> tuple[str, str]:
    raw = str(state_or_url or "").strip()
    if raw.lower().startswith(("https://", "http://")):
        return raw.rstrip("/"), raw

    token = raw.upper().strip()
    token = STATE_NAMES.get(token, token)
    token = "".join(ch for ch in token if ch.isalnum())
    token = STATE_NAMES.get(token, token)
    if token in STATE_HOSTS:
        return STATE_HOSTS[token], token
    return "", token


def _extract_facility_license(facility: Any) -> str:
    if not isinstance(facility, dict):
        return ""
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        if facility.get(key):
            return str(facility.get(key) or "").strip()
    license_payload = facility.get("License") or facility.get("license")
    if isinstance(license_payload, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            if license_payload.get(key):
                return str(license_payload.get(key) or "").strip()
    return ""


def _facility_label(facility: Any) -> str:
    if not isinstance(facility, dict):
        return ""
    label = (
        facility.get("Name")
        or facility.get("DisplayName")
        or facility.get("Alias")
        or facility.get("name")
        or facility.get("displayName")
        or ""
    )
    license_number = _extract_facility_license(facility)
    if label and license_number:
        return f"{label} ({license_number})"
    return str(label or license_number or "").strip()


def test_metrc_connection(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str = "",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    base_url, state_code = resolve_metrc_base_url(state)
    user_api_key = str(user_api_key or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    license_number = str(license_number or "").strip()

    if not base_url:
        return {
            "ok": False,
            "status": "missing_state",
            "message": "Enter a valid Metrc state code, state name, or API base URL.",
        }
    if not integrator_api_key:
        return {
            "ok": False,
            "status": "missing_integrator_key",
            "message": "METRC_INTEGRATOR_API_KEY is missing from environment or Streamlit secrets.",
            "base_url": base_url,
            "state": state_code,
        }
    if not user_api_key:
        return {
            "ok": False,
            "status": "missing_user_key",
            "message": "Enter the Metrc user API key before testing.",
            "base_url": base_url,
            "state": state_code,
        }

    try:
        resp = requests.get(
            f"{base_url}/facilities/v2/",
            auth=(integrator_api_key, user_api_key),
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )
    except requests.Timeout:
        return {
            "ok": False,
            "status": "timeout",
            "message": "Metrc did not respond before the timeout.",
            "base_url": base_url,
            "state": state_code,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status": "request_error",
            "message": f"Metrc request failed: {type(exc).__name__}.",
            "base_url": base_url,
            "state": state_code,
        }

    result: dict[str, Any] = {
        "ok": resp.status_code == 200,
        "http_status": int(resp.status_code),
        "base_url": base_url,
        "state": state_code,
    }
    if resp.status_code == 401:
        result.update(
            status="auth_failed",
            message="Metrc rejected the integrator/user API key pair.",
        )
        return result
    if resp.status_code == 403:
        result.update(
            status="forbidden",
            message="Metrc authenticated the keys, but this user is not authorized for the facilities endpoint.",
        )
        return result
    if resp.status_code == 429:
        result.update(
            status="rate_limited",
            message="Metrc rate limited the request.",
            retry_after=resp.headers.get("Retry-After", ""),
        )
        return result
    if resp.status_code >= 400:
        result.update(
            status="http_error",
            message=f"Metrc returned HTTP {resp.status_code}.",
        )
        return result

    try:
        payload = resp.json()
    except ValueError:
        result.update(
            ok=False,
            status="invalid_json",
            message="Metrc responded successfully, but the response was not valid JSON.",
        )
        return result

    facilities = payload if isinstance(payload, list) else []
    facility_labels = [_facility_label(f) for f in facilities]
    facility_labels = [label for label in facility_labels if label]
    result.update(
        status="connected",
        message="Metrc connection succeeded.",
        facility_count=len(facilities),
        facilities_preview=facility_labels[:5],
    )
    if license_number:
        normalized_target = "".join(ch for ch in license_number.upper() if ch.isalnum())
        license_found = any(
            "".join(ch for ch in _extract_facility_license(f).upper() if ch.isalnum()) == normalized_target
            for f in facilities
        )
        result["license_found"] = license_found
        if not license_found:
            result["status"] = "connected_license_not_found"
            result["message"] = "Metrc connected, but the entered facility license was not found in this user's facilities."
    return result
