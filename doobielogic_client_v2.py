import os
import requests

DOOBIE_BASE_URL = os.environ.get("DOOBIELOGIC_URL", "").rstrip("/")
DOOBIE_API_KEY = os.environ.get("DOOBIELOGIC_API_KEY", "")


def _headers():
    headers = {"Content-Type": "application/json"}
    if DOOBIE_API_KEY:
        headers["x-api-key"] = DOOBIE_API_KEY
    return headers


def _post(path: str, payload: dict):
    if not DOOBIE_BASE_URL:
        return None, "DoobieLogic URL not configured"
    try:
        resp = requests.post(f"{DOOBIE_BASE_URL}{path}", json=payload, headers=_headers(), timeout=15)
        if resp.status_code == 404:
            return None, f"Endpoint not found: {path}"
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"
        return resp.json(), None
    except Exception as e:
        return None, str(e)


def department_intelligence(scope: str, question: str, state: str = "MA", payload: dict | None = None, extras: dict | None = None):
    body = {
        "question": question,
        "state": state,
        "focus": scope,
        "payload": payload or {},
    }
    if extras:
        body.update(extras)
    response, err = _post(f"/{scope}/intelligence", body)
    if response is not None or err != f"Endpoint not found: /{scope}/intelligence":
        return response, err
    fallback_body = {
        "question": question,
        "state": state,
        "focus": scope,
        "payload": payload or {},
    }
    if extras:
        fallback_body.update(extras)
    return _post("/copilot/intelligence", fallback_body)
