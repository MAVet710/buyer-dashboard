from __future__ import annotations

import pytest

from modules.coman.db import ComanDatabaseConfigurationError, resolve_database_url


def test_postgres_url_is_normalized_for_psycopg3():
    result = resolve_database_url("postgresql://example:secret@host.test:5432/postgres")
    assert result.startswith("postgresql+psycopg://")
    assert "secret" in result


def test_missing_database_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("COMAN_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ComanDatabaseConfigurationError):
        resolve_database_url()
