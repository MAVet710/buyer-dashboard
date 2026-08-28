from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory import (
    DOCUMENTATION_VERIFIED_JURISDICTIONS,
    CapabilityStatus,
    RegulatoryMappingError,
    RegulatoryMappingService,
    capability_evidence,
    capability_status,
    get_jurisdiction,
    list_jurisdictions,
    require_capability,
    resolve_metrc_base_url,
)


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all((
            Organization(id="org-1", name="One", slug="one"),
            Organization(id="org-2", name="Two", slug="two"),
            Facility(id="fac-1", organization_id="org-1", name="One Production", code="ONE"),
            Facility(id="fac-2", organization_id="org-2", name="Two Retail", code="TWO"),
        ))
        session.flush()
        session.add_all((
            IntegrationConfiguration(
                id="credential-1", organization_id="org-1", facility_id="fac-1",
                scope_type="user", scope_key="user-1|fac-1", provider="metrc",
                configuration_json=json.dumps({"state": "OR", "license_number": "OR-1", "environment": "production"}),
                encrypted_secret="encrypted-not-a-real-secret", updated_by="admin-1",
            ),
            IntegrationConfiguration(
                id="credential-2", organization_id="org-2", facility_id="fac-2",
                scope_type="user", scope_key="user-2|fac-2", provider="metrc",
                configuration_json=json.dumps({"state": "OR", "license_number": "OR-2", "environment": "production"}),
                encrypted_secret="encrypted-not-a-real-secret", updated_by="admin-2",
            ),
        ))
        session.commit()
    return engine


def test_registry_resolves_only_explicit_verified_metrc_hosts():
    assert len(list_jurisdictions()) == 28
    assert resolve_metrc_base_url("Oregon") == ("https://api-or.metrc.com", "OR")
    assert resolve_metrc_base_url("https://api-or.metrc.com") == ("https://api-or.metrc.com", "OR")
    assert resolve_metrc_base_url("ZZ") == ("", "ZZ")
    assert resolve_metrc_base_url("https://api-zz.metrc.com") == ("", "HTTPS://API-ZZ.METRC.COM")
    assert all(profile.source_url == "https://www.metrc.com/partners/" for profile in list_jurisdictions())
    assert all(profile.documentation_url.endswith("/Documentation/") for profile in list_jurisdictions())


def test_capabilities_expand_only_for_directly_verified_jurisdictions():
    assert len(DOCUMENTATION_VERIFIED_JURISDICTIONS) == 20
    assert "MA" in DOCUMENTATION_VERIFIED_JURISDICTIONS
    assert "OR" in DOCUMENTATION_VERIFIED_JURISDICTIONS
    assert "RI" not in DOCUMENTATION_VERIFIED_JURISDICTIONS

    assert capability_status("OR", "packages") == CapabilityStatus.JURISDICTION_SPECIFIC
    assert capability_status("MA", "packages") == CapabilityStatus.JURISDICTION_SPECIFIC
    assert capability_status("RI", "packages") == CapabilityStatus.UNKNOWN
    assert require_capability("MA", "packages", environment="production") == CapabilityStatus.JURISDICTION_SPECIFIC
    with pytest.raises(ValueError, match="unknown/unverified"):
        require_capability("RI", "packages", environment="production")
    with pytest.raises(ValueError, match="not verified"):
        require_capability("ZZ", "facilities", environment="production")


def test_capability_evidence_is_sourceable_and_sandbox_stays_environment_gated():
    evidence = capability_evidence("MA", "transfers")
    assert evidence is not None
    assert evidence.endpoint == "GET /transfers/v2/incoming"
    assert evidence.source_url == "https://api-ma.metrc.com/Documentation/"
    assert evidence.verified_on == "2026-08-28"

    ma = get_jurisdiction("MA")
    ri = get_jurisdiction("RI")
    assert ma is not None and ma.documentation_verified is True
    assert ri is not None and ri.documentation_verified is False

    assert capability_status("MA", "sandbox_setup") == CapabilityStatus.SANDBOX_ONLY
    assert require_capability("MA", "sandbox_setup", environment="sandbox") == CapabilityStatus.SANDBOX_ONLY
    with pytest.raises(ValueError, match="sandbox-only"):
        require_capability("MA", "sandbox_setup", environment="production")
    with pytest.raises(ValueError, match="sandbox is not verified"):
        require_capability("RI", "facilities", environment="sandbox")


def test_package_waste_stays_unknown_without_direct_endpoint_evidence():
    assert capability_status("MA", "package_waste") == CapabilityStatus.UNKNOWN
    assert capability_evidence("MA", "package_waste") is None
    with pytest.raises(ValueError, match="unknown/unverified"):
        require_capability("MA", "package_waste", environment="production")


def test_mapping_binds_exact_tenant_facility_license_credential_and_environment():
    service = RegulatoryMappingService(_engine())
    row = service.verify(
        organization_id="org-1", facility_id="fac-1", provider="metrc",
        jurisdiction_code="OR", license_number="OR-1", provider_facility_id="provider-facility-1",
        environment="production", integration_configuration_id="credential-1", actor="admin-1",
    )
    public = service.public(row)
    assert public["credential_configured"] is True
    assert public["jurisdiction_code"] == "OR"
    assert "encrypted_secret" not in public
    assert service.get(
        organization_id="org-1", facility_id="fac-1", provider="metrc",
        license_number="OR-1", environment="production",
    ).id == row.id
    assert service.get(
        organization_id="org-1", facility_id="fac-1", provider="metrc",
        license_number="OR-1", environment="sandbox",
    ) is None


def test_mapping_rejects_cross_tenant_facility_and_credential_substitution():
    service = RegulatoryMappingService(_engine())
    with pytest.raises(RegulatoryMappingError, match="facility does not belong"):
        service.verify(
            organization_id="org-1", facility_id="fac-2", provider="metrc", jurisdiction_code="OR",
            license_number="OR-1", provider_facility_id="", environment="production",
            integration_configuration_id="credential-1", actor="attacker",
        )
    with pytest.raises(RegulatoryMappingError, match="credential does not match"):
        service.verify(
            organization_id="org-1", facility_id="fac-1", provider="metrc", jurisdiction_code="OR",
            license_number="OR-1", provider_facility_id="", environment="production",
            integration_configuration_id="credential-2", actor="attacker",
        )


def test_mapping_rejects_same_facility_license_or_environment_substitution():
    service = RegulatoryMappingService(_engine())
    with pytest.raises(RegulatoryMappingError, match="configuration does not match"):
        service.verify(
            organization_id="org-1", facility_id="fac-1", provider="metrc", jurisdiction_code="OR",
            license_number="OR-DIFFERENT", provider_facility_id="", environment="production",
            integration_configuration_id="credential-1", actor="attacker",
        )
    with pytest.raises(RegulatoryMappingError, match="configuration does not match"):
        service.verify(
            organization_id="org-1", facility_id="fac-1", provider="metrc", jurisdiction_code="OR",
            license_number="OR-1", provider_facility_id="", environment="sandbox",
            integration_configuration_id="credential-1", actor="attacker",
        )


def test_registry_does_not_claim_metrc_documentation_is_legal_authority():
    profile = get_jurisdiction("OR")
    assert profile is not None
    assert "legal" not in profile.notes.casefold()
    assert profile.api_version_preference == "v2"
