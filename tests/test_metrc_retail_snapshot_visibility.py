from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.metrc_retail_snapshot import retail_regulatory_snapshot_from_sync
from modules.coman.models import Base, Facility, Organization, RetailSale
from modules.regulatory.service import RegulatoryMappingService
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


ROOT = Path(__file__).resolve().parents[1]


def _facility():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Retail Snapshot", slug="retail-snapshot", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Retail Facility",
            code="MR281234",
            license_number="MR281234",
            retail_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def _complete(service, organization_id: str, facility_id: str, resource: str, records: list[dict]):
    service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource=resource,
        environment="sandbox",
        actor="admin",
        result={"ok": True, "http_status": 200, "records": records, "page_count": 1, "truncated": False},
        transport="test",
    )


def test_retail_snapshot_surfaces_provider_sales_records_without_fabricating_pos_sales():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MR281234",
        provider_facility_id="metrc-retail-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    _complete(
        service,
        organization_id,
        facility_id,
        "sales_receipts",
        [{
            "provider_id": "receipt-1",
            "status": "Active",
            "source": {"Id": 101, "ReceiptNumber": "R-1001", "Status": "Active", "SalesDateTime": "2026-09-04T10:00:00"},
        }],
    )
    _complete(
        service,
        organization_id,
        facility_id,
        "sales_deliveries",
        [{
            "provider_id": "delivery-1",
            "status": "Active",
            "source": {"Id": 201, "DeliveryNumber": "D-1001", "Status": "Active", "DeliveryDateTime": "2026-09-04T11:00:00"},
        }],
    )

    result = retail_regulatory_snapshot_from_sync(
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )

    assert result["configured"] is True
    assert result["ready"] is True
    assert result["network_request_made"] is False
    assert result["source"] == "integration_provider_snapshots"
    assert result["summary"] == {"active_sales_receipt_count": 1, "active_sales_delivery_count": 1}
    assert result["resources"]["sales_receipts"]["records"][0]["receipt_number"] == "R-1001"
    assert result["resources"]["sales_deliveries"]["records"][0]["delivery_number"] == "D-1001"

    with Session(engine) as session:
        assert list(session.scalars(select(RetailSale))) == []


def test_retail_frontend_loads_provider_shadow_separately_from_local_sql_sales_ledger():
    page = (ROOT / "frontend/src/pages/RetailInsightsPage.tsx").read_text(encoding="utf-8")
    component = (ROOT / "frontend/src/components/RetailRegulatoryState.tsx").read_text(encoding="utf-8")

    assert "<RetailRegulatoryState />" in page
    assert "/api/v1/retail-insights/regulatory-snapshot" in component
    assert "no Metrc request on page load" in component
    assert "do not fabricate local POS sales" in component
    assert "SQL sales ledger" in page
