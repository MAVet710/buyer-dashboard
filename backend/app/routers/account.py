from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, Facility, Organization
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/account", tags=["account"])

@router.get("/context")
def account_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        user = session.get(AppUser, context.user_id)
        if context.role == "dev":
            facilities = list(session.scalars(select(Facility).where(Facility.organization_id == context.organization_id, Facility.active.is_(True)).order_by(Facility.name)))
        else:
            facilities = list(session.scalars(select(Facility).join(AppUserFacilityRole, AppUserFacilityRole.facility_id == Facility.id).where(AppUserFacilityRole.user_id == context.user_id, AppUserFacilityRole.organization_id == context.organization_id, Facility.active.is_(True)).order_by(Facility.name)))
        active_facility = session.get(Facility, context.facility_id)
        capabilities = {
            "retail": bool(active_facility and active_facility.retail_enabled),
            "production": bool(active_facility and active_facility.production_enabled),
            "cultivation": bool(active_facility and active_facility.cultivation_enabled),
            "commercial": bool(active_facility and active_facility.commercial_enabled),
        }
        return {"user": {"id": context.user_id, "display_name": user.display_name if user else context.user_id, "email": user.email if user else "", "role": context.role}, "organization": {"id": organization.id, "name": organization.name} if organization else None, "facility_id": context.facility_id, "facility": {"id": active_facility.id, "name": active_facility.name, "code": active_facility.code, "license_number": active_facility.license_number, "license_type": active_facility.license_type} if active_facility else None, "capabilities": capabilities, "facilities": [{"id": row.id, "name": row.name, "code": row.code, "timezone_name": row.timezone_name, "capabilities": {"retail": row.retail_enabled, "production": row.production_enabled, "cultivation": row.cultivation_enabled, "commercial": row.commercial_enabled}} for row in facilities]}
