from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_authoritative_inventory import MetrcAuthoritativeInventoryReconciler
from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


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
        organization = Organization(name="Metrc Authority Test", slug="metrc-authority-test", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Authority Facility",
            code="AUTH",
            license_number="LIC-AUTH",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _package(
    label: str,
    quantity: float,
    *,
    item_id: int = 41,
    item_name: str = "GMO Bulk Flower",
    unit: str = "Grams",
    location: str = "Vault A",
    lab_state: str = "TestPassed",
):
    return {
        "provider": "metrc",
        "jurisdiction_code": "MA",
        "resource": "packages_active",
        "provider_id": label.removeprefix("PKG-"),
        "label": label,
        "name": item_name,
        "status": lab_state,
        "quantity": quantity,
        "unit_of_measure": unit,
        "source": {
            "Id": label.removeprefix("PKG-"),
            "Label": label,
            "ItemId": item_id,
            "ItemName": item_name,
            "ItemCategoryName": "Buds",
            "Quantity": quantity,
            "UnitOfMeasureName": unit,
            "LocationName": location,
            "LabTestingState": lab_state,
        },
    }


def _seed(engine, organization_id, facility_id, package):
    return MetrcCanonicalInventorySeeder(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[package],
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


def test_reconciler_appends_delta_and_updates_regulated_package_state_without_overwriting_enrichment():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    _seed(engine, organization_id, facility_id, _package("PKG-100", 100.0))

    with Session(engine) as session, session.begin():
        product = session.scalar(select(Product))
        assert product is not None
        product.name = "Local Planning Name"
        product.unit_cost = 8.75
        product.retail_price = 42.00

    result = MetrcAuthoritativeInventoryReconciler(engine).reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[
            _package(
                "PKG-100",
                75.0,
                location="Vault B",
                lab_state="TestingInProgress",
            )
        ],
    )

    assert result["authoritative_provider"] == "metrc"
    assert result["matched_package_count"] == 1
    assert result["quantity_reconciliations"] == 1
    assert result["location_updates"] == 1
    assert result["status_updates"] == 1
    assert result["conflict_count"] == 0
    assert result["ledger_strategy"] == "append_only_delta_to_provider_truth"
    assert result["local_enrichment_preserved"] is True

    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        product = session.scalar(select(Product))
        assert lot is not None and product is not None
        assert _balance(session, lot.id) == 75.0
        transactions = list(session.scalars(select(InventoryTransaction).order_by(InventoryTransaction.occurred_at)))
        assert len(transactions) == 2
        assert transactions[-1].transaction_type == "metrc_authoritative_reconciliation"
        assert transactions[-1].quantity_delta == -25.0
        assert lot.location_code == "Vault B"
        assert lot.status == "hold"
        assert product.name == "Local Planning Name"
        assert product.unit_cost == 8.75
        assert product.retail_price == 42.00
        links = list(session.scalars(select(TraceabilityObjectLink)))
        assert {(row.provider_resource, row.provider_id) for row in links} == {("items", "41"), ("packages", "100")}
        assert all(row.status == "verified" for row in links)


def test_reconciliation_is_idempotent_for_same_provider_state():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    _seed(engine, organization_id, facility_id, _package("PKG-101", 100.0))
    changed = _package("PKG-101", 60.0, location="Vault B")
    service = MetrcAuthoritativeInventoryReconciler(engine)

    first = service.reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[changed],
    )
    second = service.reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[changed],
    )

    assert first["quantity_reconciliations"] == 1
    assert second["quantity_reconciliations"] == 0
    assert second["location_updates"] == 0
    assert second["unchanged_package_count"] == 1
    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        assert lot is not None
        assert _balance(session, lot.id) == 60.0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 2


def test_unit_mismatch_fails_closed_without_guessing_conversion():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    _seed(engine, organization_id, facility_id, _package("PKG-102", 100.0, unit="Grams"))

    result = MetrcAuthoritativeInventoryReconciler(engine).reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[_package("PKG-102", 3.0, unit="Ounces", location="Vault C")],
    )

    assert result["quantity_reconciliations"] == 0
    assert any(row["code"] == "package_unit_mismatch" for row in result["conflicts"])
    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        assert lot is not None
        assert _balance(session, lot.id) == 100.0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1


def test_unlinked_package_is_never_matched_by_mutable_label_or_name():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    _seed(engine, organization_id, facility_id, _package("PKG-103", 50.0))

    impostor = _package("PKG-103", 10.0)
    impostor["provider_id"] = "DIFFERENT-PROVIDER-ID"
    impostor["source"]["Id"] = "DIFFERENT-PROVIDER-ID"
    result = MetrcAuthoritativeInventoryReconciler(engine).reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        packages=[impostor],
    )

    assert result["matched_package_count"] == 0
    assert any(row["code"] == "unlinked_package" for row in result["conflicts"])
    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        assert lot is not None
        assert _balance(session, lot.id) == 50.0


def test_natural_workspace_hydration_keeps_existing_inventory_equal_to_latest_metrc_quantity():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    hydrator = MetrcWorkspaceHydrationService(engine)

    first = hydrator.hydrate(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        resource_snapshots={"packages": [_package("PKG-104", 100.0)]},
    )
    assert first["workspaces"]["inventory"]["authority"] == "metrc"
    assert first["workspaces"]["inventory"]["regulated_state_authoritative"] is True
    assert first["workspaces"]["inventory"]["authoritative_reconciliation"]["quantity_reconciliations"] == 0

    second = hydrator.hydrate(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-AUTH",
        actor="tester",
        resource_snapshots={"packages": [_package("PKG-104", 70.0, location="Vault D")]},
    )
    reconciliation = second["workspaces"]["inventory"]["authoritative_reconciliation"]
    assert reconciliation["quantity_reconciliations"] == 1
    assert reconciliation["location_updates"] == 1

    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot))
        assert lot is not None
        assert _balance(session, lot.id) == 70.0
        assert lot.location_code == "Vault D"
