from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio_fast import FastLabelInventoryService
from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.label_studio_workflow import LabelProductionSource, LabelProductionWorkflowService
from modules.product_master.packaging import ProductPackagingService


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _source(lot_id: str, product_name: str, package_id: str, strain: str):
    return {
        "lot_id": lot_id,
        "product_id": f"source-product-{lot_id}",
        "package_id": package_id,
        "lot_code": f"LOT-{strain}",
        "product_name": product_name,
        "inventory_unit": "g",
        "on_hand": 0,
        "label": {
            "product_name": product_name,
            "strain": strain,
            "harvest_date": "2026-08-01",
            "batch_number": f"BATCH-{strain}",
            "cultivated_by": "Example Cultivator",
            "cultivator_license": "MC281111",
            "test_date": "2026-08-20",
            "total_thc": "28%",
            "total_terpenes": "2.5%",
        },
        "coa": {
            "available": True,
            "needs_confirmation": False,
            "document_id": f"coa-{lot_id}",
            "date_tested": "2026-08-20",
            "overall_status": "pass",
            "total_thc": 28.0,
            "total_cbd": 0.1,
            "total_cannabinoids": 31.0,
            "total_terpenes": 2.5,
            "results": [],
        },
        "source_summary": {},
    }


def _seed(engine, *, source_count: int):
    with Session(engine) as session, session.begin():
        org = Organization(name="Label Source Org", slug=f"label-source-org-{source_count}")
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Manufacturing", code="MFG", production_enabled=True)
        finished = Product(organization_id=org.id, sku=f"FIN-{source_count}", name="Party Pack Duo" if source_count == 2 else "Flower 3.5g", item_type="finished_good", base_unit="unit")
        source_product = Product(organization_id=org.id, sku=f"SRC-{source_count}", name="Bulk Flower", item_type="cannabis", base_unit="g")
        session.add_all([facility, finished, source_product])
        session.flush()
        ProductPackagingService.upsert(
            session,
            organization_id=org.id,
            product_id=finished.id,
            net_content=3.5 if source_count == 1 else 14,
            net_content_unit="g",
            units_per_package=1 if source_count == 1 else 28,
            label_layout="compact_split",
            label_width_in=3.5,
            label_height_in=2.1,
            label_source_count=source_count,
        )
        first = InventoryLot(organization_id=org.id, facility_id=facility.id, product_id=source_product.id, lot_code="LOT-A", compliance_package_id="PKG-A", status="available")
        second = InventoryLot(organization_id=org.id, facility_id=facility.id, product_id=source_product.id, lot_code="LOT-B", compliance_package_id="PKG-B", status="available")
        session.add_all([first, second])
        session.flush()
        return org.id, facility.id, finished.id, first.id, second.id


def test_flower_split_label_does_not_require_available_grams(monkeypatch):
    engine = _engine()
    organization_id, facility_id, product_id, first_id, _second_id = _seed(engine, source_count=1)
    source = _source(first_id, "Flower Source", "PKG-A", "Tricheratops")
    monkeypatch.setattr(FastLabelInventoryService, "get_source", lambda self, org, facility, lot_id: source)

    run = LabelProductionWorkflowService(engine).create_run(
        organization_id,
        facility_id,
        source_lot_id=first_id,
        product_id=product_id,
        quantity=100,
        actor="operator",
    )

    assert run["status"] == "validated"
    assert run["expected_material_quantity"] == 0
    assert run["snapshot"]["print_layout"] == {"layout": "compact_split", "width_in": 3.5, "height_in": 2.1, "source_count": 1}
    assert len(run["snapshot"]["sources"]) == 1


def test_duo_label_snapshots_two_verified_sources(monkeypatch):
    engine = _engine()
    organization_id, facility_id, product_id, first_id, second_id = _seed(engine, source_count=2)
    source_by_lot = {
        first_id: _source(first_id, "Moon Pie Bulk", "PKG-A", "Moon Pie"),
        second_id: _source(second_id, "Cadillac Rainbows Bulk", "PKG-B", "Cadillac Rainbows"),
    }
    monkeypatch.setattr(FastLabelInventoryService, "get_source", lambda self, org, facility, lot_id: source_by_lot[lot_id])

    run = LabelProductionWorkflowService(engine).create_run(
        organization_id,
        facility_id,
        source_lot_id=first_id,
        secondary_source_lot_id=second_id,
        product_id=product_id,
        quantity=24,
        actor="operator",
    )

    assert run["snapshot"]["print_layout"]["source_count"] == 2
    assert [row["label"]["strain"] for row in run["snapshot"]["sources"]] == ["Moon Pie", "Cadillac Rainbows"]
    with Session(engine) as session:
        rows = list(session.scalars(select(LabelProductionSource).where(LabelProductionSource.run_id == run["id"])))
    assert len(rows) == 2
    assert all(row.planned_quantity == 0 for row in rows)
