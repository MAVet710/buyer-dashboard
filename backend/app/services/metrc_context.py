from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
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
    """Keep a user's Metrc key/license isolated to the active facility."""

    return f"{context.user_id}|{context.facility_id}"


def metrc_sandbox_scope_key(context: RequestContext) -> str:
    """Match the existing DEV/Admin sandbox connection scope."""

    return f"{context.organization_id}:{context.facility_id}:sandbox"


def _sandbox_vendor_context(
    service: IntegrationConfigurationService,
    context: RequestContext,
) -> tuple[IntegrationConfiguration | None, dict, str]:
    """Return the encrypted Metrc sandbox vendor/integrator credential, if saved."""

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
    mode = AlphaOperatingModeService(engine).current(
        context.organization_id,
        context.facility_id,
    )

    # Alpha exposes only local operation or the provider sandbox. Production is
    # deliberately outside this selector and requires a future explicit release
    # path rather than being inferred from an older saved connection.
    if not str(settings.integration_encryption_key or "").strip():
        return None, MetrcContext(
            configured=False,
            integrator_api_key=settings.metrc_integrator_key if mode.metrc_enabled else "",
            environment="sandbox",
            status="disabled_by_alpha_mode" if not mode.metrc_enabled else "not_connected",
            message=(
                "DoobieLogic Sandbox is active for this facility. Metrc provider reads and writes are disabled until an administrator selects Metrc Sandbox."
                if not mode.metrc_enabled
                else "Metrc Sandbox is selected, but encrypted credential storage is not configured for this environment."
            ),
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

    # The alpha operating mode is authoritative before provider credentials are
    # decrypted or a provider call can be prepared. Keep the saved row visible
    # to the Integrations UI, but do not expose a usable runtime key in local mode.
    if not mode.metrc_enabled:
        public = service.public(row)
        config = public.get("configuration", {}) if isinstance(public, dict) else {}
        return service, MetrcContext(
            configured=False,
            state=str(config.get("state") or sandbox_config.get("state") or "").strip(),
            license_number=str(config.get("license_number") or sandbox_config.get("license_number") or "").strip(),
            integrator_api_key="",
            status="disabled_by_alpha_mode",
            environment="sandbox",
            trusted_mapping=False,
            message=(
                "DoobieLogic Sandbox is active for this facility. Saved Metrc credentials remain encrypted, "
                "but provider reads and writes are disabled until an administrator selects Metrc Sandbox."
            ),
            row=row,
        )

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
            environment="sandbox",
            message="Metrc Sandbox is selected, but no Metrc user/facility sandbox integration is saved for this account at the active facility.",
        )

    public = service.public(row)
    config = public.get("configuration", {})
    state = str(config.get("state") or "").strip()
    license_number = str(config.get("license_number") or "").strip()
    configured_environment = str(config.get("environment") or "production").strip().casefold()

    sandbox_state = str(sandbox_config.get("state") or "").strip().upper()
    sandbox_license = str(sandbox_config.get("license_number") or "").strip()
    sandbox_matches = bool(
        sandbox_row
        and sandbox_state
        and sandbox_state == state.upper()
        and (not sandbox_license or sandbox_license == license_number)
    )

    # Older web UI saved production as its implicit default. A verified sandbox
    # vendor connection for the same facility safely proves that this old row is
    # actually part of the sandbox setup. Otherwise, never reinterpret or use a
    # production credential while the alpha Metrc Sandbox mode is selected.
    if configured_environment == "sandbox" or sandbox_matches:
        environment = "sandbox"
    else:
        return service, MetrcContext(
            configured=False,
            state=state,
            license_number=license_number,
            integrator_api_key="",
            status="production_blocked_by_alpha_mode",
            environment="sandbox",
            trusted_mapping=False,
            message=(
                "Metrc Sandbox is selected, but the saved Metrc user credential is marked production. "
                "Alpha will not use or reinterpret a production credential. Save or discover the sandbox credential for this facility."
            ),
            row=row,
        )

    if sandbox_matches:
        integrator_api_key = str(sandbox_vendor_key or integrator_api_key).strip()

    secret = service.secret(row)
    user_api_key = str(secret or "").strip()
    if integrator_api_key and user_api_key == integrator_api_key:
        user_api_key = ""

    mapping = RegulatoryMappingService(engine).get(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        provider="metrc",
        license_number=license_number,
        environment="sandbox",
    ) if state and license_number else None
    trusted_mapping = bool(
        mapping
        and mapping.integration_configuration_id == row.id
        and mapping.jurisdiction_code == state.upper()
    )
    configured = bool(user_api_key and state and license_number and integrator_api_key)

    if configured and trusted_mapping:
        message = "METRC sandbox connection and trusted facility mapping are ready."
    elif configured:
        message = "An administrator must verify the exact sandbox facility, license, jurisdiction, credential, and environment mapping before regulatory operations."
    elif integrator_api_key and not user_api_key:
        message = (
            "The Metrc integrator/vendor key is saved. Add the distinct Metrc user API key for this sandbox facility, "
            "then validate the connection."
        )
    elif not integrator_api_key:
        message = "Save the Metrc sandbox integrator/vendor key in DoobieLogic before validating this facility."
    else:
        message = "Save and validate Metrc sandbox credentials for this facility before loading provider data."

    return service, MetrcContext(
        configured=configured,
        state=state,
        license_number=license_number,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        status=str(public.get("status") or "not_connected"),
        environment="sandbox",
        trusted_mapping=trusted_mapping,
        message=message,
        row=row,
        mapping=mapping,
    )