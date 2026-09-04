from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.metrc_runtime_composition import compose_metrc_runtime
from backend.app.routers import inventory_reconciliation
from backend.app.routers.metrc_package_lab_detail import _lab_resource, cached_package_lab_results
from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from modules.traceability.object_links import TraceabilityObjectLinkRepository


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Package Lab Detail", slug="package-lab-detail", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Lab Facility",
            code="MP281234",
            license_number="MP281234",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=organization.id,
            sku="LAB-FLOWER",
            name="GMO Flower",
            item_type="cannabis",
            base_unit="g",
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="1A4FF0100000000000000999",
            compliance_package_id="1A4FF0100000000000000999",
            location_code="VAULT",
            status="available",
        )
        session.add(lot)
        session.flush()
        return engine, organization.id, facility.id, lot.id


def test_package_lab_detail_returns_only_exact_package_cached_evidence():
    engine, organization_id, facility_id, lot_id = _fixture()
    links = TraceabilityObjectLinkRepository(engine)
    links.upsert_verified(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction="MA",
        environment="sandbox",
        license_number="MP281234",
        entity_type="inventory_lot",
        entity_id=lot_id,
        provider_resource="packages",
        provider_id="991",
        provider_label="1A4FF0100000000000000999",
    )
    snapshots = IntegrationProviderSnapshotRepository(engine)
    snapshots.replace(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        environment="sandbox",
        resource=_lab_resource("991"),
        run_id="package-991",
        records=[{"Id": 1, "TestTypeName": "THC", "TestResultLevel": 22.1}],
    )
    # Evidence for another package must never leak into this package's panel.
    snapshots.replace(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        environment="sandbox",
        resource=_lab_resource("992"),
        run_id="package-992",
        records=[{"Id": 2, "TestTypeName": "CBD", "TestResultLevel": 9.9}],
    )

    result = cached_package_lab_results(
        lot_id,
        environment="sandbox",
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )

    assert result["linked"] is True
    assert result["network_request_made"] is False
    assert result["provider_package_id"] == "991"
    assert result["provider_package_label"] == "1A4FF0100000000000000999"
    assert result["result_count"] == 1
    assert result["results"] == [{"Id": 1, "TestTypeName": "THC", "TestResultLevel": 22.1}]


def test_package_lab_detail_routes_are_registered_by_late_runtime_composition():
    compose_metrc_runtime()
    paths = {str(getattr(route, "path", "")) for route in inventory_reconciliation.router.routes}
    assert "/regulatory-detail/local/inventory_lot/{entity_id}/lab-results" in paths
    assert "/regulatory-detail/local/inventory_lot/{entity_id}/lab-results/live" in paths
