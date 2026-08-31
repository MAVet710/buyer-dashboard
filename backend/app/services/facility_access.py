from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, Facility
from ..auth import RequestContext


def accessible_facility_ids(context: RequestContext, engine: Engine) -> set[str]:
    """Return facilities the authenticated application user may inspect.

    Dev/admin roles are organization-wide by existing auth policy. Assigned users
    only receive their explicit facility assignments. Development-header users that
    have no durable AppUser record fail closed to the active facility.
    """

    with Session(engine) as session:
        if context.role.casefold() in {"dev", "admin"}:
            return set(
                session.scalars(
                    select(Facility.id).where(
                        Facility.organization_id == context.organization_id,
                        Facility.active.is_(True),
                    )
                )
            )
        user = session.get(AppUser, context.user_id)
        if not user or not user.active or user.organization_id != context.organization_id:
            return {context.facility_id}
        assigned = set(
            session.scalars(
                select(AppUserFacilityRole.facility_id)
                .join(Facility, Facility.id == AppUserFacilityRole.facility_id)
                .where(
                    AppUserFacilityRole.user_id == user.id,
                    AppUserFacilityRole.organization_id == context.organization_id,
                    Facility.organization_id == context.organization_id,
                    Facility.active.is_(True),
                )
            )
        )
        assigned.add(context.facility_id)
        return assigned
