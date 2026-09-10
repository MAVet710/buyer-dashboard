"""Expose real MA COA METRC source tags as DEV-only inventory scan aliases.

Revision ID: 0077_dev_reference_metrc_tags
Revises: 0076_global_traceability_ledger

This migration deliberately does not replace ``compliance_package_id``.  Real
tracking identifiers sourced from public Massachusetts COAs are external
reference identities used only inside the DEV Sandbox for scan/search testing.
The synthetic DEV package remains the current local package identity and no
provider write is implied by this alias.
"""

from alembic import op

revision = "0077_dev_reference_metrc_tags"
down_revision = "0076_global_traceability_ledger"
branch_labels = None
depends_on = None


_TRIGGER = "trg_dev_sandbox_reference_metrc_tag"
_FUNCTION = "sync_dev_sandbox_reference_metrc_tag"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            source_tag text;
            sample_tag text;
        BEGIN
            SELECT btrim(d.metrc_source_id), btrim(coalesce(d.metrc_lab_id, ''))
              INTO source_tag, sample_tag
              FROM coa_documents d
              JOIN coman_inventory_lots l ON l.id = NEW.lot_id
              JOIN coman_facilities f ON f.id = l.facility_id
              JOIN coman_organizations o ON o.id = l.organization_id
             WHERE d.id = NEW.coa_document_id
               AND NEW.evidence_source = 'coa:dev_ma_external_reference'
               AND d.verification_state = 'external_reference'
               AND o.slug = 'dev-sandbox'
               AND f.code = 'SANDBOX'
               AND l.organization_id = NEW.organization_id
               AND l.facility_id = NEW.facility_id
             LIMIT 1;

            IF coalesce(source_tag, '') = '' THEN
                RETURN NEW;
            END IF;

            UPDATE coman_inventory_lots l
               SET external_inventory_id = source_tag,
                   barcode_value = source_tag,
                   notes = (
                       CASE
                           WHEN coalesce(btrim(l.notes), '') = '' THEN '{{}}'::jsonb
                           WHEN l.notes ~ '^\\s*\\{{' THEN l.notes::jsonb
                           ELSE jsonb_build_object('legacy_note', l.notes)
                       END
                       || jsonb_build_object(
                           'reference_metrc_tag', source_tag,
                           'reference_metrc_sample_tag', coalesce(sample_tag, ''),
                           'reference_metrc_identity', 'external_reference_only',
                           'reference_metrc_scan_enabled', true,
                           'reference_metrc_notice',
                               'DEV Sandbox scan alias only; not the current regulatory package identity and never valid for provider writes.'
                       )
                   )::text,
                   updated_at = now()
             WHERE l.id = NEW.lot_id;

            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON lot_quality_evidence")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        AFTER INSERT OR UPDATE OF evidence_source, coa_document_id
        ON lot_quality_evidence
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION}()
        """
    )

    # Backfill the currently seeded DEV Sandbox. This intentionally touches only
    # the exact DEV tenant/facility and only COAs already classified as external
    # Massachusetts reference evidence.
    op.execute(
        """
        UPDATE coman_inventory_lots l
           SET external_inventory_id = btrim(d.metrc_source_id),
               barcode_value = btrim(d.metrc_source_id),
               notes = (
                   CASE
                       WHEN coalesce(btrim(l.notes), '') = '' THEN '{}'::jsonb
                       WHEN l.notes ~ '^\\s*\\{' THEN l.notes::jsonb
                       ELSE jsonb_build_object('legacy_note', l.notes)
                   END
                   || jsonb_build_object(
                       'reference_metrc_tag', btrim(d.metrc_source_id),
                       'reference_metrc_sample_tag', btrim(coalesce(d.metrc_lab_id, '')),
                       'reference_metrc_identity', 'external_reference_only',
                       'reference_metrc_scan_enabled', true,
                       'reference_metrc_notice',
                           'DEV Sandbox scan alias only; not the current regulatory package identity and never valid for provider writes.'
                   )
               )::text,
               updated_at = now()
          FROM lot_quality_evidence q
          JOIN coa_documents d ON d.id = q.coa_document_id
          JOIN coman_facilities f ON f.id = q.facility_id
          JOIN coman_organizations o ON o.id = q.organization_id
         WHERE l.id = q.lot_id
           AND l.organization_id = q.organization_id
           AND l.facility_id = q.facility_id
           AND q.evidence_source = 'coa:dev_ma_external_reference'
           AND d.verification_state = 'external_reference'
           AND coalesce(btrim(d.metrc_source_id), '') <> ''
           AND o.slug = 'dev-sandbox'
           AND f.code = 'SANDBOX'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON lot_quality_evidence")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")

    # Remove only aliases created by this migration. The synthetic local
    # compliance package identity is never modified by upgrade or downgrade.
    op.execute(
        """
        UPDATE coman_inventory_lots l
           SET external_inventory_id = CASE
                   WHEN l.external_inventory_id = (l.notes::jsonb ->> 'reference_metrc_tag') THEN ''
                   ELSE l.external_inventory_id
               END,
               barcode_value = CASE
                   WHEN l.barcode_value = (l.notes::jsonb ->> 'reference_metrc_tag') THEN ''
                   ELSE l.barcode_value
               END,
               notes = (
                   l.notes::jsonb
                   - 'reference_metrc_tag'
                   - 'reference_metrc_sample_tag'
                   - 'reference_metrc_identity'
                   - 'reference_metrc_scan_enabled'
                   - 'reference_metrc_notice'
               )::text,
               updated_at = now()
          FROM coman_facilities f, coman_organizations o
         WHERE f.id = l.facility_id
           AND o.id = l.organization_id
           AND o.slug = 'dev-sandbox'
           AND f.code = 'SANDBOX'
           AND l.notes::jsonb ->> 'reference_metrc_identity' = 'external_reference_only'
        """
    )
