from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product, utc_now
from modules.integrations.models import IntegrationProviderSnapshot, IntegrationSyncState
from services import metrc_facility_bootstrap as bootstrap_module
from services.metrc_incremental_sync import MetrcIncrementalSyncService


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-delta", name="Delta", slug="delta"))
        session.add(
            Facility(
                id="fac-delta",
                organization_id="org-delta",
                name="Delta Facility",
                code="DELTA",
                license_number="MP281234",
                production_enabled=True,
                cultivation_enabled=True,
                retail_enabled=True,
                commercial_enabled=True,
            )
        )
    return engine


def _baseline(engine, resource: str, when=None):
    when = when or utc_now()
    with Session(engine) as session, session.begin():
        session.add(
            IntegrationSyncState(
                organization_id="org-delta",
                facility_id="fac-delta",
                provider="metrc",
                resource=resource,
                environment="sandbox",
                cursor="initial-full",
                status="succeeded",
                last_started_at=when,
                last_completed_at=when,
                last_success_at=when,
                records_seen=1,
                records_written=1,
                updated_by="tester",
            )
        )
    return when


def _payload(resource: str, rows: list[dict]):
    normalized=[]
    for row in rows:
        normalized.append({
            "provider":"metrc",
            "jurisdiction_code":"MA",
            "resource":resource,
            "provider_id":str(row.get("Id") or ""),
            "label":str(row.get("Label") or ""),
            "name":str(row.get("Name") or row.get("ItemName") or ""),
            "status":str(row.get("Status") or row.get("LabTestingState") or ""),
            "quantity":row.get("Quantity"),
            "unit_of_measure":str(row.get("UnitOfMeasureName") or ""),
            "last_modified":str(row.get("LastModified") or ""),
            "source":dict(row),
        })
    return {"ok":True,"http_status":200,"payload":{"Data":rows,"TotalPages":1},"records":normalized}


def test_incremental_delta_uses_five_minute_overlap_and_never_marks_omitted_rows_absent(monkeypatch):
    engine=_engine()
    baseline=_baseline(engine,"locations")
    now=utc_now()
    with Session(engine) as session, session.begin():
        for external_id in ("LOC-KEEP","LOC-CHANGED"):
            raw={"Id":external_id,"Name":external_id}
            session.add(IntegrationProviderSnapshot(
                organization_id="org-delta",facility_id="fac-delta",provider="metrc",environment="sandbox",
                resource="locations",external_id=external_id,provider_label=external_id,fingerprint=external_id.ljust(64,"x")[:64],
                raw_payload_json=json.dumps(raw),normalized_payload_json=json.dumps({"provider_id":external_id,"source":raw}),
                present=True,snapshot_run_id="full-run",last_seen_at=now,
            ))

    captured=[]
    def fake_fetch(**kwargs):
        captured.append(dict(kwargs))
        assert kwargs["resource"]=="locations_active"
        return _payload("locations_active",[{"Id":"LOC-CHANGED","Name":"Changed Room","LastModified":now.isoformat()}])
    monkeypatch.setattr(bootstrap_module,"fetch_metrc_resource",fake_fetch)

    result=MetrcIncrementalSyncService(engine).sync(
        organization_id="org-delta",facility_id="fac-delta",state="MA",environment="sandbox",license_number="MP281234",
        integrator_api_key="integrator",user_api_key="user",actor="tester",
    )

    locations=next(row for row in result["resources"] if row["resource"]=="locations")
    assert locations["status"]=="succeeded"
    assert locations["omitted_rows_marked_absent"] is False
    assert result["destructive_membership_replacement"] is False
    assert result["periodic_full_snapshot_required_for_absence"] is True
    assert len(captured)==1
    query=captured[0]["query"]
    assert set(query)=={"lastModifiedStart"}
    start=query["lastModifiedStart"]
    from datetime import datetime
    parsed=datetime.fromisoformat(start)
    expected=baseline-timedelta(minutes=5)
    assert abs((parsed-expected).total_seconds()) < 2

    with Session(engine) as session:
        current=list(session.scalars(select(IntegrationProviderSnapshot).where(
            IntegrationProviderSnapshot.organization_id=="org-delta",
            IntegrationProviderSnapshot.facility_id=="fac-delta",
            IntegrationProviderSnapshot.resource=="locations",
        )))
    assert {row.external_id for row in current if row.present}=={"LOC-KEEP","LOC-CHANGED"}
    changed=next(row for row in current if row.external_id=="LOC-CHANGED")
    assert "Changed Room" in changed.raw_payload_json


def test_incremental_new_item_and_package_materialize_naturally_and_replay_is_idempotent(monkeypatch):
    engine=_engine()
    _baseline(engine,"items")
    _baseline(engine,"packages")
    item={
        "Id":"ITEM-NEW","Name":"GMO Bulk Flower","ProductCategoryName":"Buds","UnitOfMeasureName":"Grams",
        "LastModified":utc_now().isoformat(),
    }
    package={
        "Id":"PKG-NEW","Label":"1A4000000000000000009999","Item":{"Id":"ITEM-NEW","Name":"GMO Bulk Flower","ProductCategoryName":"Buds","UnitOfMeasureName":"Grams"},
        "Quantity":1250.0,"UnitOfMeasureName":"Grams","LocationName":"Bulk Storage","LabTestingState":"TestPassed",
        "LastModified":utc_now().isoformat(),
    }

    def fake_fetch(**kwargs):
        if kwargs["resource"]=="items_active":
            return _payload("items_active",[item])
        if kwargs["resource"]=="packages_active":
            return _payload("packages_active",[package])
        raise AssertionError(f"unexpected provider read {kwargs['resource']}")
    monkeypatch.setattr(bootstrap_module,"fetch_metrc_resource",fake_fetch)

    service=MetrcIncrementalSyncService(engine)
    first=service.sync(
        organization_id="org-delta",facility_id="fac-delta",state="MA",environment="sandbox",license_number="MP281234",
        integrator_api_key="integrator",user_api_key="user",actor="tester",
    )
    assert first["totals"]["failed"]==0
    assert first["workspace_hydration"]["workspaces"]["product_master"]["created_products"]==1
    assert first["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_lots"]==1
    assert first["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_transactions"]==1

    second=service.sync(
        organization_id="org-delta",facility_id="fac-delta",state="MA",environment="sandbox",license_number="MP281234",
        integrator_api_key="integrator",user_api_key="user",actor="tester",
    )
    assert second["totals"]["failed"]==0
    assert second["workspace_hydration"]["workspaces"]["product_master"]["created_products"]==0
    assert second["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_lots"]==0
    assert second["workspace_hydration"]["workspaces"]["inventory"]["created_inventory_transactions"]==0

    with Session(engine) as session:
        products=list(session.scalars(select(Product).where(Product.organization_id=="org-delta")))
        lots=list(session.scalars(select(InventoryLot).where(InventoryLot.facility_id=="fac-delta")))
        transactions=list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.facility_id=="fac-delta")))
    assert len(products)==1
    assert products[0].name=="GMO Bulk Flower"
    assert len(lots)==1
    assert lots[0].compliance_package_id=="1A4000000000000000009999"
    assert lots[0].status=="available"
    assert len(transactions)==1
    assert transactions[0].quantity_delta==1250.0
