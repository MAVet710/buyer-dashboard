from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, Facility

from .config import Settings, get_settings
from .database import get_engine as get_database_engine
from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine

def get_authorization_engine(settings: Settings = Depends(get_settings)) -> Engine | None:
    try:
        return create_coman_engine(settings.database_url or None)
    except ComanDatabaseConfigurationError:
        return None


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    organization_id: str
    facility_id: str
    role: str = "user"


bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, timeout=5)


def _decode_token(token: str, settings: Settings) -> dict:
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    options = {"require": ["aud", "exp", "iss", "sub"]}
    if settings.supabase_jwks_url:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options=options,
        )
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options=options,
        )
    raise HTTPException(status_code=503, detail="API authentication is not configured.")


def get_request_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
    organization_id: str = Header(default="", alias="X-Organization-Id"),
    facility_id: str = Header(default="", alias="X-Facility-Id"),
    development_user: str = Header(default="", alias="X-User-Id"),
    development_role: str = Header(default="", alias="X-User-Role"),
    engine: Engine | None = Depends(get_authorization_engine),
) -> RequestContext:
    claims: dict = {}
    if credentials:
        if engine is None:
            raise HTTPException(status_code=503, detail="Authorization database is not configured.")
        try:
            claims = _decode_token(credentials.credentials, settings)
        except HTTPException:
            raise
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc
    elif not settings.is_development:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")

    user_id = str(claims.get("sub") or development_user or "local-developer")
    role = str(development_role or "user") if settings.is_development and not credentials else "user"
    app_metadata = claims.get("app_metadata") if isinstance(claims.get("app_metadata"), dict) else {}
    organization_id = organization_id or str(app_metadata.get("organization_id") or "")
    facility_id = facility_id or str(app_metadata.get("facility_id") or "")
    if not organization_id or not facility_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization and facility context are required.",
        )
    if credentials:
        email = str(claims.get("email") or "").strip().casefold()
        app_user_id = str(app_metadata.get("app_user_id") or user_id)
        with Session(engine) as session:
            user = session.scalar(select(AppUser).where(or_(AppUser.id == app_user_id, AppUser.email == email)))
            if not user or not user.active:
                raise HTTPException(status_code=403, detail="This account is not active in Buyer Dash.")
            facility = session.get(Facility, facility_id)
            if not facility or not facility.active or facility.organization_id != organization_id:
                raise HTTPException(status_code=403, detail="The selected facility is not available in this organization.")
            if user.role == "dev":
                role = "dev"
            else:
                if user.organization_id != organization_id:
                    raise HTTPException(status_code=403, detail="This account cannot access the selected organization.")
                assignment = session.scalar(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == user.id, AppUserFacilityRole.organization_id == organization_id, AppUserFacilityRole.facility_id == facility_id))
                if not assignment:
                    raise HTTPException(status_code=403, detail="This account is not assigned to the selected facility.")
                role = assignment.role
            user_id = user.id
    return RequestContext(user_id, organization_id, facility_id, role)


def require_facility_capability(context: RequestContext, engine: Engine, capability: str) -> None:
    fields = {
        "retail": "retail_enabled",
        "production": "production_enabled",
        "cultivation": "cultivation_enabled",
        "commercial": "commercial_enabled",
    }
    field = fields.get(capability)
    if field is None:
        raise RuntimeError(f"Unknown facility capability: {capability}")
    with Session(engine) as session:
        facility = session.get(Facility, context.facility_id)
        if not facility or facility.organization_id != context.organization_id or not bool(getattr(facility, field)):
            raise HTTPException(status_code=403, detail=f"The selected facility does not enable {capability} operations.")


def get_retail_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "retail")
    return context


def get_production_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "production")
    return context


def get_commercial_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "commercial")
    return context
