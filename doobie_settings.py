import os


def get_doobie_url() -> str:
    return os.environ.get("DOOBIELOGIC_URL", "").strip().rstrip("/")


def get_doobie_api_key() -> str:
    return os.environ.get("DOOBIELOGIC_API_KEY", "").strip()


def doobie_is_configured() -> bool:
    return bool(get_doobie_url())


def doobie_config_summary() -> dict:
    url = get_doobie_url()
    key = get_doobie_api_key()
    return {
        "configured": bool(url),
        "url": url,
        "has_api_key": bool(key),
    }
