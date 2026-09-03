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


def metrc_sandbox_scope_key(context: RequestContext) -> str:
    """Match the existing DEV/Admin sandbox connection scope."""

    return f"{context.organization_id}:{context.facility_id}:sandbox"


def _sandbox_vendor_context(
    service: IntegrationConfigurationService,
    context: RequestContext,
) -> tuple[IntegrationConfiguration | None, dict, str]:
    """Return the encrypted Metrc sandbox vendor/integrator credential, if saved.

    The Developer Connections surface predates the live Metrc adapter. Its
    ``metrc_sandbox`` encrypted secret is now the canonical in-app location for
    the Metrc Connect vendor/integrator key. This keeps the key out of source,
    Streamlit, and browser-readable configuration while allowing FastAPI to use
    the credential that an administrator already saved in the app.
    """

    row = service.get("facility", metrc_sandbox_scope_key(context), "metrc_sandbox")
    if row is None:
        return None, {}, ""
    public = service.public(row)
    configuration = public.get("configuration")
    config = dict(configuration) if isinstance(configuration, dict) else {}
    return row, config, service.secret(row)


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
            message="METRC encrypted credential storage is not configured for this environment.",
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

    sandbox_row, sandbox_config, sandbox_vendor_key = _sandbox_vendor_context(service, context)
    integrator_api_key = str(sandbox_vendor_key or settings.metrc_integrator_key or "").strip()

    if row is None:
        sandbox_state = str(sandbox_config.get("state") or "").strip()
        sandbox_license = str(sandbox_config.get("license_number") or "").strip()
        if sandbox_row is not None:
            return service, MetrcContext(
                configured=False,
                state=sandbox_state,
                license_number=sandbox_license,
                integrator_api_key=integrator_api_key,
                environment="sandbox",
                status=str(service.public(sandbox_row).get("status") or "configured"),
                message=(
                    "The Metrc sandbox integrator/vendor key is saved in DoobieLogic. "
                    "A distinct Metrc sandbox user API key is still required before facility API calls can run."
                ),
            )
        return service, MetrcContext(
            configured=False,
            integrator_api_key=integrator_api_key,
            message="No METRC user/facility integration is saved for this account at the active facility.",
        )

    public = service.public(row)
    config = public.get("configuration", {})
    secret = service.secret(row)
    state = str(config.get("state") or "").strip()
    license_number = str(config.get("license_number") or "").strip()
    environment = str(config.get("environment") or "production").strip().casefold()

    # The old React METRC card did not expose environment and therefore saved
    # "production" even when an administrator had separately configured the
    # explicit MA sandbox connection. Migrate that state safely at runtime only
    # when the sandbox connection matches the same state/license and the saved
    # single METRC secret is the same vendor key. This prevents a sandbox setup
    # from ever falling through to production while avoiding a broad implicit
    # environment switch for real production credentials.
    sandbox_state = str(sandbox_config.get("state") or "").strip().upper()
    sandbox_license = str(sandbox_config.get("license_number") or "").strip()
    sandbox_matches = bool(
        sandbox_row
        and sandbox_state
        and sandbox_state == state.upper()
        and (not sandbox_license or sandbox_license == license_number)
    )
    if sandbox_matches and (environment == "sandbox" or (secret and secret == sandbox_vendor_key)):
        environment = "sandbox"
        integrator_api_key = str(sandbox_vendor_key or integrator_api_key).strip()

    user_api_key = str(secret or "").strip()
    if integrator_api_key and user_api_key == integrator_api_key:
        # A Metrc Connect vendor/integrator key and a Metrc user API key are two
        # different credentials. Older UI exposed only one METRC key input, so
        # fail closed and explain the missing user key instead of sending the
        # vendor key in both Basic Auth positions.
        user_api_key = ""

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
    configured = bool(user_api_key and state and license_number and integrator_api_key)

    if configured and trusted_mapping:
        message = "METRC connection and trusted facility mapping are ready."
    elif configured:
        message = "An administrator must verify the facility, license, jurisdiction, provider, credential, and environment mapping before live regulatory operations."
    elif integrator_api_key and not user_api_key:
        message = (
            "The Metrc integrator/vendor key is saved. Add the distinct Metrc user API key for this sandbox facility, "
            "then validate the connection."
        )
    elif not integrator_api_key:
        message = "Save the Metrc integrator/vendor key in DoobieLogic before validating this facility."
    else:
        message = "Save and validate METRC credentials for this facility before loading live provider data."

    return service, MetrcContext(
        configured=configured,
        state=state,
        license_number=license_number,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        status=str(public.get("status") or "not_connected"),
        environment=environment,
        trusted_mapping=trusted_mapping,
        message=message,
        row=row,
        mapping=mapping,
    )
