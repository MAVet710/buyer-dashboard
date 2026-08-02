"""Durable, append-only legal policy acceptance storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import LegalAcceptanceEvent, LegalPolicyVersion


VALID_METHODS = {"first_login", "policy_update", "organization_activation"}
VALID_ENVIRONMENTS = {"production", "trial", "sandbox"}


@dataclass(frozen=True)
class PolicyDocument:
    policy_type: str
    version: str
    effective_at: datetime
    document_sha256: str
    document_url: str = ""
    requires_reacceptance: bool = True


@dataclass(frozen=True)
class AcceptanceRecord:
    id: str
    user_id: str
    organization_id: str | None
    terms_version: str
    privacy_version: str
    statement_version: str
    acceptance_method: str
    environment: str
    accepted_at: datetime


class LegalAcceptanceStore:
    def __init__(self, database_url: str | None = None, engine: Engine | None = None):
        self._engine = engine
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

    def available(self) -> bool:
        """Return whether the acceptance table is present and queryable."""

        if not self._session_factory:
            return False
        try:
            with self._session_factory() as session:
                session.execute(select(LegalAcceptanceEvent.id).limit(1))
            return True
        except SQLAlchemyError:
            return False

    def has_accepted(
        self,
        *,
        user_id: str,
        terms_version: str,
        privacy_version: str,
    ) -> bool:
        if not self._session_factory or not user_id:
            return False
        try:
            with self._session_factory() as session:
                event_id = session.scalar(
                    select(LegalAcceptanceEvent.id).where(
                        LegalAcceptanceEvent.user_id == user_id,
                        LegalAcceptanceEvent.terms_version == terms_version,
                        LegalAcceptanceEvent.privacy_version == privacy_version,
                    )
                )
                return event_id is not None
        except SQLAlchemyError:
            return False

    def record_acceptance(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        terms: PolicyDocument,
        privacy: PolicyDocument,
        statement_version: str,
        acceptance_method: str = "first_login",
        environment: str = "production",
        ip_address: str = "",
        user_agent: str = "",
    ) -> AcceptanceRecord:
        if not self._session_factory:
            raise RuntimeError("The legal acceptance database is not configured.")
        if not user_id:
            raise ValueError("A durable user ID is required.")
        if terms.policy_type != "terms" or privacy.policy_type != "privacy":
            raise ValueError("Terms and privacy policy documents are required.")
        if acceptance_method not in VALID_METHODS:
            raise ValueError("Invalid acceptance method.")
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError("Invalid application environment.")

        try:
            with self._session_factory.begin() as session:
                self._ensure_policy(session, terms)
                self._ensure_policy(session, privacy)
                existing = session.scalar(
                    select(LegalAcceptanceEvent).where(
                        LegalAcceptanceEvent.user_id == user_id,
                        LegalAcceptanceEvent.terms_version == terms.version,
                        LegalAcceptanceEvent.privacy_version == privacy.version,
                    )
                )
                if existing is not None:
                    return self._record(existing)
                event = LegalAcceptanceEvent(
                    user_id=user_id,
                    organization_id=organization_id,
                    terms_version=terms.version,
                    privacy_version=privacy.version,
                    statement_version=str(statement_version or "").strip(),
                    acceptance_method=acceptance_method,
                    environment=environment,
                    accepted_at=datetime.now(timezone.utc),
                    ip_address=str(ip_address or "")[:64],
                    user_agent=str(user_agent or "")[:4096],
                    created_by_user_id=user_id,
                )
                session.add(event)
                session.flush()
                return self._record(event)
        except IntegrityError:
            if self.has_accepted(
                user_id=user_id,
                terms_version=terms.version,
                privacy_version=privacy.version,
            ):
                return self.get_acceptance(
                    user_id=user_id,
                    terms_version=terms.version,
                    privacy_version=privacy.version,
                )
            raise

    def get_acceptance(
        self,
        *,
        user_id: str,
        terms_version: str,
        privacy_version: str,
    ) -> AcceptanceRecord:
        if not self._session_factory:
            raise RuntimeError("The legal acceptance database is not configured.")
        with self._session_factory() as session:
            event = session.scalar(
                select(LegalAcceptanceEvent).where(
                    LegalAcceptanceEvent.user_id == user_id,
                    LegalAcceptanceEvent.terms_version == terms_version,
                    LegalAcceptanceEvent.privacy_version == privacy_version,
                )
            )
            if event is None:
                raise ValueError("The acceptance event was not found.")
            return self._record(event)

    @staticmethod
    def _ensure_policy(session, policy: PolicyDocument) -> None:
        existing = session.scalar(
            select(LegalPolicyVersion).where(
                LegalPolicyVersion.policy_type == policy.policy_type,
                LegalPolicyVersion.version == policy.version,
            )
        )
        if existing is not None:
            if existing.document_sha256 != policy.document_sha256:
                raise ValueError("A published policy version cannot be changed in place.")
            return
        session.add(
            LegalPolicyVersion(
                policy_type=policy.policy_type,
                version=policy.version,
                effective_at=policy.effective_at,
                document_url=policy.document_url,
                document_sha256=policy.document_sha256,
                requires_reacceptance=policy.requires_reacceptance,
            )
        )

    @staticmethod
    def _record(event: LegalAcceptanceEvent) -> AcceptanceRecord:
        return AcceptanceRecord(
            id=event.id,
            user_id=event.user_id,
            organization_id=event.organization_id,
            terms_version=event.terms_version,
            privacy_version=event.privacy_version,
            statement_version=event.statement_version,
            acceptance_method=event.acceptance_method,
            environment=event.environment,
            accepted_at=event.accepted_at,
        )

