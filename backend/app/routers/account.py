from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, AuditEvent, Facility, Organization, utc_now
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/account", tags=["account"])


def _facility_payload(row: Facility) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "timezone_name": row.timezone_name,
        "license_number": row.license_number,
        "license_type": row.license_type,
        "capabilities": {
            "retail": row.retail_enabled,
            "production": row.production_enabled,
            "cultivation": row.cultivation_enabled,
            "commercial": row.commercial_enabled,
        },
    }


def _facilities_for_user(session: Session, context: RequestContext, organization_id: str) -> list[Facility]:
    if context.role in {"dev", "admin"}:
        return list(
            session.scalars(
                select(Facility)
                .where(Facility.organization_id == organization_id, Facility.active.is_(True))
                .order_by(Facility.name)
            )
        )
    return list(
        session.scalars(
            select(Facility)
            .join(AppUserFacilityRole, AppUserFacilityRole.facility_id == Facility.id)
            .where(
                AppUserFacilityRole.user_id == context.user_id,
                AppUserFacilityRole.organization_id == organization_id,
                Facility.active.is_(True),
            )
            .order_by(Facility.name)
        )
    )


@router.get("/context")
def account_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        user = session.get(AppUser, context.user_id)
        facilities = _facilities_for_user(session, context, context.organization_id)
        active_facility = session.get(Facility, context.facility_id)
        capabilities = {
            "retail": bool(active_facility and active_facility.retail_enabled),
            "production": bool(active_facility and active_facility.production_enabled),
            "cultivation": bool(active_facility and active_facility.cultivation_enabled),
            "commercial": bool(active_facility and active_facility.commercial_enabled),
        }
        return {
            "user": {
                "id": context.user_id,
                "display_name": user.display_name if user else context.user_id,
                "email": user.email if user else "",
                "role": context.role,
                "must_change_password": bool(user and user.must_change_password),
            },
            "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug} if organization else None,
            "facility_id": context.facility_id,
            "facility": _facility_payload(active_facility) if active_facility else None,
            "capabilities": capabilities,
            "facilities": [_facility_payload(row) for row in facilities],
        }


@router.get("/access-options")
def access_options(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    """Return every organization/facility context the current account may open.

    Streamlit exposed organization and facility context as first-class operational
    state. The web client must preserve that behavior rather than pinning DEV or
    admin users to the organization embedded in their first JWT.
    """
    with Session(engine) as session:
        if context.role == "dev":
            organizations = list(session.scalars(select(Organization).where(Organization.active.is_(True)).order_by(Organization.name)))
        else:
            organization = session.get(Organization, context.organization_id)
            organizations = [organization] if organization and organization.active else []
        payload = []
        for organization in organizations:
            facilities = _facilities_for_user(session, context, organization.id)
            payload.append(
                {
                    "id": organization.id,
                    "name": organization.name,
                    "slug": organization.slug,
                    "facilities": [_facility_payload(row) for row in facilities],
                }
            )
        return {"organizations": payload, "organization_id": context.organization_id, "facility_id": context.facility_id}


@router.post("/password-changed")
def password_changed(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    """Clear the durable first-login password-change requirement after Supabase succeeds."""
    with Session(engine) as session, session.begin():
        user = session.get(AppUser, context.user_id)
        if user:
            user.must_change_password = False
            user.password_changed_at = utc_now()
            user.updated_by = context.user_id
            session.add(
                AuditEvent(
                    organization_id=context.organization_id,
                    facility_id=context.facility_id,
                    entity_type="app_user",
                    entity_id=context.user_id,
                    action="password_changed",
                    actor=context.user_id,
                    changes_json='{"must_change_password": false}',
                )
            )
    return {"ok": True}
