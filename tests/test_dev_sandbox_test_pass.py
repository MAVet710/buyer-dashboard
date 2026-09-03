import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.dev_sandbox_policy import dev_sandbox_test_pass_active
from modules.coman.models import Facility, Organization, Product
from modules.operational_moats.models import LabelReview, LabelTemplate
from modules.operational_moats.printing import LabelPrintJob, LabelPrintingService, PrinterProfile


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Organization.__table__,
        Facility.__table__,
        Product.__table__,
        LabelTemplate.__table__,
        LabelReview.__table__,
        PrinterProfile.__table__,
        LabelPrintJob.__table__,
    ]
    Organization.metadata.create_all(engine, tables=tables)
    return engine


def _scope(engine, *, slug: str, facility_code: str, suffix: str):
    with Session(engine) as session, session.begin():
        org = Organization(name=f"Org {suffix}", slug=slug)
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name=f"Facility {suffix}",
            code=facility_code,
        )
        session.add(facility)
        session.flush()
        return org.id, facility.id


def test_dev_sandbox_pass_requires_dev_role_and_exact_canonical_scope():
    engine = _engine()
    sandbox_org, sandbox_facility = _scope(
        engine, slug="dev-sandbox", facility_code="SANDBOX", suffix="sandbox"
    )
    real_org, real_facility = _scope(
        engine, slug="real-customer", facility_code="PROD", suffix="real"
    )
    wrong_code_org, wrong_code_facility = _scope(
        engine, slug="dev-sandbox-copy", facility_code="SANDBOX", suffix="copy"
    )

    with Session(engine) as session:
        assert dev_sandbox_test_pass_active(session, sandbox_org, sandbox_facility, "dev") is True
        assert dev_sandbox_test_pass_active(session, sandbox_org, sandbox_facility, "admin") is False
        assert dev_sandbox_test_pass_active(session, real_org, real_facility, "dev") is False
        assert dev_sandbox_test_pass_active(session, wrong_code_org, wrong_code_facility, "dev") is False
        assert dev_sandbox_test_pass_active(session, sandbox_org, real_facility, "dev") is False


def _seed_guarded_print(engine, organization_id: str, facility_id: str, *, suffix: str):
    with Session(engine) as session, session.begin():
        printer = PrinterProfile(
            organization_id=organization_id,
            facility_id=facility_id,
            name=f"Browser {suffix}",
            transport="browser",
            created_by="seed",
        )
        template = LabelTemplate(
            organization_id=organization_id,
            facility_id=facility_id,
            name=f"Draft label {suffix}",
            version=1,
            status="draft",
            layout_json='{"html_template":"<strong>{{product_name}}</strong>"}',
            created_by="seed",
        )
        session.add_all([printer, template])
        session.flush()
        review = LabelReview(
            organization_id=organization_id,
            facility_id=facility_id,
            template_id=template.id,
            status="fail",
            reviewed_by="seed",
        )
        session.add(review)
        session.flush()
        return printer.id, template.id, review.id


def test_advanced_printing_allows_audited_fail_only_in_dev_sandbox():
    engine = _engine()
    sandbox_org, sandbox_facility = _scope(
        engine, slug="dev-sandbox", facility_code="SANDBOX", suffix="sandbox-print"
    )
    real_org, real_facility = _scope(
        engine, slug="customer-prod", facility_code="MFG", suffix="prod-print"
    )
    sandbox_ids = _seed_guarded_print(engine, sandbox_org, sandbox_facility, suffix="sandbox")
    real_ids = _seed_guarded_print(engine, real_org, real_facility, suffix="real")
    service = LabelPrintingService(engine)

    sandbox_job = service.queue_job(
        organization_id=sandbox_org,
        facility_id=sandbox_facility,
        printer_profile_id=sandbox_ids[0],
        template_id=sandbox_ids[1],
        label_review_id=sandbox_ids[2],
        actor="dev-user",
        role="dev",
        render_data={"product_name": "Sandbox Flower"},
    )
    assert sandbox_job.status == "rendered"
    assert "DEV Sandbox test pass" in sandbox_job.override_reason
    assert "template_status=draft" in sandbox_job.override_reason
    assert "labelguard_status=fail" in sandbox_job.override_reason

    with pytest.raises(ValueError, match="active, approved label template"):
        service.queue_job(
            organization_id=real_org,
            facility_id=real_facility,
            printer_profile_id=real_ids[0],
            template_id=real_ids[1],
            label_review_id=real_ids[2],
            actor="dev-user",
            role="dev",
            render_data={"product_name": "Real Flower"},
        )


def test_non_dev_user_in_dev_sandbox_still_gets_normal_print_guards():
    engine = _engine()
    sandbox_org, sandbox_facility = _scope(
        engine, slug="dev-sandbox", facility_code="SANDBOX", suffix="role-guard"
    )
    ids = _seed_guarded_print(engine, sandbox_org, sandbox_facility, suffix="role-guard")
    service = LabelPrintingService(engine)

    with pytest.raises(ValueError, match="active, approved label template"):
        service.queue_job(
            organization_id=sandbox_org,
            facility_id=sandbox_facility,
            printer_profile_id=ids[0],
            template_id=ids[1],
            label_review_id=ids[2],
            actor="admin-user",
            role="admin",
            render_data={"product_name": "Sandbox Flower"},
        )
