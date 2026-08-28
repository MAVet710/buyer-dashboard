from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers import inventory_reconciliation
from backend.app.services.metrc_context import MetrcContext
from modules.coman.models import Base, Facility, Organization


def _engine(*, commercial: bool = True):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Distributor", slug="distributor"))
        session.add(Facility(
            id="fac-1",
            organization_id="org-1",
            name="Wholesale Facility",
            code="WHOLE",
            commercial_enabled=commercial,
        ))
        session.commit()
    return engine


def _context() -> RequestContext:
    return RequestContext("user-1", "org-1", "fac-1", "operator")


def _metrc(environment: str = "sandbox") -> MetrcContext:
    return MetrcContext(
        configured=True,
        state="MA",
        license_number="LIC-WHOLE-1",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        status="connected",
        environment=environment,
        trusted_mapping=True,
        message="ready",
        row=object(),
    )


def _resource(resource: str, rows: list[dict] | None = None):
    rows = rows or []
    return {
        "ok": True,
        "resource": resource,
        "capability": resource,
        "rows": rows,
        "records": [
            {
                "provider_id": str(row.get("Id") or ""),
                "label": str(row.get("Label") or ""),
                "name": str(row.get("Name") or ""),
                "status": str(row.get("Status") or ""),
                "quantity": row.get("Quantity"),
                "unit_of_measure": str(row.get("UnitOfMeasureName") or ""),
                "last_modified": str(row.get("LastModified") or ""),
            }
            for row in rows
        ],
        "page_count": 1,
        "truncated": False,
        "read_plan": {"evidence": {"source_url": "https://api-ma.metrc.com/Documentation"}},
    }


def test_wholesale_snapshot_expands_outgoing_transfer_in_saved_environment(monkeypatch):
    engine = _engine()
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        inventory_reconciliation,
        "resolve_trusted_regulatory_metrc",
        lambda **_kwargs: _metrc("sandbox"),
    )

    def outgoing(**kwargs):
        calls.append(("outgoing", kwargs["environment"], kwargs["license_number"]))
        return _resource("outgoing_transfers", [{
            "Id": 11,
            "ManifestNumber": "MAN-11",
            "Status": "In Transit",
            "DestFacilityName": "Retail Customer",
            "DestFacilityLicenseNumber": "MR-1",
        }])

    def deliveries(**kwargs):
        calls.append(("deliveries", kwargs["environment"], str(kwargs["transfer_id"])))
        return _resource("transfer_deliveries", [{"Id": 22, "DeliveryId": 22}])

    def packages(**kwargs):
        calls.append(("packages", kwargs["environment"], str(kwargs["delivery_id"])))
        return _resource("wholesale_delivery_packages", [{"Id": 33}, {"Id": 34}])

    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfers", outgoing)
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transfer_deliveries", deliveries)
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_wholesale_delivery_packages", packages)
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfer_templates", lambda **kwargs: _resource("transfer_templates_outgoing", [{"Id": 1}]))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_drivers", lambda **kwargs: _resource("transporter_drivers", [{"Id": 1}]))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_vehicles", lambda **kwargs: _resource("transporter_vehicles", [{"Id": 1}]))

    result = inventory_reconciliation.wholesale_regulatory_snapshot(
        context=_context(), engine=engine, settings=object()
    )

    assert result["ready"] is True
    assert result["read_only"] is True
    assert result["environment"] == "sandbox"
    assert result["summary"]["outgoing_transfer_count"] == 1
    assert result["summary"]["manifest_reference_count"] == 1
    assert result["summary"]["delivery_count"] == 1
    assert result["summary"]["wholesale_package_count"] == 2
    assert result["summary"]["transfer_template_count"] == 1
    assert result["summary"]["transporter_driver_count"] == 1
    assert result["summary"]["transporter_vehicle_count"] == 1
    assert result["transfers"][0]["manifest_number"] == "MAN-11"
    assert all(environment == "sandbox" for _name, environment, _identifier in calls)


def test_wholesale_optional_transport_resources_report_unavailable_without_hiding_transfers(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(inventory_reconciliation, "resolve_trusted_regulatory_metrc", lambda **_kwargs: _metrc())
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfers", lambda **kwargs: _resource("outgoing_transfers", []))
    blocked = {"ok": False, "resource": "transporter_drivers", "status": "regulatory_read_blocked", "message": "Capability unavailable."}
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfer_templates", lambda **kwargs: dict(blocked, resource="transfer_templates_outgoing"))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_drivers", lambda **kwargs: dict(blocked))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_vehicles", lambda **kwargs: dict(blocked, resource="transporter_vehicles"))

    result = inventory_reconciliation.wholesale_regulatory_snapshot(
        context=_context(), engine=engine, settings=object()
    )

    assert result["ready"] is True
    assert result["summary"]["outgoing_transfer_count"] == 0
    assert result["resources"]["transfer_templates"]["available"] is False
    assert result["resources"]["transporter_drivers"]["available"] is False
    assert result["resources"]["transporter_vehicles"]["available"] is False


def test_wholesale_snapshot_caps_high_fanout_transfer_expansion(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(inventory_reconciliation, "resolve_trusted_regulatory_metrc", lambda **_kwargs: _metrc())
    rows = [{"Id": index, "ManifestNumber": f"MAN-{index}"} for index in range(1, 52)]
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfers", lambda **kwargs: _resource("outgoing_transfers", rows))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_outgoing_transfer_templates", lambda **kwargs: _resource("transfer_templates_outgoing"))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_drivers", lambda **kwargs: _resource("transporter_drivers"))
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transporter_vehicles", lambda **kwargs: _resource("transporter_vehicles"))
    expanded: list[str] = []

    def deliveries(**kwargs):
        expanded.append(str(kwargs["transfer_id"]))
        return _resource("transfer_deliveries", [])

    monkeypatch.setattr(inventory_reconciliation, "fetch_all_transfer_deliveries", deliveries)

    result = inventory_reconciliation.wholesale_regulatory_snapshot(
        context=_context(), engine=engine, settings=object()
    )

    assert result["summary"]["outgoing_transfer_count"] == 51
    assert result["summary"]["expanded_transfer_count"] == 50
    assert result["summary"]["expansion_limited"] is True
    assert len(expanded) == 50
    assert len(result["transfers"]) == 50
    assert any("first 50" in warning for warning in result["warnings"])
