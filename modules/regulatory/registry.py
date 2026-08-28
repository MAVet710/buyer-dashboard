"""Authoritative, provider-neutral regulatory jurisdiction registry.

Market membership is sourced from Metrc's official partner directory. API hosts
were verified by loading the official ``/Documentation/`` page on 2026-08-28;
they are not inferred at runtime from a state-code URL pattern. Capability
claims remain conservative: endpoint-family evidence is recorded per
jurisdiction, and anything not explicitly verified remains unknown.

Endpoint documentation establishes technical surface area only. It does not
establish legal authority, user permission, license scope, or facility access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


OFFICIAL_MARKETS_SOURCE = "https://www.metrc.com/partners/"
OFFICIAL_API_DOCUMENTATION_PATH = "/Documentation/"
REGISTRY_VERIFIED_ON = "2026-08-28"


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    RESTRICTED = "restricted"
    JURISDICTION_SPECIFIC = "jurisdiction-specific"
    SANDBOX_ONLY = "sandbox-only"
    PRODUCTION_ONLY = "production-only"
    UNKNOWN = "unknown/unverified"


CAPABILITIES = (
    "facilities", "employee_permissions", "items", "packages",
    "package_adjustments", "package_waste", "package_finish_unfinish",
    "locations", "lab_tests", "transfers", "transfer_templates",
    "deliveries", "wholesale_packages", "manifests", "transporters",
    "vehicles", "plants", "plant_batches", "harvests", "processing_jobs",
    "sales", "tags", "sandbox_setup", "sandbox_package_creation",
    "sandbox_tag_generation",
)


@dataclass(frozen=True)
class CapabilityEvidence:
    capability: str
    endpoint: str
    source_url: str
    verified_on: str = REGISTRY_VERIFIED_ON
    note: str = "Official Metrc API documentation lists this endpoint family."

    def public(self) -> dict[str, str]:
        return {
            "capability": self.capability,
            "endpoint": self.endpoint,
            "source_url": self.source_url,
            "verified_on": self.verified_on,
            "note": self.note,
        }


@dataclass(frozen=True)
class JurisdictionProfile:
    code: str
    name: str
    provider: str
    api_base: str
    environments: tuple[str, ...]
    api_version_preference: str
    active: bool
    capabilities: dict[str, CapabilityStatus]
    capability_evidence: dict[str, CapabilityEvidence]
    source_url: str = OFFICIAL_MARKETS_SOURCE
    documentation_url: str = ""
    verified_on: str = REGISTRY_VERIFIED_ON
    notes: str = "Capabilities not explicitly verified remain unknown."

    @property
    def documentation_verified(self) -> bool:
        return any(key != "facilities" for key in self.capability_evidence)

    def public(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "provider": self.provider,
            "api_base": self.api_base,
            "environments": list(self.environments),
            "api_version_preference": self.api_version_preference,
            "active": self.active,
            "capabilities": {key: value.value for key, value in self.capabilities.items()},
            "capability_evidence": {key: value.public() for key, value in self.capability_evidence.items()},
            "documentation_verified": self.documentation_verified,
            "source_url": self.source_url,
            "documentation_url": self.documentation_url,
            "verified_on": self.verified_on,
            "notes": self.notes,
        }


_MARKETS = {
    "AL": "Alabama", "AK": "Alaska", "CA": "California", "CO": "Colorado",
    "DC": "District of Columbia", "GU": "Guam", "IL": "Illinois",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NV": "Nevada",
    "NJ": "New Jersey", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "RI": "Rhode Island", "SD": "South Dakota",
    "VI": "US Virgin Islands", "VA": "Virginia", "WV": "West Virginia",
}

# Explicit verified hosts. Never derive one by interpolating an arbitrary code.
_VERIFIED_API_BASES = {
    "AL": "https://api-al.metrc.com",
    "AK": "https://api-ak.metrc.com",
    "CA": "https://api-ca.metrc.com",
    "CO": "https://api-co.metrc.com",
    "DC": "https://api-dc.metrc.com",
    "GU": "https://api-gu.metrc.com",
    "IL": "https://api-il.metrc.com",
    "KY": "https://api-ky.metrc.com",
    "LA": "https://api-la.metrc.com",
    "ME": "https://api-me.metrc.com",
    "MD": "https://api-md.metrc.com",
    "MA": "https://api-ma.metrc.com",
    "MI": "https://api-mi.metrc.com",
    "MN": "https://api-mn.metrc.com",
    "MS": "https://api-ms.metrc.com",
    "MO": "https://api-mo.metrc.com",
    "MT": "https://api-mt.metrc.com",
    "NV": "https://api-nv.metrc.com",
    "NJ": "https://api-nj.metrc.com",
    "NY": "https://api-ny.metrc.com",
    "OH": "https://api-oh.metrc.com",
    "OK": "https://api-ok.metrc.com",
    "OR": "https://api-or.metrc.com",
    "RI": "https://api-ri.metrc.com",
    "SD": "https://api-sd.metrc.com",
    "VI": "https://api-vi.metrc.com",
    "VA": "https://api-va.metrc.com",
    "WV": "https://api-wv.metrc.com",
}

_NAME_ALIASES = {name.casefold(): code for code, name in _MARKETS.items()}
_NAME_ALIASES.update({"washington dc": "DC", "washington d.c.": "DC", "u.s. virgin islands": "VI", "virgin islands": "VI"})

# Current official v2 documentation was directly inspected on 2026-08-28 for
# these jurisdictions. The remaining jurisdictions stay fail-closed until the
# same endpoint-family evidence can be retrieved and reviewed. This prevents a
# temporarily unavailable documentation host from becoming an invented claim.
DOCUMENTATION_VERIFIED_JURISDICTIONS = frozenset({
    "AK", "CA", "CO", "DC", "IL", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NV", "NJ", "NY", "OH", "OK", "OR", "RI", "SD",
})

# Evidence anchors intentionally use one representative official endpoint per
# capability family. Presence means the family is documented for the market;
# runtime authorization still depends on the exact tenant, facility, license,
# credential, environment, and Metrc permissions.
DOCUMENTED_V2_CAPABILITY_ENDPOINTS = {
    "employee_permissions": "GET /employees/v2/permissions",
    "items": "GET /items/v2/active",
    "packages": "GET /packages/v2/active",
    "package_adjustments": "GET /packages/v2/adjustments",
    "package_finish_unfinish": "PUT /packages/v2/finish",
    "locations": "GET /locations/v2/active",
    "lab_tests": "GET /labtests/v2/results",
    "transfers": "GET /transfers/v2/incoming",
    "transfer_templates": "GET /transfers/v2/templates/outgoing",
    "deliveries": "GET /transfers/v2/{id}/deliveries",
    "wholesale_packages": "GET /transfers/v2/deliveries/{id}/packages/wholesale",
    "manifests": "GET /transfers/v2/manifest/{id}/pdf",
    "transporters": "GET /transporters/v2/drivers",
    "vehicles": "GET /transporters/v2/vehicles",
    "plants": "GET /plants/v2/vegetative",
    "plant_batches": "GET /plantbatches/v2/active",
    "harvests": "GET /harvests/v2/active",
    "processing_jobs": "GET /processing/v2/active",
    "sales": "GET /sales/v2/receipts/active",
    "tags": "GET /tags/v2/package/available",
    "sandbox_setup": "POST /sandbox/v2/integrator/setup",
    "sandbox_package_creation": "POST /sandbox/v2/packages/create",
    "sandbox_tag_generation": "POST /sandbox/v2/facility/tags",
}


def _base_capabilities() -> dict[str, CapabilityStatus]:
    values = {name: CapabilityStatus.UNKNOWN for name in CAPABILITIES}
    values["facilities"] = CapabilityStatus.SUPPORTED
    return values


def _base_evidence(code: str) -> dict[str, CapabilityEvidence]:
    documentation_url = f"{_VERIFIED_API_BASES[code]}{OFFICIAL_API_DOCUMENTATION_PATH}"
    return {
        "facilities": CapabilityEvidence(
            capability="facilities",
            endpoint="GET /facilities/v2/",
            source_url=documentation_url,
            note="The jurisdiction API host and facilities endpoint were verified during registry creation.",
        )
    }


_REGISTRY = {
    code: JurisdictionProfile(
        code=code,
        name=name,
        provider="metrc",
        api_base=_VERIFIED_API_BASES[code],
        environments=("production", "sandbox") if code in DOCUMENTATION_VERIFIED_JURISDICTIONS else ("production",),
        api_version_preference="v2",
        active=True,
        capabilities=_base_capabilities(),
        capability_evidence=_base_evidence(code),
        documentation_url=f"{_VERIFIED_API_BASES[code]}{OFFICIAL_API_DOCUMENTATION_PATH}",
    )
    for code, name in _MARKETS.items()
}

for _code in DOCUMENTATION_VERIFIED_JURISDICTIONS:
    _profile = _REGISTRY[_code]
    for _capability, _endpoint in DOCUMENTED_V2_CAPABILITY_ENDPOINTS.items():
        _profile.capabilities[_capability] = (
            CapabilityStatus.SANDBOX_ONLY
            if _capability.startswith("sandbox_")
            else CapabilityStatus.JURISDICTION_SPECIFIC
        )
        _profile.capability_evidence[_capability] = CapabilityEvidence(
            capability=_capability,
            endpoint=_endpoint,
            source_url=_profile.documentation_url,
        )


def normalize_jurisdiction(value: str) -> str:
    token = str(value or "").strip()
    if token.casefold().startswith(("https://", "http://")):
        normalized = token.rstrip("/").casefold()
        for code, base in _VERIFIED_API_BASES.items():
            if normalized == base.casefold():
                return code
        return ""
    upper = token.upper()
    if upper in _REGISTRY:
        return upper
    return _NAME_ALIASES.get(token.casefold(), "")


def get_jurisdiction(value: str, *, provider: str = "metrc", active_only: bool = True) -> JurisdictionProfile | None:
    if str(provider or "").casefold() != "metrc":
        return None
    profile = _REGISTRY.get(normalize_jurisdiction(value))
    if profile is None or (active_only and not profile.active):
        return None
    return profile


def list_jurisdictions(*, provider: str = "metrc", active_only: bool = True) -> tuple[JurisdictionProfile, ...]:
    if str(provider or "").casefold() != "metrc":
        return ()
    return tuple(profile for profile in _REGISTRY.values() if profile.active or not active_only)


def resolve_metrc_base_url(value: str) -> tuple[str, str]:
    profile = get_jurisdiction(value)
    return (profile.api_base, profile.code) if profile else ("", str(value or "").strip().upper())


def capability_status(jurisdiction: str, capability: str) -> CapabilityStatus:
    profile = get_jurisdiction(jurisdiction)
    if profile is None or capability not in CAPABILITIES:
        return CapabilityStatus.UNKNOWN
    return profile.capabilities[capability]


def capability_evidence(jurisdiction: str, capability: str) -> CapabilityEvidence | None:
    profile = get_jurisdiction(jurisdiction)
    if profile is None:
        return None
    return profile.capability_evidence.get(capability)


def require_capability(jurisdiction: str, capability: str, *, environment: str) -> CapabilityStatus:
    environment = str(environment or "").strip().casefold()
    if environment not in {"sandbox", "production"}:
        raise ValueError("Regulatory environment must be sandbox or production.")
    profile = get_jurisdiction(jurisdiction)
    if profile is None:
        raise ValueError("The regulatory jurisdiction is not verified in the active registry.")
    if environment not in profile.environments:
        raise ValueError(f"{environment} is not verified for {profile.code}.")
    status = capability_status(profile.code, capability)
    if status in {CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED}:
        raise ValueError(f"{capability} is {status.value} for {profile.code}.")
    if status == CapabilityStatus.SANDBOX_ONLY and environment != "sandbox":
        raise ValueError(f"{capability} is sandbox-only for {profile.code}.")
    if status == CapabilityStatus.PRODUCTION_ONLY and environment != "production":
        raise ValueError(f"{capability} is production-only for {profile.code}.")
    return status
