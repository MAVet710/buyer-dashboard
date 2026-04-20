import os

from services.doobie_client import DoobieClient


def get_llm_client() -> DoobieClient:
    return DoobieClient(
        base_url=os.getenv("DOOBIE_BASE_URL") or os.getenv("DOOBIELOGIC_URL", ""),
        api_key=os.getenv("DOOBIE_API_KEY") or os.getenv("DOOBIELOGIC_API_KEY", ""),
    )


def get_chat_model() -> str:
    return "doobie-copilot"
