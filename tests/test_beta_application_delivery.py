from __future__ import annotations

from sqlalchemy import create_engine

from backend.app.config import Settings
from backend.app.routers import beta


def payload(**overrides):
    values = dict(
        name="Test Operator",
        email="operator@example.com",
        company="Test Cannabis Co",
        role="Operations Manager",
        operation="Vertically Integrated",
        facilities="2–3",
        primary_workflow="Extraction & Production",
        stack="Dutchie",
        state="MA",
        timeline="Within 30 days",
        pain="We need better operational visibility across facilities.",
        must_have="One place to see inventory, production, and compliance.",
        consent=True,
    )
    values.update(overrides)
    return beta.BetaApplication(**values)


def test_beta_application_routes_to_durable_advisory_pipeline(monkeypatch):
    captured = {}

    def fake_capture(engine, settings, lead):
        captured["engine"] = engine
        captured["settings"] = settings
        captured["lead"] = lead
        return {"accepted": True, "reference": "lead-123"}

    monkeypatch.setattr(beta.advisory, "capture_lead", fake_capture)
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    settings = Settings(doobielogic_advisory_organization_id="advisory-owner")
    result = beta.submit_beta_application(payload(), engine=engine, settings=settings)

    lead = captured["lead"]
    assert result == {"accepted": True, "reference": "lead-123"}
    assert lead.service == "beta-program"
    assert lead.locations == 2
    assert lead.email == "operator@example.com"
    assert lead.challenge.startswith("We need better operational visibility")
    assert "Beta facilities / licenses: 2–3" in lead.message
    assert "Primary pilot workflow: Extraction & Production" in lead.message
    assert "Primary POS / ERP: Dutchie" in lead.message
    assert "Desired beta start: Within 30 days" in lead.message
    assert "One place to see inventory" in lead.message
    engine.dispose()


def test_beta_honeypot_does_not_persist(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("honeypot must not persist")
    monkeypatch.setattr(beta.advisory, "capture_lead", fail)
    result = beta.submit_beta_application(
        payload(website="spam.invalid"),
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        settings=Settings(),
    )
    assert result == {"accepted": True}
