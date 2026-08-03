"""Expand the common production-machine reference library.

Revision ID: 0014_machine_reference_library
Revises: 0013_legal_acceptance
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op

revision = "0014_machine_reference_library"
down_revision = "0013_legal_acceptance"
branch_labels = None
depends_on = None


ROWS = (
    ("46ea9f9f-e075-4dc4-b80d-a46769440020", "GreenBroz", "Model G Precision Batch Grinder", "cannabis grinding and destemming", '["destemming","grinding","sifting"]', 100, "pounds/hour", 1, 2, 65, "https://www.greenbroz.com/automation/rise-n-grind"),
    ("46ea9f9f-e075-4dc4-b80d-a46769440021", "STM Canna", "RocketBox 2.0", "batch pre-roll cone filling", '["cone loading","flower filling","compaction"]', 2500, "pre-rolls/hour", 1, 2, 65, "https://stmcanna.com/rocketbox-2-0-commercial-preroll-machine-joint-roller/"),
    ("46ea9f9f-e075-4dc4-b80d-a46769440022", "STM Canna", "RocketBox Pro", "continuous pre-roll cone filling", '["multi-station filling","compaction","tray handling"]', 5000, "pre-rolls/hour", 2, 4, 60, "https://stmcanna.com/automated-commercial-pre-roll-machines/"),
    ("46ea9f9f-e075-4dc4-b80d-a46769440023", "RollPros", "Blackbird", "automatic joint rolling", '["paper feed","flower dosing","joint rolling"]', 900, "pre-rolls/hour", 1, 2, 70, "https://rollpros.com/blackbird/"),
    ("46ea9f9f-e075-4dc4-b80d-a46769440024", "Sorting Robotics", "Stardust", "infused pre-roll coating", '["adhesive application","kief coating","infused pre-roll finishing"]', 1500, "pre-rolls/hour", 1, 2, 65, "https://www.sortingrobotics.com/the-grind-blog/how-to-improve-efficiency-in-pre-roll-production"),
)


def upgrade() -> None:
    checked_at = datetime(2026, 8, 2, tzinfo=timezone.utc)
    for row in ROWS:
        (
            machine_id,
            manufacturer,
            model,
            category,
            operations_json,
            rate,
            rate_unit,
            min_ops,
            max_ops,
            utilization,
            source_url,
        ) = row
        op.execute(
            """
            insert into coman_machine_models
                (id, manufacturer, model, category, operations_json,
                 published_max_rate, rate_unit, published_min_operators,
                 published_max_operators, planning_utilization_pct, source_url,
                 source_checked_at, active, created_at, updated_at)
            values
                (:id, :manufacturer, :model, :category, :operations_json,
                 :rate, :rate_unit, :min_ops, :max_ops, :utilization, :source_url,
                 :checked_at, true, :checked_at, :checked_at)
            on conflict (manufacturer, model) do update set
                category = excluded.category,
                operations_json = excluded.operations_json,
                published_max_rate = excluded.published_max_rate,
                rate_unit = excluded.rate_unit,
                published_min_operators = excluded.published_min_operators,
                published_max_operators = excluded.published_max_operators,
                planning_utilization_pct = excluded.planning_utilization_pct,
                source_url = excluded.source_url,
                source_checked_at = excluded.source_checked_at,
                active = true,
                updated_at = excluded.updated_at
            """,
            {
                "id": machine_id,
                "manufacturer": manufacturer,
                "model": model,
                "category": category,
                "operations_json": operations_json,
                "rate": rate,
                "rate_unit": rate_unit,
                "min_ops": min_ops,
                "max_ops": max_ops,
                "utilization": utilization,
                "source_url": source_url,
                "checked_at": checked_at,
            },
        )


def downgrade() -> None:
    ids = ", ".join(f"'{row[0]}'" for row in ROWS)
    op.execute(f"delete from coman_machine_models where id in ({ids})")
