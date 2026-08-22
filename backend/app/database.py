from functools import lru_cache

from sqlalchemy import Engine

from modules.coman.db import create_coman_engine

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_coman_engine(settings.database_url or None)
