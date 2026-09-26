"""Read-only guided setup projection. Credentials stay in their existing stores."""
import json

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Product
from modules.integrations.accounting_links import AccountingSyncLink
from .adoption_models import ReadinessAnnotation
from .implementation_readiness import scope

PROVIDERS = {"metrc": "Metrc", "biotrack": "BioTrack", "quickbooks": "QuickBooks", "spacemail": "Spacemail", "ai_runtime": "AI runtime", "doobie": "Doobie AI"}
STEPS = ("facility", "systems", "connect", "validate", "map", "evidence", "summary")


def wizard(engine, settings, context):
    # Reuse public configuration contracts and the authoritative Metrc resolver.
    # These reads never dispatch a provider request.
    from ..routers.integrations import integrations
    from ..routers.native_integrations import native_integrations
    from ..routers.alpha_operating_mode import current_mode
    from .metrc_context import resolve_metrc_context

    with Session(engine) as session:
        facility = session.scalar(select(Facility).where(Facility.id == context.facility_id, Facility.organization_id == context.organization_id))
        if not facility:
            raise HTTPException(404, "Facility not found in this organization.")
        capabilities = [name for name in ("retail", "production", "cultivation", "commercial") if getattr(facility, name + "_enabled")]
        facility_public = {"id": facility.id, "name": facility.name, "license_number": facility.license_number, "license_type": facility.license_type, "capabilities": capabilities}
        notes = dict(session.execute(select(ReadinessAnnotation.item_key, ReadinessAnnotation.notes).where(*scope(ReadinessAnnotation, context))).all())
        missing_items = session.scalar(select(func.count()).select_from(Product).where(
            Product.organization_id == context.organization_id, Product.active.is_(True),
            ~exists().where(*scope(AccountingSyncLink, context), AccountingSyncLink.provider == "quickbooks",
                AccountingSyncLink.entity_type == "item", AccountingSyncLink.internal_id == Product.id,
                AccountingSyncLink.status == "synced", AccountingSyncLink.external_id != "")))
        failed_links = session.scalar(select(func.count()).select_from(AccountingSyncLink).where(*scope(AccountingSyncLink, context), AccountingSyncLink.provider == "quickbooks", AccountingSyncLink.status != "synced"))
    try:
        progress = json.loads(notes.get("wizard_progress", "{}"))
    except ValueError:
        progress = {}
    mode = current_mode(context, engine)
    values, unavailable = {}, set()
    for reader, providers in ((integrations, {"metrc", "spacemail", "ai_runtime", "doobie"}), (native_integrations, {"biotrack", "quickbooks"})):
        try:
            result = reader(context, engine, settings)
            values.update({key: result.get(key) for key in providers})
        except (HTTPException, RuntimeError):
            unavailable.update(providers)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError:
        metrc = None
    items = []
    for key, label in PROVIDERS.items():
        value = values.get(key)
        required = key == "metrc" and mode["effective_mode"] == "metrc_sandbox"
        applicable = bool(capabilities) if key in {"metrc", "biotrack"} else ("commercial" in capabilities if key == "quickbooks" else True)
        # An explicitly selected Metrc mode is required even if capabilities change.
        applicable = applicable or required
        skipped = notes.get("wizard_" + key) == "skipped" and not required
        config = (value or {}).get("configuration") or {}
        status, evidence = "needs_validation", "Save connection settings, then run the existing provider test. Saved credentials alone are not validation."
        test_path = f"/api/v1/{'native-integrations' if key in {'biotrack', 'quickbooks'} else 'integrations'}/{key.replace('_', '-')}/test"
        if value and value.get("status") == "connected" and value.get("last_validated_at"):
            status, evidence = "connected", "Successful provider connection validation is recorded. This does not prove production workflow readiness."
        if value and value.get("status") == "failed":
            status, evidence = "blocked", "The last provider validation failed. Review advanced settings and run the test again."
        if key == "metrc":
            if not required:
                applicable, test_path = False, None
                evidence = "DoobieLogic Sandbox is selected. Metrc dispatch is disabled. Change the facility operating mode in advanced settings to opt into Metrc Sandbox."
            elif metrc is None or not metrc.configured:
                status, evidence, test_path = "blocked", "Metrc sandbox credentials, state and exact facility license must resolve before testing. Review the existing sandbox connection settings.", None
            elif not metrc.trusted_mapping and status != "blocked":
                status, evidence = "needs_mapping", "Verify the exact facility, license, jurisdiction, credential and sandbox mapping in advanced settings."
        if key == "quickbooks" and status == "connected" and missing_items:
            status, evidence = "needs_mapping", f"{missing_items} active organization products lack a successful Item mapping for this facility. Review products used on invoices before synchronization."
        if key == "quickbooks" and failed_links:
            status, evidence = "blocked", f"{failed_links} accounting links are failed or stale. Review accounting synchronization health in Wholesale Ops."
        if key in unavailable or value is None:
            status, evidence, test_path = "blocked", "Connection evidence is unavailable. Open advanced settings to resolve access or configuration.", None
            if key in {"spacemail", "ai_runtime", "doobie"} and context.role != "dev":
                evidence = "Platform-scoped connection. A DEV operator must configure and validate it; facility administrator access does not expose platform settings."
        if key == "biotrack":
            evidence += " BioTrack requires an explicit state-approved API contract. Availability for this facility is not inferred from its license or saved credentials."
        if not applicable:
            status = "not_applicable"
            if key != "metrc":
                evidence = "The related facility capability is disabled."
        elif skipped:
            status, evidence = "optional_skipped", "Optional setup deferred for this facility. This does not attest to a validated connection."
        items.append({"key": key, "label": label, "required": required, "status": status, "evidence": evidence,
            "last_validated_at": (value or {}).get("last_validated_at"),
            "environment": metrc.environment if key == "metrc" and metrc else config.get("environment", "platform" if key in {"spacemail", "ai_runtime", "doobie"} else "not configured"),
            "test_path": test_path if applicable and not skipped else None,
            "route": "Integration Wizard", "settings_path": "/settings/integrations?provider=" + key,
            "mapping_route": "Wholesale Ops" if key == "quickbooks" else "Integrations",
            "managed_entities": ["customer", "invoice"] if key == "quickbooks" else [],
            "manual_mapping_required": ["product -> QuickBooks Item"] if key == "quickbooks" else [],
            "missing_item_mappings": missing_items if key == "quickbooks" else 0})
    return {"facility": facility_public, "mode": mode, "items": items,
        "step": progress.get("step", "facility") if progress.get("step") in STEPS else "facility",
        "can_manage": context.role.casefold() in {"admin", "dev"}}
