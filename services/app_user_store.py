"""Durable application users backed by the Co-Man PostgreSQL database."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import AppUser, AppUserFacilityRole, Facility, Organization


VALID_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,120}$")


def normalize_username(username: str | None) -> str:
    return str(username or "").strip().casefold()


@dataclass(frozen=True)
class AppUserRecord:
    id: str
    organization_id: str | None
    username: str
    normalized_username: str
    display_name: str
    email: str
    password_hash: str
    role: str
    active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime | None

    @property
    def is_admin(self) -> bool:
        return self.role in {"dev", "admin"}

    @property
    def is_dev(self) -> bool:
        return self.role == "dev"


@dataclass(frozen=True)
class OrganizationRecord:
    id: str
    name: str
    slug: str
    active: bool


@dataclass(frozen=True)
class FacilityRecord:
    id: str
    organization_id: str
    name: str
    code: str
    timezone_name: str
    active: bool


class AppUserStore:
    def __init__(self, database_url: str | None = None, engine: Engine | None = None):
        self._engine: Engine | None = engine
        if self._engine is None:
            try:
                self._engine = create_coman_engine(database_url)
            except ComanDatabaseConfigurationError:
                self._engine = None
        self._session_factory = (
            sessionmaker(bind=self._engine, expire_on_commit=False, future=True)
            if self._engine is not None
            else None
        )

    @property
    def configured(self) -> bool:
        return self._session_factory is not None

    def health_check(self) -> bool:
        """Return whether the configured database can answer a minimal query."""
        if not self._session_factory:
            return False
        try:
            with self._session_factory() as session:
                session.execute(select(1))
            return True
        except SQLAlchemyError:
            return False

    def get_user(self, username: str) -> AppUserRecord | None:
        if not self._session_factory:
            return None
        normalized = normalize_username(username)
        if not normalized:
            return None
        try:
            with self._session_factory() as session:
                user = session.scalar(
                    select(AppUser).where(AppUser.normalized_username == normalized)
                )
                return self._record(user) if user else None
        except SQLAlchemyError:
            return None

    def list_users(self, organization_id: str | None = None) -> list[AppUserRecord]:
        if not self._session_factory:
            return []
        try:
            with self._session_factory() as session:
                statement = select(AppUser)
                if organization_id:
                    statement = statement.where(AppUser.organization_id == organization_id)
                users = session.scalars(statement.order_by(AppUser.username)).all()
                return [self._record(user) for user in users]
        except SQLAlchemyError:
            return []

    def list_organizations(self, *, active_only: bool = True) -> list[OrganizationRecord]:
        if not self._session_factory:
            return []
        try:
            with self._session_factory() as session:
                statement = select(Organization)
                if active_only:
                    statement = statement.where(Organization.active.is_(True))
                organizations = session.scalars(statement.order_by(Organization.name)).all()
                return [self._organization_record(item) for item in organizations]
        except SQLAlchemyError:
            return []

    def list_facilities(
        self,
        organization_id: str,
        *,
        user_id: str | None = None,
        active_only: bool = True,
    ) -> list[FacilityRecord]:
        if not self._session_factory or not organization_id:
            return []
        try:
            with self._session_factory() as session:
                statement = select(Facility).where(Facility.organization_id == organization_id)
                if user_id:
                    statement = statement.join(
                        AppUserFacilityRole,
                        AppUserFacilityRole.facility_id == Facility.id,
                    ).where(AppUserFacilityRole.user_id == user_id)
                if active_only:
                    statement = statement.where(Facility.active.is_(True))
                facilities = session.scalars(statement.order_by(Facility.name)).all()
                return [self._facility_record(item) for item in facilities]
        except SQLAlchemyError:
            return []

    def create_organization(self, *, name: str, slug: str) -> OrganizationRecord:
        if not self._session_factory:
            raise RuntimeError("The application user database is not configured.")
        clean_name = str(name or "").strip()
        clean_slug = re.sub(r"[^a-z0-9-]+", "-", str(slug or "").strip().casefold()).strip("-")
        if not clean_name or not clean_slug:
            raise ValueError("Organization name and slug are required.")
        organization = Organization(name=clean_name, slug=clean_slug, active=True)
        with self._session_factory.begin() as session:
            existing = session.scalar(select(Organization.id).where(Organization.slug == clean_slug))
            if existing:
                raise ValueError("That organization slug already exists.")
            session.add(organization)
        return self._organization_record(organization)

    def create_facility(
        self,
        *,
        organization_id: str,
        name: str,
        code: str,
        timezone_name: str = "America/New_York",
    ) -> FacilityRecord:
        if not self._session_factory:
            raise RuntimeError("The application user database is not configured.")
        clean_name = str(name or "").strip()
        clean_code = str(code or "").strip().upper()
        if not organization_id or not clean_name or not clean_code:
            raise ValueError("Organization, facility name, and code are required.")
        facility = Facility(
            organization_id=organization_id,
            name=clean_name,
            code=clean_code,
            timezone_name=str(timezone_name or "America/New_York").strip(),
            active=True,
        )
        with self._session_factory.begin() as session:
            if not session.get(Organization, organization_id):
                raise ValueError("Organization was not found.")
            existing = session.scalar(
                select(Facility.id).where(
                    Facility.organization_id == organization_id,
                    Facility.code == clean_code,
                )
            )
            if existing:
                raise ValueError("That facility code already exists in the organization.")
            session.add(facility)
        return self._facility_record(facility)

    def ensure_dev_sandbox(self) -> tuple[OrganizationRecord, FacilityRecord]:
        """Return the isolated platform sandbox, creating it once when needed."""
        if not self._session_factory:
            raise RuntimeError("The application user database is not configured.")
        with self._session_factory.begin() as session:
            organization = session.scalar(
                select(Organization).where(Organization.slug == "dev-sandbox")
            )
            if organization is None:
                organization = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
                session.add(organization)
                session.flush()
            facility = session.scalar(
                select(Facility).where(
                    Facility.organization_id == organization.id,
                    Facility.code == "SANDBOX",
                )
            )
            if facility is None:
                facility = Facility(
                    organization_id=organization.id,
                    name="Sandbox Facility",
                    code="SANDBOX",
                    timezone_name="America/New_York",
                    active=True,
                )
                session.add(facility)
                session.flush()
        return self._organization_record(organization), self._facility_record(facility)

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        created_by: str,
        organization_id: str | None = None,
        display_name: str = "",
        email: str = "",
        facility_ids: list[str] | None = None,
        must_change_password: bool = True,
    ) -> AppUserRecord:
        if not self._session_factory:
            raise RuntimeError("The application user database is not configured.")
        clean_username = str(username or "").strip()
        normalized = normalize_username(clean_username)
        clean_role = str(role or "").strip().casefold()
        if not USERNAME_PATTERN.fullmatch(clean_username):
            raise ValueError("Username must be 3-120 characters using letters, numbers, ., _, or -.")
        if clean_role not in VALID_ROLES:
            raise ValueError("Invalid user role.")
        if clean_role == "dev" and organization_id:
            raise ValueError("DEV accounts must remain platform-wide and cannot belong to one organization.")
        if not str(password_hash).startswith(("$2a$", "$2b$", "$2y$")):
            raise ValueError("A bcrypt password hash is required.")
        if facility_ids and not organization_id:
            raise ValueError("Facility assignments require an organization.")

        user = AppUser(
            organization_id=organization_id,
            username=clean_username,
            normalized_username=normalized,
            display_name=str(display_name or "").strip(),
            email=str(email or "").strip().casefold(),
            password_hash=password_hash,
            role=clean_role,
            active=True,
            must_change_password=bool(must_change_password),
            created_by=str(created_by or "system"),
            updated_by=str(created_by or "system"),
        )
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(AppUser.id).where(AppUser.normalized_username == normalized)
            )
            if existing:
                raise ValueError("That username already exists.")
            session.add(user)
            session.flush()
            for facility_id in sorted(set(facility_ids or [])):
                facility = session.get(Facility, facility_id)
                if not facility or facility.organization_id != organization_id:
                    raise ValueError("A selected facility does not belong to the organization.")
                session.add(
                    AppUserFacilityRole(
                        user_id=user.id,
                        organization_id=str(organization_id),
                        facility_id=facility_id,
                        role=clean_role,
                    )
                )
        return self._record(user)

    def ensure_legacy_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        created_by: str = "legacy-secrets-bootstrap",
    ) -> AppUserRecord | None:
        existing = self.get_user(username)
        if existing:
            return existing
        try:
            return self.create_user(
                username=username,
                password_hash=password_hash,
                role=role,
                created_by=created_by,
                must_change_password=False,
            )
        except (RuntimeError, ValueError, SQLAlchemyError):
            return None

    def set_active(self, user_id: str, active: bool, updated_by: str) -> bool:
        if not self._session_factory:
            return False
        try:
            with self._session_factory.begin() as session:
                user = session.get(AppUser, user_id)
                if not user:
                    return False
                user.active = bool(active)
                user.updated_by = updated_by
            return True
        except SQLAlchemyError:
            return False

    def reset_password(self, user_id: str, password_hash: str, updated_by: str) -> bool:
        if not self._session_factory:
            return False
        if not str(password_hash).startswith(("$2a$", "$2b$", "$2y$")):
            raise ValueError("A bcrypt password hash is required.")
        try:
            with self._session_factory.begin() as session:
                user = session.get(AppUser, user_id)
                if not user:
                    return False
                user.password_hash = password_hash
                user.password_changed_at = datetime.now(timezone.utc)
                user.must_change_password = True
                user.updated_by = updated_by
            return True
        except SQLAlchemyError:
            return False

    def change_password(self, user_id: str, password_hash: str) -> bool:
        """Change an active user's password and complete the first-login flow."""
        if not self._session_factory:
            return False
        if not str(password_hash).startswith(("$2a$", "$2b$", "$2y$")):
            raise ValueError("A bcrypt password hash is required.")
        try:
            with self._session_factory.begin() as session:
                user = session.get(AppUser, user_id)
                if not user or not user.active:
                    return False
                user.password_hash = password_hash
                user.password_changed_at = datetime.now(timezone.utc)
                user.must_change_password = False
                user.updated_by = user.username
            return True
        except SQLAlchemyError:
            return False

    def record_login(self, user_id: str) -> None:
        if not self._session_factory:
            return
        try:
            with self._session_factory.begin() as session:
                user = session.get(AppUser, user_id)
                if user:
                    user.last_login_at = datetime.now(timezone.utc)
        except SQLAlchemyError:
            return

    @staticmethod
    def _record(user: AppUser) -> AppUserRecord:
        return AppUserRecord(
            id=user.id,
            organization_id=user.organization_id,
            username=user.username,
            normalized_username=user.normalized_username,
            display_name=user.display_name,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            active=bool(user.active),
            must_change_password=bool(user.must_change_password),
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )

    @staticmethod
    def _organization_record(organization: Organization) -> OrganizationRecord:
        return OrganizationRecord(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            active=bool(organization.active),
        )

    @staticmethod
    def _facility_record(facility: Facility) -> FacilityRecord:
        return FacilityRecord(
            id=facility.id,
            organization_id=facility.organization_id,
            name=facility.name,
            code=facility.code,
            timezone_name=facility.timezone_name,
            active=bool(facility.active),
        )
