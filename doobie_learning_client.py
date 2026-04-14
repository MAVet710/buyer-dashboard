import os
import requests

DOOBIE_BASE_URL = os.environ.get("DOOBIELOGIC_URL", "").rstrip("/")
DOOBIE_API_KEY = os.environ.get("DOOBIELOGIC_API_KEY", "")


def _headers():
    headers = {"Content-Type": "application/json"}
    if DOOBIE_API_KEY:
        headers["x-api-key"] = DOOBIE_API_KEY
    return headers


def submit_feedback(mode: str, question: str, outcome: str, state: str = "MA", recommendation: str | None = None):
    if not DOOBIE_BASE_URL:
        return None, "DoobieLogic URL not configured"
    try:
        resp = requests.post(
            f"{DOOBIE_BASE_URL}/learning/feedback",
            json={
                "mode": mode,
                "question": question,
                "state": state,
                "outcome": outcome,
                "recommendation": recommendation,
            },
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"
        return resp.json(), None
    except Exception as e:
        return None, str(e)


def fetch_learning_summary():
    if not DOOBIE_BASE_URL:
        return None, "DoobieLogic URL not configured"
    try:
        resp = requests.get(
            f"{DOOBIE_BASE_URL}/learning/summary",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"
        return resp.json(), None
    except Exception as e:
        return None, str(e)
