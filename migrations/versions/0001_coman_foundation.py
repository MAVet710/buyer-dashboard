"""Create the durable Co-Man foundation.

Revision ID: 0001_coman_foundation
Revises: None
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op

from modules.coman.models import Base, MachineModel

revision = "0001_coman_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        for table_name in [
            "coman_organizations",
            "coman_facilities",
            "coman_customers",
            "coman_machine_models",
            "coman_facility_machines",
            "coman_production_orders",
            "coman_audit_events",
        ]:
            op.execute(f"alter table {table_name} enable row level security")
    checked_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
    op.bulk_insert(
        MachineModel.__table__,
        [
            {
                "id": "46ea9f9f-e075-4dc4-b80d-a46769440001",
                "manufacturer": "IMA",
                "model": "C-1 FILLER",
                "category": "pre-roll filling and closing",
                "operations_json": '["cone filling", "compaction", "twisting", "vision inspection"]',
                "published_max_rate": 80.0,
                "rate_unit": "units/minute",
                "published_min_operators": None,
                "published_max_operators": None,
                "planning_utilization_pct": 65.0,
                "source_url": "https://imagroup.com/machines/c-1-filler/",
                "source_checked_at": checked_at,
                "active": True,
                "created_at": checked_at,
                "updated_at": checked_at,
            },
            {
                "id": "46ea9f9f-e075-4dc4-b80d-a46769440002",
                "manufacturer": "IMA",
                "model": "C-1 MAKER",
                "category": "pre-roll cone making",
                "operations_json": '["filter folding", "paper cutting", "cone rolling", "vision inspection"]',
                "published_max_rate": 200.0,
                "rate_unit": "cones/minute",
                "published_min_operators": None,
                "published_max_operators": None,
                "planning_utilization_pct": 65.0,
                "source_url": "https://imagroup.com/machines/c-1-maker/",
                "source_checked_at": checked_at,
                "active": True,
                "created_at": checked_at,
                "updated_at": checked_at,
            },
            {
                "id": "46ea9f9f-e075-4dc4-b80d-a46769440003",
                "manufacturer": "Massman / General Packer",
                "model": "GP-M3000",
                "category": "flower pouch packaging",
                "operations_json": '["pouch feeding", "opening", "filling", "settling", "heat sealing"]',
                "published_max_rate": 65.0,
                "rate_unit": "pouches/minute",
                "published_min_operators": 2,
                "published_max_operators": 2,
                "planning_utilization_pct": 65.0,
                "source_url": "https://massmanautomation.com/revolutionizing-cannabis-packaging-the-gp-m3000-machine/",
                "source_checked_at": checked_at,
                "active": True,
                "created_at": checked_at,
                "updated_at": checked_at,
            },
        ],
    )


def downgrade() -> None:
    for table_name in [
        "coman_audit_events",
        "coman_production_orders",
        "coman_facility_machines",
        "coman_machine_models",
        "coman_customers",
        "coman_facilities",
        "coman_organizations",
    ]:
        op.drop_table(table_name)
