"""Database configuration for the Co-Man workspace.

Co-Man data must never silently fall back to an ephemeral database in a hosted
deployment. Callers must provide a durable PostgreSQL URL directly or through
the authenticated sealed Render handoff.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Engine, create_engine


class ComanDatabaseConfigurationError(RuntimeError):
    """Raised when durable Co-Man persistence has not been configured."""


_SEALED_DB_AAD = b"doobielogic-render-db-v1"


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _sealed_database_url() -> str:
    private_value = str(os.environ.get("DATABASE_SEAL_PRIVATE_KEY") or "").strip()
    if not private_value:
        return ""
    sealed_path = Path(
        str(os.environ.get("SEALED_DATABASE_URL_PATH") or "deploy/sealed/render_database_url.json").strip()
    )
    if not sealed_path.is_file():
        return ""
    try:
        payload = json.loads(sealed_path.read_text(encoding="utf-8"))
        if int(payload.get("version") or 0) != 1:
            raise ValueError("unsupported sealed credential version")
        private_key = X25519PrivateKey.from_private_bytes(_decode(private_value))
        ephemeral_key = X25519PublicKey.from_public_bytes(_decode(str(payload["ephemeral_public_key"])))
        shared = private_key.exchange(ephemeral_key)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=_SEALED_DB_AAD,
        ).derive(shared)
        plaintext = AESGCM(key).decrypt(
            _decode(str(payload["nonce"])),
            _decode(str(payload["ciphertext"])),
            _SEALED_DB_AAD,
        ).decode("utf-8").strip()
    except Exception as exc:
        raise ComanDatabaseConfigurationError("Sealed database credential could not be decrypted.") from exc
    if not plaintext.startswith(("postgres://", "postgresql://")):
        raise ComanDatabaseConfigurationError("Sealed database credential is not a PostgreSQL URL.")
    return plaintext


def resolve_database_url(explicit_url: str | None = None) -> str:
    database_url = str(
        explicit_url
        or os.environ.get("COMAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or _sealed_database_url()
        or ""
    ).strip()
    if not database_url:
        try:
            import streamlit as st

            database_url = str(
                st.secrets.get("COMAN_DATABASE_URL")
                or st.secrets.get("DATABASE_URL")
                or ""
            ).strip()
        except Exception:
            database_url = ""
    if not database_url:
        raise ComanDatabaseConfigurationError(
            "Co-Man database is not configured. Set DATABASE_URL or provide the sealed Render credential."
        )
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://") :]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def _int_setting(name: str, default: int, *, minimum: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def create_coman_engine(database_url: str | None = None) -> Engine:
    resolved = resolve_database_url(database_url)
    options: dict = {"future": True, "pool_pre_ping": True}
    if resolved.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options["pool_size"] = _int_setting("DATABASE_POOL_SIZE", 2, minimum=1)
        options["max_overflow"] = _int_setting("DATABASE_MAX_OVERFLOW", 0, minimum=0)
        options["pool_timeout"] = _int_setting("DATABASE_POOL_TIMEOUT", 30, minimum=1)
        options["pool_use_lifo"] = True
        options["pool_recycle"] = 300
        options["connect_args"] = {"connect_timeout": 5}
    return create_engine(resolved, **options)
