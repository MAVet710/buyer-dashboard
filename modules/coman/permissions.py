from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, TimestampMixin, new_id


class AppUserPermissionOverride(TimestampMixin, Base):
    """Explicit facility-scoped permission override layered on top of role defaults."""

    __tablename__ = "app_user_permission_overrides"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            "facility_id",
            "permission",
            name="uq_app_user_permission_scope",
        ),
        CheckConstraint("effect in ('allow', 'deny')", name="ck_app_user_permission_effect"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    effect: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
