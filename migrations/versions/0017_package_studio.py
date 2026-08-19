"""Add durable Package Studio transformation lineage.

Revision ID: 0017_package_studio
Revises: 0016_durable_data_hub_imports
"""

from alembic import op

from modules.package_studio.models import PackageStudioInput, PackageStudioOutput, PackageStudioRun

revision = "0017_package_studio"
down_revision = "0016_durable_data_hub_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    PackageStudioRun.__table__.create(bind=bind, checkfirst=True)
    PackageStudioInput.__table__.create(bind=bind, checkfirst=True)
    PackageStudioOutput.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table package_studio_runs enable row level security")
        op.execute("alter table package_studio_inputs enable row level security")
        op.execute("alter table package_studio_outputs enable row level security")


def downgrade() -> None:
    op.drop_table("package_studio_outputs")
    op.drop_table("package_studio_inputs")
    op.drop_table("package_studio_runs")
