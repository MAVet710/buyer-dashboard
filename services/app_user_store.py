"""Durable application users backed by the Co-Man PostgreSQL database."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import AppUser, AppUserFacilityRole, Facility


VALID_ROLES = {"admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only"}
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
        return self.role == "admin"


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
