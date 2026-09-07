from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, MaterialReservation
from modules.coman.repository import ComanRepository
from modules.material_lineage.service import MaterialLineageService
from modules.production_erp.run360_mutations import ProductionRun360MutationService
from modules.production_erp.service import ProductionERPService


@dataclass(frozen=True)
class ComponentSpec:
    sku: str
    name: str
    item_type: str
    unit: str
    unit_cost: float
    required: float
    opening: float


@dataclass(frozen=True)
class FormatSpec:
    key: str
    product_name: str
    product_format: str
    components: tuple[ComponentSpec, ...]


FORMATS = (
    FormatSpec(
        key="infused-preroll",
        product_name="GMO Infused Pre-Roll 10 Pack",
        product_format="Infused Pre-Roll",
        components=(
            ComponentSpec("FO-IPR-FLOWER", "GMO Bulk Flower", "cannabis", "g", 2.00, 10.0, 20.0),
            ComponentSpec("FO-IPR-EXTRACT", "GMO Distillate", "cannabis", "g", 5.00, 2.0, 4.0),
            ComponentSpec("FO-IPR-TUBE", "10 Pack Pre-Roll Tube", "packaging", "unit", 0.35, 10.0, 20.0),
        ),
    ),
    FormatSpec(
        key="vape",
        product_name="GMO Vape Cartridge 1g",
        product_format="Vape Cart Fill",
        components=(
            ComponentSpec("FO-VAPE-OIL", "GMO Formulated Vape Oil", "cannabis", "g", 6.00, 10.0, 20.0),
            ComponentSpec("FO-VAPE-HARDWARE", "1g Vape Cartridge Hardware", "packaging", "unit", 1.25, 10.0, 20.0),
        ),
    ),
    FormatSpec(
        key="edible",
        product_name="GMO Gummies 10 Pack",
        product_format="Edible Gummies",
        components=(
            ComponentSpec("FO-EDIBLE-DIST", "GMO Distillate", "cannabis", "g", 5.00, 1.0, 2.0),
            ComponentSpec("FO-EDIBLE-BASE", "Gummy Base", "ingredient", "g", 0.05, 90.0, 180.0),
            ComponentSpec("FO-EDIBLE-JAR", "Gummy Jar", "packaging", "unit", 0.40, 10.0, 20.0),
        ),
    ),
)


def _engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _scope(engine):
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    organization = repo.create_organization("Functional Product Formats")
    facility = repo.create_facility(organization.id, "Manufacturing", "FO-MFG")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.production_enabled = True
        row.commercial_enabled = True
        row.license_number = "MP281234"
        row.license_type = "Marijuana Product Manufacturer"
    return repo, organization, facility


@pytest.mark.parametrize("spec", FORMATS, ids=lambda spec: spec.key)
def test_major_finished_formats_reserve_consume_and_output_exactly(spec: FormatSpec):
    engine = _engine()
    repo, organization, facility = _scope(engine)

    finished = repo.create_product(
        organization.id,
        sku=f"FO-{spec.key.upper()}-FG",
        name=spec.product_name,
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        retail_price=40,
        actor="format-acceptance",
    )

    components = []
    source_lots = []
    expected_balances = {}
    for index, component in enumerate(spec.components, start=1):
        product = repo.create_product(
            organization.id,
            sku=component.sku,
            name=component.name,
            item_type=component.item_type,
            base_unit=component.unit,
            unit_cost=component.unit_cost,
            actor="format-acceptance",
        )
        lot = repo.create_inventory_lot(
            organization.id,
            facility.id,
            product_id=product.id,
            lot_code=f"{spec.key.upper()}-SOURCE-{index}",
            opening_quantity=component.opening,
            unit=component.unit,
            actor="format-acceptance",
        )
        components.append({
            "input_product_id": product.id,
            "quantity": component.required,
            "unit": component.unit,
        })
        source_lots.append((lot, component))
        expected_balances[lot.id] = component.opening - component.required

    repo.create_bom(
        organization.id,
        output_product_id=finished.id,
        output_quantity=10,
        expected_loss_pct=0,
        components=components,
        actor="format-acceptance",
    )
    order = repo.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number=f"FO-{spec.key.upper()}-RUN-001",
        work_type="internal",
        product_name=finished.name,
        product_format=spec.product_format,
        requested_units=10,
        sku=finished.sku,
        actor="format-acceptance",
    )

    erp = ProductionERPService(engine)
    reserved = erp.reserve_bom_materials(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        actor="format-acceptance",
    )
    assert reserved["shortages"] == []

    with Session(engine) as session:
        reservations = list(
            session.scalars(
                select(MaterialReservation)
                .where(MaterialReservation.production_order_id == order.id)
                .order_by(MaterialReservation.lot_id)
            )
        )
        by_lot = {row.lot_id: row for row in reservations}
        assert set(by_lot) == {lot.id for lot, _component in source_lots}
        for lot, component in source_lots:
            assert by_lot[lot.id].quantity == component.required
            assert by_lot[lot.id].unit == component.unit
            assert by_lot[lot.id].status == "reserved"

    mutations = ProductionRun360MutationService(engine)
    materials = [
        {"lot_id": lot.id, "quantity": component.required, "unit": component.unit}
        for lot, component in source_lots
    ]
    preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload={"materials": materials},
    )
    assert preview["blocker_count"] == 0
    consumed = mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload={"materials": materials},
        preview_key=preview["preview_key"],
        actor="format-acceptance",
    )
    consumed_by_lot = {row["lot_id"]: row for row in consumed["result"]["consumed"]}
    assert set(consumed_by_lot) == set(expected_balances)
    for lot, component in source_lots:
        assert consumed_by_lot[lot.id]["quantity"] == component.required
        assert repo.inventory_balance(organization.id, lot.id) == expected_balances[lot.id]

    with Session(engine) as session:
        reservations = list(
            session.scalars(select(MaterialReservation).where(MaterialReservation.production_order_id == order.id))
        )
        assert len(reservations) == len(source_lots)
        assert all(row.quantity == 0 for row in reservations)
        assert all(row.status == "consumed" for row in reservations)

    output = erp.add_output(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        product_id=finished.id,
        planned_quantity=10,
        actor="format-acceptance",
        unit="unit",
        label=f"{spec.product_name} acceptance output",
    )
    output_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload={
            "output_id": output.id,
            "actual_quantity": 10,
            "lot_code": f"FO-{spec.key.upper()}-OUTPUT-LOT",
        },
    )
    assert output_preview["blocker_count"] == 0
    output_commit = mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload={
            "output_id": output.id,
            "actual_quantity": 10,
            "lot_code": f"FO-{spec.key.upper()}-OUTPUT-LOT",
        },
        preview_key=output_preview["preview_key"],
        actor="format-acceptance",
    )
    output_lot_id = output_commit["result"]["lot_id"]
    assert repo.inventory_balance(organization.id, output_lot_id) == 10

    release_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="qa_decision",
        payload={"event_type": "release", "result": "passed", "output_id": output.id},
    )
    assert release_preview["blocker_count"] == 0
    mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="qa_decision",
        payload={"event_type": "release", "result": "passed", "output_id": output.id},
        preview_key=release_preview["preview_key"],
        actor="qa",
    )

    graph = MaterialLineageService(engine).lot_graph(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=output_lot_id,
    )
    graph_lot_ids = {node["id"] for node in graph["nodes"] if node["type"] == "lot"}
    assert {lot.id for lot, _component in source_lots}.issubset(graph_lot_ids)
    assert any(
        node["type"] == "production_order" and node["order_number"] == f"FO-{spec.key.upper()}-RUN-001"
        for node in graph["nodes"]
    )

    completion = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="run_event",
        payload={"event_type": "completed"},
    )
    assert completion["blocker_count"] == 0


def test_vape_formulation_api_persists_exact_mass_and_rejects_invalid_formula_without_ghost_run():
    engine = _engine()
    _repo, organization, facility = _scope(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": organization.id,
        "X-Facility-Id": facility.id,
        "X-User-Id": "extraction-formulator",
        "X-User-Role": "dev",
    }
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.post(
            "/api/v1/extraction/runs",
            headers=headers,
            json={
                "batch_number": "FO-VAPE-FORM-001",
                "workflow_key": "ethanol_crude",
                "method": "Ethanol",
                "product_family": "Vape Oil",
                "final_product_type": "Vape Cart Fill",
                "formulation_used": True,
                "formulation_base_g": 100,
                "terpene_handling_mode": "Reintroduced Cannabis Terpenes",
                "terpene_type": "Cannabis-derived terpene blend",
                "terpene_source": "FO-TERP-SOURCE-001",
                "terpene_percentage": 5,
            },
        )
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["formulation_used"] is True
        assert run["formulation_base_g"] == 100
        assert run["terpene_percentage"] == 5
        assert run["terpene_weight_g"] == 5
        assert run["final_output_g"] == 105
        assert run["final_product_type"] == "Vape Cart Fill"
        assert run["terpene_type"] == "Cannabis-derived terpene blend"
        assert run["terpene_source"] == "FO-TERP-SOURCE-001"

        detail = client.get(f"/api/v1/extraction/runs/{run['id']}", headers=headers)
        assert detail.status_code == 200, detail.text
        persisted = detail.json()["run"]
        assert persisted["formulation_base_g"] == 100
        assert persisted["terpene_percentage"] == 5
        assert persisted["terpene_weight_g"] == 5
        assert persisted["final_output_g"] == 105

        before = client.get("/api/v1/extraction/runs", headers=headers)
        assert before.status_code == 200
        before_ids = {row["id"] for row in before.json()}

        invalid = client.post(
            "/api/v1/extraction/runs",
            headers=headers,
            json={
                "batch_number": "FO-VAPE-FORM-INVALID",
                "workflow_key": "ethanol_crude",
                "method": "Ethanol",
                "product_family": "Vape Oil",
                "formulation_used": True,
                "formulation_base_g": 100,
                "terpene_handling_mode": "Reintroduced Cannabis Terpenes",
                "terpene_percentage": 25,
            },
        )
        assert invalid.status_code == 422
        assert "outside the supported formulation range" in invalid.text

        after = client.get("/api/v1/extraction/runs", headers=headers)
        assert after.status_code == 200
        after_ids = {row["id"] for row in after.json()}
        assert after_ids == before_ids, "A rejected formulation must not leave a ghost extraction run."
    finally:
        app.dependency_overrides.clear()
