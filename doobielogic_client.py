from __future__ import annotations

from doobie_settings import doobie_config_summary
from services.doobie_client import DoobieClient


def _client() -> DoobieClient:
    cfg = doobie_config_summary()
    return DoobieClient(base_url=cfg["url"], api_key=cfg["api_key"])


def buyer_intelligence(question: str, state: str, inventory_payload: dict):
    client = _client()
    payload = {
        "question": question,
        "state": state,
        "inventory": inventory_payload.get("inventory", inventory_payload),
    }
    response = client.buyer_brief(payload, state=state)
    if response.get("mode") == "fallback":
        return response, response.get("error", "Doobie is currently unavailable.")
    return response, None


def extraction_intelligence(question: str, state: str, run_payload: dict):
    client = _client()
    payload = {
        "question": question,
        "state": state,
        "runs": run_payload.get("runs", run_payload),
    }
    response = client.extraction_brief(payload, state=state)
    if response.get("mode") == "fallback":
        return response, response.get("error", "Doobie is currently unavailable.")
    return response, None
