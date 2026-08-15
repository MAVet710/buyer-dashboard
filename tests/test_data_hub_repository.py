from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base, Facility, Organization
from modules.data_hub_repository import DataHubRepository, hydrate_durable_sources


@pytest.fixture()
def repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'data-hub.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Organization.__table__.insert(),
            [
                {"id": "org-a", "name": "A", "slug": "a", "active": True},
                {"id": "org-b", "name": "B", "slug": "b", "active": True},
            ],
        )
        connection.execute(
            Facility.__table__.insert(),
            [
                {
                    "id": "facility-a",
                    "organization_id": "org-a",
                    "name": "A Retail",
                    "code": "AR",
                    "timezone_name": "America/New_York",
                    "active": True,
                },
                {
                    "id": "facility-b",
                    "organization_id": "org-b",
                    "name": "B Retail",
                    "code": "BR",
                    "timezone_name": "America/New_York",
                    "active": True,
                },
            ],
        )
    return DataHubRepository(engine)


def _publish(repository, *, organization_id="org-a", facility_id="facility-a", payload=b"a"):
    return repository.publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key="inventory",
        dataset_label="Inventory",
        cache_key="_cache_inv",
        filename="inventory.csv",
        fingerprint=hashlib.sha256(payload).hexdigest(),
        payload=payload,
        inspection={"rows": 1, "columns": 2, "quality": "Ready"},
        imported_by="buyer@example.com",
    )


def test_publish_and_restore_survives_a_fresh_session(repository):
    record = _publish(repository, payload=b"Product,On Hand\nBlue Dream,12\n")

    state = {}
    restored = hydrate_durable_sources(
        state,
        repository,
        organization_id="org-a",
        facility_id="facility-a",
        cache_keys=("_cache_inv", "_cache_sales"),
    )

    assert restored == 1
    assert state["_cache_inv"]["bytes"].startswith(b"Product")
    assert state["_cache_inv"]["durable_id"] == record.id
    assert state["_cache_inv"]["durable"] is True


def test_active_sources_are_tenant_and_facility_isolated(repository):
    _publish(repository, payload=b"tenant-a")
    _publish(
        repository,
        organization_id="org-b",
        facility_id="facility-b",
        payload=b"tenant-b",
    )

    assert repository.list_active_sources("org-a", "facility-a")[0].payload == b"tenant-a"
    assert repository.list_active_sources("org-b", "facility-b")[0].payload == b"tenant-b"

    state = {"_cache_inv": {"bytes": b"tenant-a"}, "_durable_data_hub_scope": "org-a|facility-a"}
    hydrate_durable_sources(
        state,
        repository,
        organization_id="org-b",
        facility_id="facility-b",
        cache_keys=("_cache_inv",),
    )
    assert state["_cache_inv"]["bytes"] == b"tenant-b"


def test_republishing_is_idempotent_and_new_version_archives_previous(repository):
    first = _publish(repository, payload=b"first")
    duplicate = _publish(repository, payload=b"first")
    second = _publish(repository, payload=b"second")

    history = repository.list_history("org-a", "facility-a")
    assert duplicate.id == first.id
    assert len(history) == 2
    assert {item.status for item in history} == {"active", "archived"}
    assert repository.list_active_sources("org-a", "facility-a")[0].id == second.id


def test_retention_caps_stored_versions(repository):
    for index in range(6):
        repository.publish_source(
            organization_id="org-a",
            facility_id="facility-a",
            dataset_key="inventory",
            dataset_label="Inventory",
            cache_key="_cache_inv",
            filename=f"inventory-{index}.csv",
            fingerprint=hashlib.sha256(str(index).encode()).hexdigest(),
            payload=str(index).encode(),
            retain_versions=3,
        )
    assert len(repository.list_history("org-a", "facility-a")) == 3


def test_facility_must_belong_to_selected_organization(repository):
    with pytest.raises(ValueError, match="does not belong"):
        _publish(repository, organization_id="org-a", facility_id="facility-b")


def test_manual_migration_enables_rls_and_advances_revision():
    sql = open(
        "migrations/versions/0016_durable_data_hub_imports.sql",
        encoding="utf-8",
    ).read().lower()
    assert "enable row level security" in sql
    assert "0016_durable_data_hub_imports" in sql
    assert "organization_id" in sql and "facility_id" in sql
