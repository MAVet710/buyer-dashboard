from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, CommercialOrder, Facility, InventoryAudit, InventoryTransaction, Organization, Product, ProductionActual
from modules.commerce_storefronts.models import CommerceStorefront
from modules.integrations.models import IntegrationConfiguration, IntegrationSyncState
from modules.product_master.models import ProductMasterProfile
from .adoption_models import ReadinessAnnotation
from .work import assignee_query

MANUAL_ITEMS = {"permissions", "traceability_mode", "accounting_review", "first_workflow_review"}
ITEMS = {
    "facility": ("Organization and facility configured", "Location Settings"),
    "users": ("Active users assigned", "Admin"),
    "permissions": ("Permissions reviewed (manual)", "Admin"),
    "catalog": ("Applicable organization catalog available", "Production Product Master"),
    "inventory": ("Starting inventory recorded", "Data & Settings"),
    "traceability_mode": ("Traceability operating mode reviewed (manual)", "Integrations"),
    "traceability": ("Traceability integration synchronized", "Integrations"),
    "accounting": ("Accounting integration synchronized", "Integrations"),
    "accounting_review": ("Accounting applicability reviewed (manual)", "Integrations"),
    "storefront": ("Wholesale storefront published", "Wholesale Ops"),
    "first_workflow": ("First operational workflow completed", "Operations Control Tower"),
    "first_workflow_review": ("First operational workflow acceptance (manual)", "Operations Control Tower"),
}


def scope(model, context):
    return (model.organization_id == context.organization_id, model.facility_id == context.facility_id)


def readiness(engine, context):
    # A fixed number of EXISTS probes, independent of inventory or user count.
    with Session(engine) as session:
        facility = session.scalar(
            select(Facility).where(Facility.id == context.facility_id, Facility.organization_id == context.organization_id))
        def has(model, *conditions):
            return bool(session.scalar(select(exists().where(*conditions))))
        configured = bool(facility and facility.active and facility.name and facility.code and has(
            Organization, Organization.id == context.organization_id, Organization.active.is_(True)))
        users = has(AppUserFacilityRole, *scope(AppUserFacilityRole, context), AppUserFacilityRole.user_id == AppUser.id, AppUser.active.is_(True))
        # Products are organization-owned. Apply the same optional catalog profile
        # flags, rather than inventing a second facility product ledger.
        catalog_modes = []
        if facility and facility.retail_enabled:
            catalog_modes.append(ProductMasterProfile.retail_enabled.is_(True))
        if facility and (facility.production_enabled or facility.cultivation_enabled or facility.commercial_enabled):
            catalog_modes.append(ProductMasterProfile.production_enabled.is_(True))
        catalog = bool(catalog_modes) and session.scalar(select(exists(select(Product.id).outerjoin(
            ProductMasterProfile, (ProductMasterProfile.product_id == Product.id) &
            (ProductMasterProfile.organization_id == context.organization_id)).where(
                Product.organization_id == context.organization_id, Product.active.is_(True),
                or_(ProductMasterProfile.product_id.is_(None), *catalog_modes)))))
        inventory = has(InventoryTransaction, *scope(InventoryTransaction, context))
        first = bool(session.scalar(select(or_(
            exists().where(*scope(ProductionActual, context), ProductionActual.completed_at.is_not(None)),
            exists().where(*scope(InventoryAudit, context), InventoryAudit.status == "completed", InventoryAudit.completed_at.is_not(None)),
            exists().where(*scope(CommercialOrder, context), CommercialOrder.status == "fulfilled"),
        ))))
        storefront = has(CommerceStorefront, *scope(CommerceStorefront, context), CommerceStorefront.published.is_(True))
        integrations = list(session.execute(select(IntegrationConfiguration.provider, IntegrationConfiguration.status,
            IntegrationConfiguration.last_validated_at).where(*scope(IntegrationConfiguration, context),
            IntegrationConfiguration.scope_type == "facility")))
        synced = set(session.scalars(select(IntegrationSyncState.provider).where(*scope(IntegrationSyncState, context),
            IntegrationSyncState.environment == "production", IntegrationSyncState.status == "succeeded",
            IntegrationSyncState.last_success_at.is_not(None))))
        annotations = {r.item_key: r for r in session.scalars(select(ReadinessAnnotation).where(*scope(ReadinessAnnotation, context)))}
        owners = {user.id: user.display_name or user.username for user in session.scalars(
            select(AppUser).where(AppUser.organization_id == context.organization_id,
                AppUser.id.in_([r.owner_user_id for r in annotations.values() if r.owner_user_id])))}
        owner_options = [{"id": user.id, "name": user.display_name or user.username}
            for user in session.scalars(assignee_query(context).order_by(AppUser.display_name, AppUser.id).limit(500))]
        facts = {
            "facility": (configured, "Active organization and named facility with a code."),
            "users": (users, "Active user with an explicit assignment to this facility."),
            "catalog": (catalog, "Active organization-owned product applicable to this facility's enabled operations. Review catalog completeness separately."),
            "inventory": (inventory, "Canonical inventory transaction exists at this facility. Review opening balances separately."),
            "storefront": (storefront, "Published wholesale storefront at this facility."),
            "first_workflow": (first, "Completed production actual, completed inventory audit, or fulfilled commercial order at this facility. This does not attest to provider verification."),
        }
        items = []
        for key, (label, route) in ITEMS.items():
            if key == "catalog" and facility and facility.retail_enabled and not facility.production_enabled:
                route = "Retail Product Master"
            status, evidence = "needs_review", "Administrator attestation required, with supporting notes."
            if key in facts:
                present, explanation = facts[key]
                status, evidence = ("complete" if present else "incomplete"), ("Observed: " if present else "Not observed: ") + explanation
            if key in {"traceability", "accounting"}:
                providers = {"metrc", "biotrack"} if key == "traceability" else {"quickbooks"}
                validated = {p for p, state, stamp in integrations if p in providers and state == "connected" and stamp}
                status = "complete" if validated & synced else "needs_review"
                evidence = "Validated connection and successful production synchronization observed." if status == "complete" else "No validated facility connection with successful production synchronization. Credentials alone do not verify a workflow."
            if facility and key == "storefront" and not facility.commercial_enabled:
                status, evidence = "not_applicable", "The related facility capability is disabled."
            annotation = annotations.get(key)
            if annotation and key in MANUAL_ITEMS and annotation.manual_status:
                status, evidence = annotation.manual_status, f"Manual attestation by {annotation.updated_by}: {annotation.notes}"
            items.append(dict(key=key, label=label, route=route, status=status, evidence=evidence, manual=key in MANUAL_ITEMS,
                manual_status=annotation.manual_status if annotation else None,
                notes=annotation.notes if annotation else "",
                owner_user_id=annotation.owner_user_id if annotation else None,
                owner_name=owners.get(annotation.owner_user_id) if annotation else None,
                work_item_id=annotation.work_item_id if annotation else None,
                target_date=annotation.target_date if annotation else None))
        return {"items": items, "owner_options": owner_options, "can_manage": context.role.casefold() in {"admin", "dev"}}
