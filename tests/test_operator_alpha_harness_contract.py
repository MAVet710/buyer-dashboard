from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_real_stack_alpha_migrates_before_seeding_and_preserves_schema():
    workflow = (ROOT / ".github" / "workflows" / "web-ci.yml").read_text(encoding="utf-8")
    seed = (ROOT / "scripts" / "seed_operator_alpha.py").read_text(encoding="utf-8")

    migrate_at = workflow.index("alembic upgrade head")
    seed_at = workflow.index("python scripts/seed_operator_alpha.py")
    assert migrate_at < seed_at
    assert "rm -f operator-alpha.db" in workflow
    assert "alembic current" in workflow

    # The seed must consume the migrated schema. Recreating/deleting the DB in
    # Python would erase non-Co-Man tables and make the browser gate dishonest.
    assert "Base.metadata.create_all" not in seed
    assert "unlink(" not in seed
    assert "_verify_migrated_schema" in seed
    for table in (
        "integration_configurations",
        "action_proposals",
        "traceability_transactions",
        "material_transformations",
        "lot_quality_evidence",
    ):
        assert table in seed
