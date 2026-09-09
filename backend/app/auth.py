from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, Facility
from services.trial_access import verify_trial_token

from .config import Settings, get_settings
from .database import get_engine as get_database_engine
from modules.coman.db import ComanDatabaseConfigurationError


def get_authorization_engine() -> Engine | None:
    """Reuse the application's single cached SQLAlchemy engine.

    Auth used to construct a fresh QueuePool for every authenticated request.
    On Supabase session-mode pooling that leaked idle sessions until the 15-client
    ceiling was exhausted. ``get_database_engine`` is process-cached, so all API
    dependencies now share one deliberately bounded pool per Cloud Run instance.
    """
    try:
        return get_database_engine()
    except ComanDatabaseConfigurationError:
        return None


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    organization_id: str
    facility_id: str
    role: str = "user"
    data_mode: str = "Uploads"


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


def _password_change_path_allowed(path: str, settings: Settings) -> bool:
    """Keep first-login sessions restricted to the minimum password setup surface."""
    normalized_prefix = settings.api_prefix.rstrip("/")
    return path in {
        f"{normalized_prefix}/account/context",
        f"{normalized_prefix}/account/password",
    }


def get_request_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
    organization_id: str = Header(default="", alias="X-Organization-Id"),
    facility_id: str = Header(default="", alias="X-Facility-Id"),
    development_user: str = Header(default="", alias="X-User-Id"),
    development_role: str = Header(default="", alias="X-User-Role"),
    data_mode: str = Header(default="Uploads", alias="X-DoobieLogic-Data-Mode"),
    trial_token: str = Header(default="", alias="X-Trial-Token"),
    engine: Engine | None = Depends(get_authorization_engine),
) -> RequestContext:
    normalized_data_mode = "Dutchie Live" if "dutchie" in str(data_mode or "").casefold() else "Uploads"
    if trial_token and not credentials:
        signing_secret = settings.integration_encryption_key or ("buyer-dash-development-trial" if settings.is_development else "")
        payload = verify_trial_token(trial_token, secret=signing_secret) if signing_secret else None
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Trial session is invalid or expired.")
        if engine is None:
            raise HTTPException(status_code=503, detail="Authorization database is not configured.")
        trial_org = str(payload.get("organization_id") or "")
        trial_facility = str(payload.get("facility_id") or "")
        with Session(engine) as session:
            facility = session.get(Facility, trial_facility)
            if not facility or not facility.active or facility.organization_id != trial_org:
                raise HTTPException(status_code=403, detail="Trial workspace is unavailable.")
        return RequestContext(str(payload.get("sub")), trial_org, trial_facility, "trial", normalized_data_mode)

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization and facility context are required.")
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
                if user.role == "admin":
                    role = "admin"
                else:
                    assignment = session.scalar(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == user.id, AppUserFacilityRole.organization_id == organization_id, AppUserFacilityRole.facility_id == facility_id))
                    if not assignment:
                        raise HTTPException(status_code=403, detail="This account is not assigned to the selected facility.")
                    role = assignment.role
            if user.must_change_password and not _password_change_path_allowed(request.url.path, settings):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required before using the operations API.")
            user_id = user.id
    return RequestContext(user_id, organization_id, facility_id, role, normalized_data_mode)


_CAPABILITY_FIELDS = {"retail": "retail_enabled", "production": "production_enabled", "cultivation": "cultivation_enabled", "commercial": "commercial_enabled"}


def require_any_facility_capability(context: RequestContext, engine: Engine, capabilities: tuple[str, ...]) -> None:
    if not capabilities:
        raise RuntimeError("At least one facility capability is required.")
    unknown = [capability for capability in capabilities if capability not in _CAPABILITY_FIELDS]
    if unknown:
        raise RuntimeError(f"Unknown facility capability: {unknown[0]}")
    with Session(engine) as session:
        facility = session.get(Facility, context.facility_id)
        enabled = bool(facility and facility.organization_id == context.organization_id and any(bool(getattr(facility, _CAPABILITY_FIELDS[capability])) for capability in capabilities))
    if not enabled:
        readable = " or ".join(capabilities)
        raise HTTPException(status_code=403, detail=f"The selected facility does not enable {readable} operations.")


def require_facility_capability(context: RequestContext, engine: Engine, capability: str) -> None:
    require_any_facility_capability(context, engine, (capability,))


def require_inventory_operation_capability(context: RequestContext, engine: Engine, operation: str) -> None:
    normalized = str(operation or "").strip().casefold()
    if normalized == "retail":
        require_facility_capability(context, engine, "retail")
        return
    if normalized == "production":
        require_any_facility_capability(context, engine, ("production", "cultivation"))
        return
    raise RuntimeError(f"Unknown inventory operation: {operation}")


def get_retail_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "retail")
    return context


def get_production_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "production")
    return context


def get_commercial_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_database_engine)) -> RequestContext:
    require_facility_capability(context, engine, "commercial")
    return context
