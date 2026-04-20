import os


DEFAULT_DOOBIE_BASE_URL = "https://doobie-api.onrender.com"


def get_doobie_url() -> str:
    return (
        os.environ.get("DOOBIE_BASE_URL")
        or os.environ.get("DOOBIELOGIC_URL", "")
        or DEFAULT_DOOBIE_BASE_URL
    ).strip().rstrip("/")


def get_doobie_api_key() -> str:
    return (
        os.environ.get("DOOBIE_API_KEY")
        or os.environ.get("DOOBIELOGIC_API_KEY", "")
    ).strip()


def doobie_is_configured() -> bool:
    return bool(get_doobie_url() and get_doobie_api_key())


def doobie_config_summary() -> dict:
    url = get_doobie_url()
    key = get_doobie_api_key()
    return {
        "configured": bool(url and key),
        "url": url,
        "api_key": key,
        "has_api_key": bool(key),
    }
