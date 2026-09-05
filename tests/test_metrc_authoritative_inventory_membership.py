from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization
from services.metrc_authoritative_inventory_membership import MetrcAuthoritativeInventoryMembershipReconciler
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _tenant(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Metrc Membership Test", slug="metrc-membership-test", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Membership Facility",
            code="MEM",
            license_number="LIC-MEM",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _package(label: str, quantity: float):
    return {
        "provider": "metrc",
        "jurisdiction_code": "MA",
        "resource": "packages_active",
        "provider_id": label.removeprefix("PKG-"),
        "label": label,
        "quantity": quantity,
        "unit_of_measure": "Grams",
        "source": {
            "Id": label.removeprefix("PKG-"),
            "Label": label,
            "ItemId": 41,
            "ItemName": "GMO Bulk Flower",
            "ItemCategoryName": "Buds",
            "Quantity": quantity,
            "UnitOfMeasureName": "Grams",
            "LocationName": "Vault A",
            "LabTestingState": "TestPassed",
        },
    }


def _seed(engine, organization_id, facility_id, packages):
    return MetrcCanonicalInventorySeeder(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-MEM",
        actor="tester",
        packages=packages,
    )


def _balance(session, lot_id: str) -> float:
    return float(
        session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot_id
            )
        )
        or 0.0
    )


def test_complete_active_snapshot_closes_linked_package_that_is_no_longer_active():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    pkg_a = _package("PKG-200", 100.0)
    pkg_b = _package("PKG-201", 50.0)
    _seed(engine, organization_id, facility_id, [pkg_a, pkg_b])

    result = MetrcAuthoritativeInventoryMembershipReconciler(engine).reconcile_absent(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-MEM",
        actor="tester",
        current_packages=[pkg_a],
    )

    assert result["complete_active_snapshot"] is True
    assert result["current_provider_package_count"] == 1
    assert result["linked_package_count"] == 2
    assert result["absent_linked_package_count"] == 1
    assert result["closed_balance_count"] == 1
    assert result["status_update_count"] == 1
    assert result["incremental_absence_inference"] is False

    with Session(engine) as session:
        lots = {row.lot_code: row for row in session.scalars(select(InventoryLot))}
        assert _balance(session, lots["PKG-200"].id) == 100.0
        assert _balance(session, lots["PKG-201"].id) == 0.0
        assert lots["PKG-200"].status == "available"
        assert lots["PKG-201"].status == "inactive"
        corrections = list(
            session.scalars(
                select(InventoryTransaction).where(
                    InventoryTransaction.transaction_type == "metrc_authoritative_absence_reconciliation"
                )
            )
        )
        assert len(corrections) == 1
        assert corrections[0].quantity_delta == -50.0


def test_complete_membership_reconciliation_is_idempotent():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    pkg = _package("PKG-202", 25.0)
    _seed(engine, organization_id, facility_id, [pkg])
    service = MetrcAuthoritativeInventoryMembershipReconciler(engine)

    first = service.reconcile_absent(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-MEM",
        actor="tester",
        current_packages=[],
    )
    second = service.reconcile_absent(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-MEM",
        actor="tester",
        current_packages=[],
    )

    assert first["closed_balance_count"] == 1
    assert second["closed_balance_count"] == 0
    assert second["status_update_count"] == 0
    assert second["unchanged_absent_count"] == 1
    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        assert lot is not None
        assert _balance(session, lot.id) == 0.0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 2


def test_natural_full_bootstrap_is_the_only_layer_that_invokes_absence_inference():
    natural = (ROOT / "services" / "metrc_natural_bootstrap.py").read_text(encoding="utf-8")
    incremental = (ROOT / "services" / "metrc_incremental_sync.py").read_text(encoding="utf-8")

    assert "MetrcAuthoritativeInventoryMembershipReconciler" in natural
    assert 'if "packages" in current_resources:' in natural
    assert "reconcile_absent(" in natural
    assert "complete_snapshot_only" in natural
    assert "MetrcAuthoritativeInventoryMembershipReconciler" not in incremental
    assert "reconcile_absent(" not in incremental
