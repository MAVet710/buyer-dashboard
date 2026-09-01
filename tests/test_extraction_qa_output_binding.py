from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization, Product
from modules.extraction.models import ExtractionQAEvent, ExtractionRunOutput
from modules.extraction.repository import ExtractionRepository


def _fixture(output_count: int = 1):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="QA Binding Org", slug="qa-binding-org")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="QA Manufacturing",
            code="QA-MFG",
            production_enabled=True,
            retail_enabled=False,
        )
        session.add(facility)
        products = [
            Product(
                organization_id=organization.id,
                sku=f"QA-OUTPUT-{index + 1}",
                name=f"QA Output {index + 1}",
                item_type="finished_good",
                base_unit="g",
            )
            for index in range(output_count)
        ]
        session.add_all(products)
        session.flush()
        organization_id = organization.id
        facility_id = facility.id
        product_ids = [row.id for row in products]

    repo = ExtractionRepository(engine)
    run = repo.create_run(
        organization_id=organization_id,
        facility_id=facility_id,
        batch_number=f"QA-BIND-{output_count}",
        method="Ethanol",
        workflow_key="ethanol_crude",
        actor="operator",
    )
    outputs = [
        repo.create_output(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            product_id=product_id,
            lot_code=f"QA-BIND-LOT-{index + 1}",
            quantity=5,
            unit="g",
            actor="operator",
        )
        for index, product_id in enumerate(product_ids)
    ]
    return engine, repo, organization_id, facility_id, run, outputs


def test_single_output_coa_event_binds_automatically_when_ui_omits_output_id():
    engine, repo, organization_id, facility_id, run, outputs = _fixture(1)

    event = repo.record_qa_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        event_type="coa_attached",
        result="passed",
        coa_reference="QA-BIND-COA-001",
        actor="qa",
    )

    with Session(engine) as session:
        saved_event = session.get(ExtractionQAEvent, event.id)
        saved_output = session.get(ExtractionRunOutput, outputs[0].id)
        assert saved_event.output_id == outputs[0].id
        assert saved_output.coa_status == "passed"


def test_multi_output_coa_event_requires_explicit_output_instead_of_guessing():
    _, repo, organization_id, facility_id, run, _ = _fixture(2)

    with pytest.raises(ValueError, match="specific extraction output"):
        repo.record_qa_event(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            event_type="coa_attached",
            result="passed",
            coa_reference="QA-BIND-COA-MULTI",
            actor="qa",
        )
