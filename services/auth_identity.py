"""Pure helpers for resolving legacy Streamlit-secret identities."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class LegacyIdentity:
    username: str
    stored_value: str
    role: str


def resolve_legacy_identity(
    username: str,
    *,
    dev_users: Mapping[str, str],
    admin_users: Mapping[str, str],
    standard_users: Mapping[str, str],
    require_admin: bool,
) -> LegacyIdentity | None:
    normalized = str(username or "").strip().casefold()
    if not normalized:
        return None
    sources = (
        ((dev_users, "dev"), (admin_users, "admin"))
        if require_admin
        else ((standard_users, "buyer"),)
    )
    for users, role in sources:
        for configured_username, stored_value in users.items():
            if str(configured_username).strip().casefold() == normalized:
                return LegacyIdentity(
                    username=str(configured_username).strip(),
                    stored_value=str(stored_value),
                    role=role,
                )
    return None
