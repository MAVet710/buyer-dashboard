from pathlib import Path
import re


MIGRATIONS = Path("migrations/versions")
REVISION_RE = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
LEGACY_OVERSIZED_REVISIONS = {
    "0011_commercial_order_fulfillment",
}


def test_alembic_revision_ids_fit_deployed_version_column_except_documented_legacy():
    revisions: list[tuple[Path, str]] = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        match = REVISION_RE.search(path.read_text(encoding="utf-8"))
        if match:
            revisions.append((path, match.group(1)))

    assert revisions
    oversized = {revision for _, revision in revisions if len(revision) > 32}
    assert oversized == LEGACY_OVERSIZED_REVISIONS, (
        "Unexpected Alembic revision IDs exceed varchar(32): "
        f"{sorted(oversized - LEGACY_OVERSIZED_REVISIONS)}"
    )

    values = [revision for _, revision in revisions]
    assert len(values) == len(set(values)), "Alembic revision IDs must be unique"


def test_new_0019_revision_fits_deployed_version_column():
    source = (MIGRATIONS / "0019_package_studio_production_order_index.py").read_text(encoding="utf-8")
    match = REVISION_RE.search(source)
    assert match
    assert match.group(1) == "0019_pkgstudio_po_index"
    assert len(match.group(1)) <= 32


def test_0019_standalone_sql_matches_short_revision_id():
    source = (MIGRATIONS / "0019_package_studio_production_order_index.sql").read_text(encoding="utf-8")
    assert "0019_pkgstudio_po_index" in source
    assert "0019_package_studio_production_order_index'" not in source
