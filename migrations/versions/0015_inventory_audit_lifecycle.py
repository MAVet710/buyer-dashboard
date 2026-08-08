"""Allow resumable and stoppable inventory-audit sessions.

Revision ID: 0015_inventory_audit_lifecycle
Revises: 0014_machine_reference_library
"""

from alembic import op

revision = "0015_inventory_audit_lifecycle"
down_revision = "0014_machine_reference_library"
branch_labels = None
depends_on = None


NEW_CHECK = "status in ('draft', 'in_progress', 'paused', 'stopped', 'completed', 'cancelled')"
OLD_CHECK = "status in ('draft', 'in_progress', 'completed', 'cancelled')"


def _replace_status_check(expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_inventory_audit_status", "inventory_audits", type_="check")
        op.create_check_constraint("ck_inventory_audit_status", "inventory_audits", expression)
        return

    # SQLite and other batch-migration dialects need the table recreated to
    # change a CHECK constraint safely.
    with op.batch_alter_table("inventory_audits", recreate="always") as batch:
        batch.drop_constraint("ck_inventory_audit_status", type_="check")
        batch.create_check_constraint("ck_inventory_audit_status", expression)


def upgrade() -> None:
    _replace_status_check(NEW_CHECK)


def downgrade() -> None:
    # Existing paused/stopped rows cannot satisfy the old constraint. Preserve
    # the audit record by translating them to in_progress before downgrade.
    op.execute("update inventory_audits set status = 'in_progress' where status in ('paused', 'stopped')")
    _replace_status_check(OLD_CHECK)
