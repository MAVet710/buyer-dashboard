import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

from backend.app.routers.traceability_actions import TraceabilityIntent, _preflight
from modules.traceability.action_registry import get_traceability_action, list_traceability_actions
from modules.traceability.models import TraceabilityTransaction


ROOT = Path(__file__).resolve().parents[1]


def _intent(**overrides):
    values = {
        "provider": "metrc",
        "operation_type": "plant_move",
        "entity_id": "plant-1",
        "license_number": "LIC-1",
        "jurisdiction": "MA",
        "environment": "sandbox",
        "payload": {"destination_location": "Flower 2"},
        "reason": "Move selected plants",
        "idempotency_key": "move-plant-1-v1",
        "workflow_id": "cultivation-move-44",
    }
    values.update(overrides)
    return TraceabilityIntent(**values)


def test_registry_exposes_domain_first_safety_contracts():
    actions = {row.name: row for row in list_traceability_actions()}
    assert {"package_create", "plant_batch_create", "plant_move", "plant_harvest", "harvest_package", "transfer_create"} <= actions.keys()
    move = get_traceability_action("plant_move")
    assert move is not None
    assert move.label == "Move plants"
    assert move.supports_bulk is True
    assert move.execution_path == "specialized_verified"
    assert move.retry_policy == "reconcile_before_retry"
    assert move.reconciliation_strategy == "exact_provider_readback"
    assert get_traceability_action("harvest_start").catalog_visible is False


def test_preflight_returns_operator_preview_and_replay_contract():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    TraceabilityTransaction.__table__.create(engine)
    result = _preflight(_intent(), SimpleNamespace(role="operator", organization_id="org-1", facility_id="fac-1"), engine)
    assert result["ready"] is True
    assert result["summary"]["title"] == "Move plants"
    assert result["summary"]["verification"] == "plants_by_id"
    assert result["revalidate_on_execute"] is True
    assert len(result["preview_token"]) == 64


def test_preflight_blocks_incomplete_environment_and_payload():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    TraceabilityTransaction.__table__.create(engine)
    result = _preflight(
        _intent(environment="", license_number="", payload={}),
        SimpleNamespace(role="admin", organization_id="org-1", facility_id="fac-1"),
        engine,
    )
    assert result["ready"] is False
    assert {row["code"] for row in result["blockers"]} == {"facility_mapping_incomplete", "environment_not_verified", "input_missing"}


def test_coverage_matrix_tracks_ledger_and_future_queue_guards():
    matrix = json.loads((ROOT / "docs" / "metrc-action-coverage.json").read_text(encoding="utf-8"))
    assert matrix["all_outbound"] == {
        "ledger": True,
        "idempotency": True,
        "preview": True,
        "reconciliation": True,
        "blind_retry": False,
        "revalidate_on_execute": True,
    }
    assert matrix["domains"]["cultivation"]["status"] == "specialized_verified"
