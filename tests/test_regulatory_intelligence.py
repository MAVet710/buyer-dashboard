from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers import ai_agents
from backend.app.services import regulatory_intelligence as intelligence_module
from backend.app.services.metrc_context import MetrcContext
from backend.app.services.regulatory_intelligence import RegulatoryIntelligenceService
from modules.coman.models import Facility
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from tests.test_web_inventory_api import _engine


def _context() -> RequestContext:
    return RequestContext("user-1", "org-1", "facility-1", "admin")


def _metrc(*, trusted: bool = True, status: str = "connected") -> MetrcContext:
    return MetrcContext(
        configured=True,
        state="MA",
        license_number="MP281281",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        status=status,
        environment="sandbox",
        trusted_mapping=trusted,
        message="ready",
        row=object(),
    )


def _ok(resource: str, records=None, rows=None):
    values = list(records or [])
    provider_rows = list(rows if rows is not None else [dict(row.get("source") or {}) for row in values])
    return {
        "ok": True,
        "resource": resource,
        "records": values,
        "rows": provider_rows,
        "page_count": 1,
        "truncated": False,
        "read_plan": {"evidence": {"source": "official-docs", "resource": resource}},
    }


def test_unconfigured_metrc_still_surfaces_local_traceability_exception(monkeypatch):
    engine = _engine()
    repo = TraceabilityBackofficeRepository(engine)
    tx = repo.create_transaction(
        organization_id="org-1",
        facility_id="facility-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406000000001",
        idempotency_key="reg-intel-unconfigured",
        actor="tester",
    )
    for status in ("validated", "queued", "submitted", "reconciliation_required"):
        tx = repo.transition_logged(
            organization_id="org-1",
            facility_id="facility-1",
            transaction_id=tx.id,
            new_status=status,
            actor="worker",
            reason="provider mismatch",
            source="system",
        )
    monkeypatch.setattr(
        intelligence_module,
        "resolve_metrc_context",
        lambda *_args, **_kwargs: (None, MetrcContext(configured=False, message="Configure Metrc for this facility.")),
    )

    report = RegulatoryIntelligenceService(engine, object()).collect(_context())

    assert report["configured"] is False
    assert report["ready"] is False
    assert report["summary"]["high_count"] == 1
    assert report["findings"][0]["domain"] == "traceability"
    assert report["findings"][0]["entity_id"] == "1A406000000001"


def test_untrusted_mapping_fails_closed_before_any_provider_read(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(intelligence_module, "resolve_metrc_context", lambda *_args, **_kwargs: (None, _metrc(trusted=False)))

    def should_not_run(**_kwargs):
        raise AssertionError("provider read should not run before trusted mapping")

    monkeypatch.setattr(intelligence_module, "fetch_all_active_metrc_packages", should_not_run)
    report = RegulatoryIntelligenceService(engine, object()).collect(_context())

    assert report["ready"] is False
    assert any(row["code"] == "metrc_mapping_not_trusted" for row in report["findings"])


def test_multi_domain_live_intelligence_propagates_exact_environment_and_prioritizes_findings(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        facility = session.get(Facility, "facility-1")
        facility.retail_enabled = True
        facility.production_enabled = True
        facility.cultivation_enabled = True
        facility.commercial_enabled = True
        session.commit()

    monkeypatch.setattr(intelligence_module, "resolve_metrc_context", lambda *_args, **_kwargs: (None, _metrc()))
    captured = []

    def packages(**kwargs):
        captured.append(("packages", kwargs["environment"], kwargs["license_number"]))
        return _ok("packages_active", records=[{
            "provider_id": "99",
            "label": "1A406000000001",
            "name": "Blue Dream",
            "status": "TestFailed",
            "quantity": 10,
            "unit_of_measure": "g",
            "source": {"Label": "1A406000000001", "LabTestingState": "TestFailed", "LocationName": "Bulk Vault"},
        }])

    def processing(**kwargs):
        captured.append(("processing", kwargs["environment"], kwargs["license_number"]))
        return _ok("processing_active", records=[{"provider_id": "P-1", "name": "Run 1", "status": "On Hold", "source": {"Status": "On Hold"}}])

    def empty_named(name):
        def inner(**kwargs):
            captured.append((name, kwargs["environment"], kwargs.get("license_number", "")))
            return _ok(name)
        return inner

    def outgoing(**kwargs):
        captured.append(("outgoing", kwargs["environment"], kwargs["license_number"]))
        return _ok("outgoing_transfers", rows=[{"Id": 44, "DestFacilityName": "Retailer"}])

    monkeypatch.setattr(intelligence_module, "fetch_all_active_metrc_packages", packages)
    monkeypatch.setattr(intelligence_module, "fetch_all_active_processing_jobs", processing)
    monkeypatch.setattr(intelligence_module, "fetch_all_active_plant_batches", empty_named("plant_batches_active"))
    monkeypatch.setattr(intelligence_module, "fetch_all_vegetative_plants", empty_named("plants_vegetative"))
    monkeypatch.setattr(intelligence_module, "fetch_all_flowering_plants", empty_named("plants_flowering"))
    monkeypatch.setattr(intelligence_module, "fetch_all_active_harvests", empty_named("harvests_active"))
    monkeypatch.setattr(intelligence_module, "fetch_all_outgoing_transfers", outgoing)
    monkeypatch.setattr(intelligence_module, "fetch_all_transporter_drivers", empty_named("transporter_drivers"))
    monkeypatch.setattr(intelligence_module, "fetch_all_transporter_vehicles", empty_named("transporter_vehicles"))
    monkeypatch.setattr(intelligence_module, "fetch_all_transfer_deliveries", lambda **kwargs: _ok("transfer_deliveries"))
    monkeypatch.setattr(intelligence_module, "fetch_all_wholesale_delivery_packages", lambda **kwargs: _ok("wholesale_delivery_packages"))

    report = RegulatoryIntelligenceService(engine, object()).collect(_context())
    codes = {row["code"] for row in report["findings"]}

    assert report["configured"] is True
    assert report["ready"] is True
    assert report["scope"]["environment"] == "sandbox"
    assert report["summary"]["high_count"] >= 2
    assert "package_regulatory_hold" in codes
    assert "processing_job_exception" in codes
    assert "transfer_manifest_reference_missing" in codes
    assert "transfer_recipient_license_missing" in codes
    assert "no_transporter_drivers_returned" in codes
    assert "no_transporter_vehicles_returned" in codes
    assert captured
    assert all(environment == "sandbox" for _name, environment, _license in captured)
    assert all(license_number in {"", "MP281281"} for _name, _environment, license_number in captured)
    assert report["findings"][0]["severity"] == "high"


def test_compliance_agent_receives_sanitized_regulatory_context(monkeypatch):
    engine = _engine()
    captured = {}
    report = {
        "generated_at": "2026-08-28T21:00:00+00:00",
        "ready": True,
        "scope": {"jurisdiction_code": "MA", "license_number": "MR123", "environment": "sandbox"},
        "summary": {"high_count": 1, "medium_count": 0, "info_count": 0},
        "findings": [{
            "severity": "high", "domain": "inventory", "code": "missing_in_metrc", "title": "Missing In Metrc",
            "message": "Local package was not returned.", "entity_type": "package", "entity_id": "PKG-1",
            "source": "metrc_package_reconciliation", "recommended_review": "Review the package.",
            "jurisdiction_code": "MA", "license_number": "MR123", "environment": "sandbox",
            "credential": "must-never-be-injected",
        }],
        "warnings": [],
        "snapshots": {},
    }

    monkeypatch.setattr(ai_agents.RegulatoryIntelligenceService, "collect", lambda _self, _context: report)

    class FakeResult:
        def as_dict(self):
            return {"answer": "review", "datasets": [], "data_freshness": {}, "read_only": True}

    class FakeRuntime:
        def run(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr(
        ai_agents,
        "build_runtime",
        lambda **_kwargs: (FakeRuntime(), object(), "Org", "Facility", {}),
    )

    output = ai_agents.run_agent(
        ai_agents.AgentRun(agent_key="compliance", app_mode="Retail Ops", section="Compliance", question="What needs review?"),
        context=_context(),
        engine=engine,
        settings=object(),
    )

    injected = captured["history"][-1]["content"]
    assert "observed operational/provider signals, not as legal conclusions" in injected
    assert "must-never-be-injected" not in injected
    assert "PKG-1" in injected
    assert "regulatory_intelligence" in output["datasets"]
    assert output["data_freshness"]["regulatory_intelligence"] == "2026-08-28T21:00:00+00:00"


def test_react_regulatory_panel_is_explicit_and_not_auto_fetched():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    panel = (root / "frontend" / "src" / "components" / "RegulatoryIntelligencePanel.tsx").read_text(encoding="utf-8")
    page = (root / "frontend" / "src" / "pages" / "CompliancePage.tsx").read_text(encoding="utf-8")
    assert 'enabled: active' in panel
    assert "Check regulatory state" in panel
    assert "No live Metrc request is made until you run this check." in panel
    assert "Signals identify what needs review; they do not replace authoritative regulations or SOPs." in panel
    assert "<RegulatoryIntelligencePanel/>" in page
