from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.services.transfer_control_provider_shadow import ProviderAwareTransferControlService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.integrations import IntegrationConfigurationService, SandboxIntegrationRuntime
from modules.integrations.models import IntegrationProviderSnapshot
from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from modules.product_master.models import ProductMasterProfile
from modules.traceability.object_links import TraceabilityObjectLink


ENCRYPTION_KEY = "natural-metrc-workspace-test-encryption-key"


def _runtime():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-natural", name="Natural Sandbox", slug="natural-sandbox"))
        session.add(
            Facility(
                id="fac-natural",
                organization_id="org-natural",
                name="Sandbox Medical Marijuana Facility",
                code="NATURAL",
                license_number="SAN-MA-001",
                license_type="Marijuana Product Manufacturer",
                retail_enabled=True,
                production_enabled=True,
                cultivation_enabled=True,
                commercial_enabled=True,
            )
        )
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    service.save(
        scope_type="facility",
        scope_key="org-natural:fac-natural:sandbox",
        provider="metrc_sandbox",
        organization_id="org-natural",
        facility_id="fac-natural",
        configuration={"environment": "sandbox", "state": "MA", "license_number": ""},
        secret="sandbox-integrator-key",
        actor="developer",
    )
    return engine


def test_successful_metrc_sandbox_sync_materializes_items_packages_and_keeps_transfers_provider_owned():
    engine = _runtime()
    runtime = SandboxIntegrationRuntime(engine, ENCRYPTION_KEY)

    first = runtime.sync(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc",
        actor="developer",
    )

    hydration = first["workspace_hydration"]
    assert hydration["automatic"] is True
    assert hydration["materialized_workspaces"] == ["inventory", "product_master"]
    assert hydration["provider_shadow_workspaces"] == ["transfer_control"]
    assert hydration["workspaces"]["product_master"]["created_products"] == 3
    assert hydration["workspaces"]["inventory"]["created_inventory_lots"] == 3
    assert hydration["workspaces"]["inventory"]["created_inventory_transactions"] == 3
    assert hydration["workspaces"]["transfer_control"]["source_transfer_count"] == 2
    assert first["current_snapshot"]["network_request_required_for_workspace_reads"] is False
    assert first["current_snapshot"]["resources"]["items"]["present"] == 3
    assert first["current_snapshot"]["resources"]["packages"]["present"] == 3
    assert first["current_snapshot"]["resources"]["transfers"]["present"] == 2

    with Session(engine) as session:
        products = list(session.scalars(select(Product).where(Product.organization_id == "org-natural")))
        profiles = list(session.scalars(select(ProductMasterProfile).where(ProductMasterProfile.organization_id == "org-natural")))
        lots = list(session.scalars(select(InventoryLot).where(InventoryLot.facility_id == "fac-natural")))
        transactions = list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.facility_id == "fac-natural")))
        links = list(session.scalars(select(TraceabilityObjectLink).where(TraceabilityObjectLink.facility_id == "fac-natural")))
        current = list(session.scalars(select(IntegrationProviderSnapshot).where(
            IntegrationProviderSnapshot.facility_id == "fac-natural",
            IntegrationProviderSnapshot.present.is_(True),
        )))

    assert {product.name for product in products} == {"Sandbox Flower", "Sandbox Distillate", "Sandbox Live Resin"}
    assert len(profiles) == 3
    assert len(lots) == 3
    assert sorted(round(transaction.quantity_delta, 3) for transaction in transactions) == [210.0, 420.0, 1250.0]
    assert all(lot.status == "available" for lot in lots)
    assert len([link for link in links if link.provider_resource == "items"]) == 3
    assert len([link for link in links if link.provider_resource == "packages"]) == 3
    assert all(link.license_number == "SAN-MA-001" for link in links)
    assert len(current) == 8

    second = runtime.sync(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc",
        actor="developer",
    )
    assert second["workspace_hydration"]["workspaces"]["product_master"]["created_products"] == 0
    assert second["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_lots"] == 0
    assert second["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_transactions"] == 0
    assert second["current_snapshot"]["resources"]["transfers"]["updated"] == 2

    with Session(engine) as session:
        assert len(list(session.scalars(select(Product).where(Product.organization_id == "org-natural")))) == 3
        assert len(list(session.scalars(select(InventoryLot).where(InventoryLot.facility_id == "fac-natural")))) == 3
        assert len(list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.facility_id == "fac-natural")))) == 3
        assert len(list(session.scalars(select(IntegrationProviderSnapshot).where(
            IntegrationProviderSnapshot.facility_id == "fac-natural",
            IntegrationProviderSnapshot.present.is_(True),
        )))) == 8


def test_transfer_control_naturally_surfaces_current_synced_metrc_transfers_without_fabricating_workflow_rows():
    engine = _runtime()
    SandboxIntegrationRuntime(engine, ENCRYPTION_KEY).sync(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc",
        actor="developer",
    )

    snapshot = ProviderAwareTransferControlService(engine).snapshot("org-natural", "fac-natural")

    assert snapshot["provider_synced"] == {
        "count": 2,
        "open": 2,
        "rejected": 0,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
    }
    assert snapshot["metrics"]["provider_in_flight"] == 2
    assert len(snapshot["outgoing"]) == 1
    assert len(snapshot["inbound"]) == 1
    assert snapshot["outgoing"][0]["provider_synced"] is True
    assert snapshot["inbound"][0]["provider_synced"] is True
    assert snapshot["outgoing"][0]["proposal_status"] == "provider_synced"
    assert snapshot["inbound"][0]["operation"] == "provider_sync"
    assert snapshot["outgoing"][0]["proposal_id"].startswith("provider-shadow:")
    assert snapshot["inbound"][0]["preflight_id"].startswith("provider-shadow:")
    assert snapshot["inbound"][0]["environment"] == "sandbox"


def test_complete_provider_snapshot_removes_rows_that_are_no_longer_present():
    engine = _runtime()
    runtime = SandboxIntegrationRuntime(engine, ENCRYPTION_KEY)
    runtime.sync(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc",
        actor="developer",
    )

    repository = IntegrationProviderSnapshotRepository(engine)
    repository.replace(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc_sandbox",
        environment="sandbox",
        resource="transfers",
        run_id="replacement-run",
        records=[
            {
                "id": "METRC-XFER-ONLY",
                "manifest_number": "MAN-ONLY",
                "direction": "incoming",
                "status": "Scheduled",
            }
        ],
    )

    current = repository.current(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc_sandbox",
        resources=("transfers",),
        environment="sandbox",
    )
    assert len(current) == 1
    assert current[0].external_id == "METRC-XFER-ONLY"

    snapshot = ProviderAwareTransferControlService(engine).snapshot("org-natural", "fac-natural")
    assert snapshot["provider_synced"]["count"] == 1
    assert len(snapshot["inbound"]) == 1
    assert len(snapshot["outgoing"]) == 0


def test_rejected_provider_transfer_routes_to_exception_queue_and_preserves_snapshot_environment():
    engine = _runtime()
    repository = IntegrationProviderSnapshotRepository(engine)
    repository.replace(
        organization_id="org-natural",
        facility_id="fac-natural",
        provider="metrc",
        environment="sandbox",
        resource="rejected_transfers",
        run_id="rejected-run",
        records=[
            {
                "Id": 9001,
                "ManifestNumber": "MAN-REJECTED",
                "Status": "Rejected",
                "RejectionReason": "Recipient license could not accept the transfer.",
                "RecipientFacilityName": "Example Retail",
                "RecipientFacilityLicenseNumber": "MR281111",
            }
        ],
    )

    snapshot = ProviderAwareTransferControlService(engine).snapshot("org-natural", "fac-natural")

    assert snapshot["provider_synced"]["count"] == 1
    assert snapshot["provider_synced"]["rejected"] == 1
    assert snapshot["provider_synced"]["open"] == 0
    assert snapshot["outgoing"] == []
    assert snapshot["inbound"] == []
    assert snapshot["metrics"]["exceptions"] == 1
    assert len(snapshot["exceptions"]) == 1
    exception = snapshot["exceptions"][0]
    assert exception["kind"] == "provider_rejected"
    assert exception["reference"] == "MAN-REJECTED"
    assert exception["environment"] == "sandbox"
    assert "Recipient license" in exception["message"]
