"""Add post-harvest workflow and append-only trim weight history.

Revision ID: 0067_post_harvest_workflow
Revises: 0066_metrc_guide_v11_alignment
"""

import sqlalchemy as sa
from alembic import op

revision = "0067_post_harvest_workflow"
down_revision = "0066_metrc_guide_v11_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cultivation_post_harvest_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("harvest_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("location_code", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage in ('harvested','drying','bucking','trimming','curing','testing_hold','ready')",
            name="ck_cultivation_post_harvest_stage",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["harvest_id"], ["cultivation_harvests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("harvest_id", name="uq_cultivation_post_harvest_harvest"),
    )
    op.create_index(
        "ix_cultivation_post_harvest_facility_stage",
        "cultivation_post_harvest_batches",
        ["facility_id", "stage"],
        unique=False,
    )
    op.create_index(op.f("ix_cultivation_post_harvest_batches_organization_id"), "cultivation_post_harvest_batches", ["organization_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_batches_facility_id"), "cultivation_post_harvest_batches", ["facility_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_batches_harvest_id"), "cultivation_post_harvest_batches", ["harvest_id"], unique=False)

    op.create_table(
        "cultivation_post_harvest_weight_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("weight_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_g", sa.Float(), nullable=False),
        sa.Column("container_code", sa.String(length=120), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("correction_reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "weight_type in ('wip','finished_flower','trim','biomass','waste')",
            name="ck_cultivation_post_harvest_weight_type",
        ),
        sa.CheckConstraint("quantity_g >= 0", name="ck_cultivation_post_harvest_weight_nonnegative"),
        sa.ForeignKeyConstraint(["batch_id"], ["cultivation_post_harvest_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cultivation_post_harvest_weight_batch_time",
        "cultivation_post_harvest_weight_events",
        ["batch_id", "occurred_at"],
        unique=False,
    )
    op.create_index(op.f("ix_cultivation_post_harvest_weight_events_organization_id"), "cultivation_post_harvest_weight_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_weight_events_facility_id"), "cultivation_post_harvest_weight_events", ["facility_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_weight_events_batch_id"), "cultivation_post_harvest_weight_events", ["batch_id"], unique=False)

    op.create_table(
        "cultivation_post_harvest_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_value", sa.String(length=255), nullable=False),
        sa.Column("to_value", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["cultivation_post_harvest_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cultivation_post_harvest_event_batch_time",
        "cultivation_post_harvest_events",
        ["batch_id", "occurred_at"],
        unique=False,
    )
    op.create_index(op.f("ix_cultivation_post_harvest_events_organization_id"), "cultivation_post_harvest_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_events_facility_id"), "cultivation_post_harvest_events", ["facility_id"], unique=False)
    op.create_index(op.f("ix_cultivation_post_harvest_events_batch_id"), "cultivation_post_harvest_events", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cultivation_post_harvest_events_batch_id"), table_name="cultivation_post_harvest_events")
    op.drop_index(op.f("ix_cultivation_post_harvest_events_facility_id"), table_name="cultivation_post_harvest_events")
    op.drop_index(op.f("ix_cultivation_post_harvest_events_organization_id"), table_name="cultivation_post_harvest_events")
    op.drop_index("ix_cultivation_post_harvest_event_batch_time", table_name="cultivation_post_harvest_events")
    op.drop_table("cultivation_post_harvest_events")

    op.drop_index(op.f("ix_cultivation_post_harvest_weight_events_batch_id"), table_name="cultivation_post_harvest_weight_events")
    op.drop_index(op.f("ix_cultivation_post_harvest_weight_events_facility_id"), table_name="cultivation_post_harvest_weight_events")
    op.drop_index(op.f("ix_cultivation_post_harvest_weight_events_organization_id"), table_name="cultivation_post_harvest_weight_events")
    op.drop_index("ix_cultivation_post_harvest_weight_batch_time", table_name="cultivation_post_harvest_weight_events")
    op.drop_table("cultivation_post_harvest_weight_events")

    op.drop_index(op.f("ix_cultivation_post_harvest_batches_harvest_id"), table_name="cultivation_post_harvest_batches")
    op.drop_index(op.f("ix_cultivation_post_harvest_batches_facility_id"), table_name="cultivation_post_harvest_batches")
    op.drop_index(op.f("ix_cultivation_post_harvest_batches_organization_id"), table_name="cultivation_post_harvest_batches")
    op.drop_index("ix_cultivation_post_harvest_facility_stage", table_name="cultivation_post_harvest_batches")
    op.drop_table("cultivation_post_harvest_batches")
