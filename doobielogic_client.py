import os
import requests


DOOBIE_BASE_URL = os.environ.get("DOOBIELOGIC_URL", "").rstrip("/")
DOOBIE_API_KEY = os.environ.get("DOOBIELOGIC_API_KEY", "")


def _headers():
    headers = {"Content-Type": "application/json"}
    if DOOBIE_API_KEY:
        headers["x-api-key"] = DOOBIE_API_KEY
    return headers


def buyer_intelligence(question: str, state: str, inventory_payload: dict):
    if not DOOBIE_BASE_URL:
        return None, "DoobieLogic URL not configured"

    try:
        resp = requests.post(
            f"{DOOBIE_BASE_URL}/buyer/intelligence",
            json={
                "question": question,
                "state": state,
                "inventory": inventory_payload,
                "focus": "buyer",
            },
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"
        return resp.json(), None
    except Exception as e:
        return None, str(e)


def extraction_intelligence(question: str, state: str, run_payload: dict):
    if not DOOBIE_BASE_URL:
        return None, "DoobieLogic URL not configured"

    try:
        resp = requests.post(
            f"{DOOBIE_BASE_URL}/extraction/intelligence",
            json={
                "question": question,
                "state": state,
                "run_data": run_payload,
                "focus": "extraction",
            },
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"
        return resp.json(), None
    except Exception as e:
        return None, str(e)
