from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from modules.legal_acceptance.policies import (
    CURRENT_PRIVACY_POLICY,
    CURRENT_TERMS_POLICY,
    PRIVACY_TEXT,
    PRIVACY_VERSION,
    STATEMENT_VERSION,
    TERMS_TEXT,
    TERMS_VERSION,
)


RELEASE_VERSION = "2026-08-1"


def test_published_policy_versions_and_hashes_are_immutable() -> None:
    assert TERMS_VERSION == RELEASE_VERSION
    assert PRIVACY_VERSION == RELEASE_VERSION
    assert STATEMENT_VERSION == RELEASE_VERSION
    assert CURRENT_TERMS_POLICY.document_sha256 == sha256(TERMS_TEXT.encode("utf-8")).hexdigest()
    assert CURRENT_PRIVACY_POLICY.document_sha256 == sha256(PRIVACY_TEXT.encode("utf-8")).hexdigest()


def test_customer_facing_policy_copy_has_no_prerelease_language() -> None:
    customer_copy = "\n".join((TERMS_TEXT, PRIVACY_TEXT)).casefold()
    for phrase in ("beta", "draft", "pending attorney review", "attorney-approved"):
        assert phrase not in customer_copy

    assert "## doobielogic terms of service" in customer_copy
    assert "## doobielogic privacy policy" in customer_copy


def test_acceptance_screen_has_no_beta_caption() -> None:
    source = Path("modules/legal_acceptance/ui.py").read_text(encoding="utf-8").casefold()
    assert "review the beta agreements" not in source
    assert "review the agreements before entering your operations workspace" in source
