"""Add versioned legal policies and append-only acceptance events.

Revision ID: 0013_legal_acceptance
Revises: 0012_inventory_audits
"""

from alembic import op

from modules.coman.models import LegalAcceptanceEvent, LegalPolicyVersion

revision = "0013_legal_acceptance"
down_revision = "0012_inventory_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for model in (LegalPolicyVersion, LegalAcceptanceEvent):
        model.__table__.create(bind=bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {model.__tablename__} enable row level security")


def downgrade() -> None:
    op.drop_table("legal_acceptance_events")
    op.drop_table("legal_policy_versions")


