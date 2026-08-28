from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory import RegulatoryMappingService
from modules.regulatory.models import RegulatoryFacilityMapping
from ..auth import RequestContext
from ..config import Settings


@dataclass(frozen=True)
class MetrcContext:
    configured: bool
    state: str = ""
    license_number: str = ""
    user_api_key: str = ""
    integrator_api_key: str = ""
    status: str = "not_connected"
    environment: str = "production"
    trusted_mapping: bool = False
    message: str = ""
    row: IntegrationConfiguration | None = None
    mapping: RegulatoryFacilityMapping | None = None


def metrc_scope_key(context: RequestContext) -> str:
    """Keep a user's Metrc key/license isolated to the active facility.

    A user may legitimately work in a retail license and a separate
    production/cultivation license. Reusing one user-wide record would leak the
    wrong license into the other operation. The composite key preserves the
    existing user-scoped credential model while adding facility isolation.
    """

    return f"{context.user_id}|{context.facility_id}"


def resolve_metrc_context(
    engine: Engine, settings: Settings, context: RequestContext
) -> tuple[IntegrationConfigurationService | None, MetrcContext]:
    # Development/test environments intentionally allow local deterministic
    # inventory workflows without integration secrets. Production startup is
    # already fail-closed on INTEGRATION_ENCRYPTION_KEY, so treating a missing
    # key as an unconfigured METRC connection here preserves local inventory
    # work without weakening production credential handling.
    if not str(settings.integration_encryption_key or "").strip():
        return None, MetrcContext(
            configured=False,
            integrator_api_key=settings.metrc_integrator_key,
            message="METRC is not configured for this environment.",
        )

    service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
    row = service.get("user", metrc_scope_key(context), "metrc")

    # Compatibility with credentials created before facility-specific scope was
    # introduced. Only reuse a legacy record when it was saved for this exact
    # facility; never carry a retail license into production or vice versa.
    if row is None:
        legacy = service.get("user", context.user_id, "metrc")
        if legacy is not None and str(legacy.facility_id or "") == str(context.facility_id):
            row = legacy

    if row is None:
        return service, MetrcContext(
            configured=False,
            integrator_api_key=settings.metrc_integrator_key,
            message="No METRC integration is saved for this user at the active facility.",
        )

    public = service.public(row)
    config = public.get("configuration", {})
    secret = service.secret(row)
    state = str(config.get("state") or "").strip()
    license_number = str(config.get("license_number") or "").strip()
    environment = str(config.get("environment") or "production").strip().casefold()
    mapping = RegulatoryMappingService(engine).get(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        provider="metrc",
        license_number=license_number,
        environment=environment,
    ) if state and license_number and environment in {"sandbox", "production"} else None
    trusted_mapping = bool(
        mapping
        and mapping.integration_configuration_id == row.id
        and mapping.jurisdiction_code == state.upper()
    )
    configured = bool(secret and state and license_number and settings.metrc_integrator_key)
    return service, MetrcContext(
        configured=configured,
        state=state,
        license_number=license_number,
        user_api_key=secret,
        integrator_api_key=settings.metrc_integrator_key,
        status=str(public.get("status") or "not_connected"),
        environment=environment,
        trusted_mapping=trusted_mapping,
        message=(
            "METRC connection and trusted facility mapping are ready."
            if configured and trusted_mapping
            else "An administrator must verify the facility, license, jurisdiction, provider, credential, and environment mapping before live regulatory operations."
            if configured
            else "Save and validate METRC credentials for this facility before loading inbound transfers."
        ),
        row=row,
        mapping=mapping,
    )
