"""Expand the commercial Co-Man machine reference library.

Revision ID: 0007_machine_reference_library
Revises: 0006_crew_availability
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op

from modules.coman.models import MachineModel

revision = "0007_machine_reference_library"
down_revision = "0006_crew_availability"
branch_labels = None
depends_on = None


MACHINE_IDS = [f"46ea9f9f-e075-4dc4-b80d-a467694400{number}" for number in range(10, 18)]


def _row(index, manufacturer, model, category, operations, rate, rate_unit, utilization, source, min_ops=None, max_ops=None):
    checked_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return {
        "id": MACHINE_IDS[index], "manufacturer": manufacturer, "model": model,
        "category": category, "operations_json": operations,
        "published_max_rate": rate, "rate_unit": rate_unit,
        "published_min_operators": min_ops, "published_max_operators": max_ops,
        "planning_utilization_pct": utilization, "source_url": source,
        "source_checked_at": checked_at, "active": True,
        "created_at": checked_at, "updated_at": checked_at,
    }


def upgrade() -> None:
    op.bulk_insert(MachineModel.__table__, [
        _row(0, "Ishida", "ATLAS 114C-ECO + SE Weigher", "flexible pouch and pre-roll pack packaging", '["weighing","film forming","product feeding","bag sealing"]', 100, "packages/minute", 60, "https://www.ishida.com/eu/en/products/documents/upload/FIRST-RANGE-BROCHURE-ENG.pdf"),
        _row(1, "Ishida", "ASTRO-S-103 + SE Weigher", "flexible pouch and pre-roll pack packaging", '["weighing","film forming","product feeding","bag sealing"]', 85, "packages/minute", 60, "https://www.ishida.com/eu/en/products/documents/upload/FIRST-RANGE-BROCHURE-ENG.pdf"),
        _row(2, "Vape-Jet", "Vape-Jet 4.0", "automatic vape cartridge and device filling", '["oil heating","machine-vision alignment","precision filling","run data capture"]', 1200, "devices/hour", 70, "https://vape-jet.com/faq/", 1, 1),
        _row(3, "Vape-Jet", "Jet Fueler 3.0", "semi-automatic vape cartridge and device filling", '["oil heating","foot-pedal dispensing","precision filling"]', 1125, "devices/hour", 65, "https://vape-jet.com/category/events/", 1, 1),
        _row(4, "Futurola", "Knockbox 3/100", "batch pre-roll cone filling", '["cone loading","flower filling","vibration compaction"]', 3000, "pre-rolls/hour", 55, "https://futurola.com/blogs/news/guide-picking-right-futurola-knockbox-model", 1, 2),
        _row(5, "Futurola", "Knockbox 3/300", "high-volume batch pre-roll cone filling", '["cone loading","flower filling","vibration compaction"]', 9000, "pre-rolls/hour", 50, "https://futurola.com/blogs/news/guide-picking-right-futurola-knockbox-model", 1, 2),
        _row(6, "Thompson Duke Industrial", "IZR", "automatic vape cartridge and device filling", '["tray handling","extract heating","automatic filling","diagnostics"]', 1800, "devices/hour", 65, "https://thompsondukeindustrial.com/izr/"),
        _row(7, "Thompson Duke Industrial", "Big JIM", "automatic pre-roll infusion and device filling", '["joint infusion","extract heating","cartridge filling","rapid formula changeover"]', 600, "infused pre-rolls/hour", 65, "https://thompsondukeindustrial.com/jim/"),
    ])


def downgrade() -> None:
    ids = ", ".join(f"'{machine_id}'" for machine_id in MACHINE_IDS)
    op.execute(f"delete from coman_machine_models where id in ({ids})")

