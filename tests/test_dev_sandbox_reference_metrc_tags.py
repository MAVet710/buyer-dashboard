from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0077_dev_sandbox_reference_metrc_tags.py"


def test_reference_tag_migration_is_dev_only_and_preserves_compliance_identity():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0077_dev_reference_metrc_tags"' in source
    assert 'down_revision = "0076_global_traceability_ledger"' in source
    assert "o.slug = 'dev-sandbox'" in source
    assert "f.code = 'SANDBOX'" in source
    assert "q.evidence_source = 'coa:dev_ma_external_reference'" in source
    assert "d.verification_state = 'external_reference'" in source

    # The external source tag is a DEV scan alias only. The current local
    # compliance package identity must never be rewritten to a real external tag.
    assert "external_inventory_id = btrim(d.metrc_source_id)" in source
    assert "barcode_value = btrim(d.metrc_source_id)" in source
    assert "reference_metrc_identity', 'external_reference_only'" in source
    assert "reference_metrc_scan_enabled', true" in source
    assert "SET compliance_package_id" not in source
    assert "compliance_package_id =" not in source


def test_reference_tag_migration_keeps_provider_write_boundary_explicit():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "not the current regulatory package identity" in source
    assert "never valid for provider writes" in source
    assert "AFTER INSERT OR UPDATE OF evidence_source, coa_document_id" in source
    assert "coalesce(btrim(d.metrc_source_id), '') <> ''" in source
