from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.inventory_transfers.service import InventoryTransferService
from modules.material_lineage.service import MaterialLineageService
from services.agent_registry import PROFILES
from services.ai.datasets import DatasetAccessContext, DatasetRegistry
from services.ai.router import ProviderRouter
from services.ai.runtime import AgentRuntime
from services.ai.schemas import AIResponse, ProviderHealth
from services.ai.tools import ToolRegistry
from services.ai.traceability_tools import AgentTraceabilityService, register_traceability_tools


class FakeProvider:
    def __init__(self, answer: str = "Grounded package review completed."):
        self.name = "local"
        self.model = "local-test-model"
        self.local = True
        self.answer = answer
        self.calls = 0
        self.requests = []

    def health(self):
        return ProviderHealth(self.name, True, True, self.model, True, True, True, "test")

    def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        structured = {
            "answer": self.answer,
            "summary": "grounded traceability review",
            "priority": "normal",
            "confidence": 1.0,
            "recommendations": [],
            "warnings": [],
            "missing_data": [],
        }
        return AIResponse(text=json.dumps(structured), provider=self.name, model=self.model, local=True, structured=structured)

    def supports_tools(self):
        return True

    def supports_structured_output(self):
        return True


class GovernmentRetriever:
    def search(self, **_kwargs):
        return {
            "results": [
                {
                    "title": "Government traceability rule",
                    "source": "test-government",
                    "source_type": "government",
                    "authority_level": 1,
                    "jurisdiction": "MA",
                    "effective_date": "2026-01-01",
                    "updated_at": "2026-01-01",
                    "version": "1",
                    "url": "https://example.test/government",
                    "page_or_section": "1",
                    "content": "Government evidence for the test.",
                    "score": 1.0,
                }
            ],
            "retrieval_mode": "test",
        }


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Organization(id="org-agent", name="Agent Trace Org", slug="agent-trace-org"),
                Organization(id="org-other", name="Other Agent Org", slug="other-agent-org"),
            ]
        )
        session.add_all(
            [
                Facility(
                    id="fac-source",
                    organization_id="org-agent",
                    name="Manufacturing License",
                    code="MFG",
                    license_number="MFG-AGENT",
                    production_enabled=True,
                    cultivation_enabled=True,
                    retail_enabled=False,
                ),
                Facility(
                    id="fac-dest",
                    organization_id="org-agent",
                    name="Retail License",
                    code="RTL",
                    license_number="RTL-AGENT",
                    retail_enabled=True,
                    production_enabled=False,
                    cultivation_enabled=False,
                ),
                Facility(
                    id="fac-other",
                    organization_id="org-other",
                    name="Other Tenant Facility",
                    code="OTH",
                    license_number="OTH-SECRET",
                    production_enabled=True,
                ),
            ]
        )
        session.add_all(
            [
                Product(id="prod-raw", organization_id="org-agent", sku="RAW", name="Raw Material", item_type="cannabis", base_unit="g", unit_cost=1.0),
                Product(id="prod-finished", organization_id="org-agent", sku="FIN", name="Finished Product", item_type="cannabis", base_unit="g", unit_cost=4.0),
                Product(id="prod-other", organization_id="org-other", sku="SECRET", name="Other Tenant Product", item_type="cannabis", base_unit="g", unit_cost=9.0),
            ]
        )
        session.flush()
        _lot(session, "lot-agent-source", "AGENT-SOURCE", "PKG-AGENT-SOURCE", "prod-raw", "org-agent", "fac-source", 100.0)
        _lot(session, "lot-agent-finished", "AGENT-FINISHED", "PKG-AGENT-FINISHED", "prod-finished", "org-agent", "fac-source", 20.0)
        _lot(session, "lot-other-secret", "SECRET-LOT", "PKG-OTHER-SECRET", "prod-other", "org-other", "fac-other", 10.0)
        _lot(session, "lot-dup-source", "DUPLICATE", "PKG-DUP-SOURCE", "prod-raw", "org-agent", "fac-source", 1.0)
        _lot(session, "lot-dup-dest", "DUPLICATE", "PKG-DUP-DEST", "prod-finished", "org-agent", "fac-dest", 1.0)

        transform = MaterialLineageService.transformation(
            session,
            organization_id="org-agent",
            facility_id="fac-source",
            transformation_type="production",
            source_entity_type="production_order",
            source_entity_id="agent-order-1",
            actor="seed",
        )
        MaterialLineageService.add_input(
            session,
            transform,
            entity_type="lot",
            entity_id="lot-agent-source",
            lot_id="lot-agent-source",
            product_id="prod-raw",
            quantity=25.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            transform,
            lot_id="lot-agent-finished",
            product_id="prod-finished",
            quantity=20.0,
            unit="g",
        )
    return engine


def _lot(
    session: Session,
    lot_id: str,
    lot_code: str,
    package_id: str,
    product_id: str,
    organization_id: str,
    facility_id: str,
    quantity: float,
) -> None:
    session.add(
        InventoryLot(
            id=lot_id,
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product_id,
            lot_code=lot_code,
            compliance_package_id=package_id,
            external_inventory_id=package_id,
            barcode_value=package_id,
            location_code="VAULT",
            status="released",
        )
    )
    session.flush()
    session.add(
        InventoryTransaction(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot_id,
            transaction_type="receipt",
            quantity_delta=quantity,
            unit="g",
            actor="seed",
        )
    )


def _transfer_finished(engine):
    service = InventoryTransferService(engine)
    dispatched = service.dispatch(
        "org-agent",
        "fac-source",
        destination_facility_id="fac-dest",
        manifest_reference="AGENT-MANIFEST-001",
        lines=[{"source_lot_id": "lot-agent-finished", "quantity": 4.0}],
        actor="shipper",
    )
    received = service.receive_line(
        "org-agent",
        "fac-dest",
        dispatched["id"],
        dispatched["lines"][0]["id"],
        operation="retail",
        package_id="PKG-AGENT-DEST",
        lot_code="AGENT-DEST",
        actor="receiver",
    )
    return received["lines"][0]["destination_lot_id"]


def _access(engine, *, role="operator", facility_id="fac-source", organization_id="org-agent", capabilities=None):
    return DatasetAccessContext(
        organization_id,
        facility_id,
        f"{role}-{facility_id}",
        role,
        frozenset(capabilities or {"production"}),
        operation_type="production",
        engine=engine,
    )


def test_traceability_tool_schemas_never_expose_tenant_scope_arguments():
    engine = _engine()
    tools = ToolRegistry({})
    assert register_traceability_tools(tools, _access(engine, role="admin")) is True
    assert {"package_lineage", "recall_blast_radius"}.issubset(set(tools.names()))
    serialized = json.dumps([schema for schema in tools.schemas() if schema["function"]["name"] in {"package_lineage", "recall_blast_radius"}]).casefold()
    assert "organization_id" not in serialized
    assert "facility_id" not in serialized
    assert "user_id" not in serialized
    assert '"role"' not in serialized


def test_agent_recall_fails_closed_across_unassigned_facility_but_preserves_exposure_reference():
    engine = _engine()
    destination_lot_id = _transfer_finished(engine)
    result = AgentTraceabilityService(_access(engine, role="operator")).recall_blast_radius({"identifier": "PKG-AGENT-SOURCE"})
    affected_ids = {row["lot_id"] for row in result["affected_lots"]}
    assert destination_lot_id not in affected_ids
    assert result["protected_exposure_count"] == 1
    assert result["redacted_facility_count"] == 1
    assert result["protected_exposures"][0]["package_id"] == "PKG-AGENT-DEST"
    assert result["protected_exposures"][0]["redacted"] is True
    assert result["read_only"] is True


def test_agent_recall_admin_can_follow_authorized_cross_license_destination():
    engine = _engine()
    destination_lot_id = _transfer_finished(engine)
    result = AgentTraceabilityService(_access(engine, role="admin")).recall_blast_radius({"identifier": "PKG-AGENT-SOURCE"})
    affected_ids = {row["lot_id"] for row in result["affected_lots"]}
    assert destination_lot_id in affected_ids
    assert result["protected_exposure_count"] == 0
    assert result["facility_count"] == 2
    assert result["license_count"] == 2
    assert result["scope_complete"] is True


def test_agent_traceability_does_not_leak_other_tenant_package_existence():
    engine = _engine()
    result = AgentTraceabilityService(_access(engine, role="admin")).package_lineage({"identifier": "PKG-OTHER-SECRET"})
    assert result["resolved"] is False
    assert result["status"] == "not_found"
    assert result["candidates"] == []
    assert "authorized facility scope" in result["_agent_summary"]
    serialized = json.dumps(result)
    assert "OTH-SECRET" not in serialized
    assert "Other Tenant Product" not in serialized


def test_agent_traceability_refuses_ambiguous_lot_code_instead_of_guessing():
    engine = _engine()
    result = AgentTraceabilityService(_access(engine, role="admin")).package_lineage({"identifier": "DUPLICATE"})
    assert result["resolved"] is False
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert {row["package_id"] for row in result["candidates"]} == {"PKG-DUP-SOURCE", "PKG-DUP-DEST"}
    assert "Use a unique package ID" in result["_agent_summary"]


def test_explicit_recall_question_runs_deterministically_with_zero_model_providers():
    engine = _engine()
    _transfer_finished(engine)
    runtime = AgentRuntime(
        provider_router=ProviderRouter({}, order=[], allow_cloud_fallback=False),
        dataset_registry=DatasetRegistry(),
    )
    result = runtime.run(
        profile=PROFILES["inventory"],
        access=_access(engine, role="admin"),
        question="What is the recall blast radius for package PKG-AGENT-SOURCE?",
    )
    assert result.provider == "deterministic"
    assert result.model == "python/sql"
    assert result.local is True
    assert result.read_only is True
    assert result.tool_calls == ["recall_blast_radius"]
    assert "Recall 360 for PKG-AGENT-SOURCE" in result.answer


def test_compliance_agent_can_report_factual_lineage_without_weakening_regulatory_grounding():
    engine = _engine()
    runtime = AgentRuntime(
        provider_router=ProviderRouter({}, order=[], allow_cloud_fallback=False),
        dataset_registry=DatasetRegistry(),
    )
    factual = runtime.run(
        profile=PROFILES["compliance"],
        access=_access(engine, role="admin"),
        question="Trace the lineage for package PKG-AGENT-FINISHED.",
    )
    assert factual.provider == "deterministic"
    assert factual.tool_calls == ["package_lineage"]
    assert factual.read_only is True
    assert "Package lineage for PKG-AGENT-FINISHED" in factual.answer

    regulatory = runtime.run(
        profile=PROFILES["compliance"],
        access=_access(engine, role="admin"),
        question="Is package PKG-AGENT-FINISHED legally compliant and can I release it?",
    )
    assert regulatory.provider == "deterministic"
    assert regulatory.model == "policy"
    assert regulatory.tool_calls == []
    assert "can’t verify" in regulatory.answer
    assert "government/regulatory" in regulatory.answer


def test_mixed_recall_and_legal_question_combines_traceability_with_authoritative_evidence():
    engine = _engine()
    _transfer_finished(engine)
    provider = FakeProvider("Package facts and government evidence were reviewed together.")
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
        retriever=GovernmentRetriever(),
    )
    result = runtime.run(
        profile=PROFILES["compliance"],
        access=_access(engine, role="admin"),
        question="What is the recall exposure for package PKG-AGENT-SOURCE, and is releasing it legally compliant?",
    )
    assert provider.calls == 1
    assert result.provider == "local"
    assert result.grounding == "mixed"
    assert "recall_blast_radius" in result.tool_calls
    assert result.sources
    request_text = "\n".join(message["content"] for message in provider.requests[0].messages)
    assert "Recall 360 for PKG-AGENT-SOURCE" in request_text
    assert "Retrieved knowledge evidence" in request_text
    assert "canonical application data" in request_text


def test_explicit_traceability_service_error_fails_closed_without_model_fallback(monkeypatch):
    engine = _engine()
    provider = FakeProvider("This answer must never be used.")

    def fail_recall(self, args):
        raise RuntimeError("traceability backend unavailable")

    monkeypatch.setattr(AgentTraceabilityService, "recall_blast_radius", fail_recall)
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
    )
    result = runtime.run(
        profile=PROFILES["inventory"],
        access=_access(engine, role="admin"),
        question="Show the recall blast radius for package PKG-AGENT-SOURCE.",
    )
    assert provider.calls == 0
    assert result.provider == "deterministic"
    assert result.model == "python/sql"
    assert result.read_only is True
    assert result.tool_calls == ["recall_blast_radius"]
    assert "won’t infer or reconstruct it from model memory" in result.answer
    assert result.warnings == ["Canonical traceability query failed closed."]


def test_traceability_tools_are_unavailable_without_trusted_engine_or_cannabis_capability():
    no_engine = DatasetAccessContext("org-agent", "fac-source", "u", "admin", frozenset({"production"}), operation_type="production")
    no_capability = DatasetAccessContext("org-agent", "fac-source", "u", "admin", frozenset({"commercial"}), operation_type="commercial", engine=_engine())
    assert AgentTraceabilityService.available_for(no_engine) is False
    assert AgentTraceabilityService.available_for(no_capability) is False
    tools = ToolRegistry({})
    assert register_traceability_tools(tools, no_engine) is False
    assert "package_lineage" not in tools.names()
