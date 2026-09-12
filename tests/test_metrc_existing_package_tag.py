"""Offline regressions only: synthetic provider responses never certify a task."""
from __future__ import annotations

import ast
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from services.metrc_existing_package_tag import (
    ExistingPackageTagError, load_existing_tag_allocation,
    verify_allocation_resume, verify_existing_tag_available,
)
from services.metrc_resume_response import ResumeResponseError, object_rows, verify_package

RUN = "TEST-PKG-RUN"
BASE = "DL-EVAL-20260912-RESUME-01"
SOURCE = "TESTPKG00000000000001"
RESERVED = "TESTPKG00000000000002"
DESTINATION = "TESTPKG00000000000003"
LICENSE = "TEST-SANDBOX-FACILITY"


def raw_plan():
    return {"schema_version": 1, "run_id": RUN, "evaluation_run_id": BASE,
            "state": "MA", "environment": "sandbox", "license_number": LICENSE,
            "source_id": "10", "source_label": SOURCE, "destination_label": DESTINATION,
            "protected_labels": [SOURCE, RESERVED], "task17_reserved_label": RESERVED,
            "checkpoint_sha256": "a" * 64, "reservation_evidence_sha256": "b" * 64}


def load(value=None):
    return load_existing_tag_allocation(json.dumps(raw_plan() if value is None else value),
        run_id=RUN, evaluation_run_id=BASE, license_number=LICENSE,
        source_id="10", source_label=SOURCE)


def tag_row():
    return {"Id": 40, "FacilityId": 7, "Label": DESTINATION,
            "TagInventoryTypeName": "CannabisPackage"}


def completed(task):
    return {"passed": True, "http_status": 200, "stage": "complete", "task_number": task,
            "postconditions_verified": True, "label": DESTINATION, "provider_id": "20"}


def test_allocation_stable_hash_and_valid_provider_row():
    plan = load()
    assert plan["destination_label"] != plan["task17_reserved_label"]
    assert len(plan["allocation_sha256"]) == 64
    reordered = raw_plan()
    reordered["protected_labels"].reverse()
    assert load(reordered) == plan
    assert verify_existing_tag_available(plan, [tag_row()], provider_facility_id=7)["Id"] == 40


@pytest.mark.parametrize("key,value", [
    ("run_id", "OTHER"), ("evaluation_run_id", "OTHER"), ("state", "CA"),
    ("environment", "production"), ("license_number", "OTHER"),
    ("source_id", "99"), ("source_label", DESTINATION),
    ("schema_version", True), ("destination_label", RESERVED),
    ("destination_label", SOURCE), ("destination_label", "bad"),
    ("protected_labels", []), ("protected_labels", [SOURCE]),
    ("protected_labels", [RESERVED]), ("protected_labels", [SOURCE, RESERVED, RESERVED]),
    ("checkpoint_sha256", "missing"), ("reservation_evidence_sha256", ""),
])
def test_allocation_rejects_scope_changes_or_missing_protection(key, value):
    plan = raw_plan(); plan[key] = value
    with pytest.raises(ExistingPackageTagError):
        load(plan)


@pytest.mark.parametrize("value", [None, [], {"unexpected": "field"}, "text"])
def test_allocation_rejects_non_plan(value):
    with pytest.raises(ExistingPackageTagError):
        load_existing_tag_allocation(json.dumps(value), run_id=RUN, evaluation_run_id=BASE,
            license_number=LICENSE, source_id="10", source_label=SOURCE)


@pytest.mark.parametrize("rows", [[], [tag_row(), tag_row()],
    [{**tag_row(), "FacilityId": 8}], [{**tag_row(), "TagInventoryTypeName": "CannabisPlant"}],
    [{**tag_row(), "Id": None}], [{**tag_row(), "Id": True}], [{**tag_row(), "Label": RESERVED}],
])
def test_current_inventory_must_identify_exact_available_package_tag(rows):
    with pytest.raises(ExistingPackageTagError):
        verify_existing_tag_available(load(), rows, provider_facility_id=7)


@pytest.mark.parametrize("events", [
    {"tag_generation_started": {}}, {"tag_generation_result": {"passed": False}},
    {"task25_started": {}}, {"task26_started": {}},
    {"task25_result": completed(25)},
    {"tag_allocation": {"allocation_sha256": "other"}},
])
def test_resume_refuses_ambiguous_or_unbound_prior_attempts(events):
    with pytest.raises(ExistingPackageTagError):
        verify_allocation_resume(load(), events)


def test_resume_accepts_bound_prior_pass_and_rejects_false_positive():
    events = {"tag_allocation": load(), "task25_result": completed(25)}
    verify_allocation_resume(load(), events)
    for field, value in [("http_status", 201), ("stage", "write"),
                         ("postconditions_verified", False), ("label", RESERVED), ("passed", False)]:
        bad = deepcopy(events); bad["task25_result"][field] = value
        with pytest.raises(ExistingPackageTagError):
            verify_allocation_resume(load(), bad)


def runner_functions():
    """Load real function bodies without importing the API's startup threads."""
    path = Path(__file__).parents[1] / "backend/app/services/metrc_package_eval_resume.py"
    tree = ast.parse(path.read_text())
    names = {"MetrcPackageResumeError", "_now", "_configuration", "_sanitize", "_record",
             "_once", "_alternate_item", "run_package_tasks_25_26"}
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
             and node.name in names]
    env = {"datetime": datetime, "timezone": timezone, "os": os, "re": re, "json": json,
           "hashlib": hashlib, "ZoneInfo": ZoneInfo, "EVALUATION_BASE_RUN": BASE,
           "SOURCE_ITEM": BASE + "-Clones", "ENTITY_TYPE": "metrc_package_eval_resume",
           "TAG_PATTERN": re.compile(r"^[A-Z0-9]{20,32}$"), "object_rows": object_rows,
           "verify_package": verify_package, "ResumeResponseError": ResumeResponseError,
           "ExistingPackageTagError": ExistingPackageTagError,
           "load_existing_tag_allocation": load_existing_tag_allocation,
           "verify_existing_tag_available": verify_existing_tag_available,
           "verify_allocation_resume": verify_allocation_resume}
    module = ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), env)
    return env


def setup_runner(monkeypatch, *, mode="preflight", events=None):
    ns = runner_functions()
    for key, value in {"ORGANIZATION_ID": "test-org", "FACILITY_ID": "test-facility",
                       "SOURCE_LABEL": SOURCE, "SOURCE_ID": "10", "MODE": mode,
                       "APPROVAL": RUN, "TAG_ALLOCATION": json.dumps(raw_plan())}.items():
        monkeypatch.setenv("METRC_PACKAGE_EVAL_" + key, value)
    events = deepcopy(events or {})
    recorded, paths = [], []
    source = {"Id": 10, "Label": SOURCE, "Item": {"Name": BASE + "-Clones",
              "ProductCategoryName": "Immature Plants"}, "Quantity": 2 if events.get("task25_result") else 3,
              "UnitOfMeasureName": "Each", "IsFinished": False, "IsOnHold": False,
              "PackageType": "ImmaturePlant", "LocationName": "TEST-ROOM"}
    alternate = {"Id": 30, "Name": BASE + "-Clones-Alt", "ProductCategoryName": "Immature Plants",
                 "QuantityType": "CountBased", "UnitOfMeasureName": "Each", "ApprovalStatus": "Approved"}
    target = {**source, "Id": 20, "Label": DESTINATION, "Quantity": 1}
    if events.get("task26_result"):
        target["Item"] = {"Name": alternate["Name"]}
    fixture = {"source": source, "target": target, "available": [tag_row()], "paths": paths,
               "events": events, "recorded": recorded, "writes": []}

    class Provider:
        def __init__(self, _): pass
        def get(self, path, **_):
            paths.append(path)
            assert path == "facilities/v2/", "Unexpected provider endpoint: " + path
            return [{"Id": 7, "LicenseNumber": LICENSE, "FacilityType": {}}], {"http_status": 200}
        def package(self, label):
            paths.append("packages/v2/" + label)
            return deepcopy(source if label == SOURCE else target), {"http_status": 200}
        def pages(self, path):
            paths.append(path)
            assert path in {"items/v2/active", "tags/v2/package/available"}
            rows = [alternate] if path == "items/v2/active" else fixture["available"]
            return deepcopy(rows), [{"http_status": 200, "path": path, "response": deepcopy(rows)}]

    ns["_Provider"] = Provider
    ns["_facility_lock"] = lambda *_: nullcontext()
    ns["_events"] = lambda *_: events
    def record(*args):
        action, data = args[4:6]
        recorded.append(action)
        events[action] = deepcopy(data)
        if action == "tag_allocation" and fixture.get("consume_after_reservation"):
            fixture["available"] = []
    ns["_record"] = record
    ns["select"] = MagicMock()
    ns["IntegrationConfiguration"] = MagicMock()
    session = MagicMock()
    session.__enter__.return_value = session
    session.scalars.return_value = [SimpleNamespace(scope_key="test-user|test-facility")]
    ns["Session"] = lambda *_: session
    ns["RequestContext"] = lambda *_: None
    ns["resolve_metrc_context"] = lambda *_: (None, SimpleNamespace(
        configured=True, trusted_mapping=True, environment="sandbox", state="MA", status="connected",
        license_number=LICENSE, integrator_api_key="synthetic-vendor", user_api_key="synthetic-user"))
    def task(provider, number, payload, record, **_):
        assert "tag_allocation" in recorded
        assert f"task{number}_started" in recorded
        assert payload.get("tag", payload.get("label")) == DESTINATION
        fixture["writes"].append(number)
        if number == 25:
            source["Quantity"] = 2
        else:
            target["Item"] = {"Name": alternate["Name"]}
        return completed(number)
    ns["_task"] = task
    fixture["run"] = lambda: ns["run_package_tasks_25_26"](None, None, RUN)
    return ns, fixture


def test_preflight_never_mutates_or_calls_sandbox_provisioning(monkeypatch):
    _, fixture = setup_runner(monkeypatch)
    result = fixture["run"]()
    assert result == {"status": "preflight_complete", "mutations_sent": 0}
    assert fixture["recorded"] == ["preflight"]
    assert fixture["writes"] == []
    assert all(not path.startswith(("sandbox/", "sales/")) for path in fixture["paths"])


def test_execute_reserves_exact_tag_and_runs_only_25_26(monkeypatch):
    _, fixture = setup_runner(monkeypatch, mode="execute")
    assert fixture["run"]()["status"] == "complete"
    assert fixture["writes"] == [25, 26]
    assert fixture["paths"].count("tags/v2/package/available") == 2
    assert fixture["events"]["tag_allocation"]["destination_label"] == DESTINATION
    assert RESERVED in fixture["events"]["tag_allocation"]["protected_labels"]


def test_tag_disappearing_after_preflight_blocks_before_create(monkeypatch):
    _, fixture = setup_runner(monkeypatch, mode="execute")
    fixture["consume_after_reservation"] = True
    assert fixture["run"]()["status"] == "blocked"
    assert fixture["writes"] == []


def test_prior_unknown_create_is_not_retried(monkeypatch):
    _, fixture = setup_runner(monkeypatch, mode="execute", events={"task25_started": {}})
    assert fixture["run"]()["status"] == "blocked"
    assert fixture["writes"] == []
    assert fixture["paths"] == []


def test_verified_task25_resume_only_executes_task26(monkeypatch):
    prior = {"tag_allocation": load(), "task25_started": {}, "task25_result": completed(25)}
    _, fixture = setup_runner(monkeypatch, mode="execute", events=prior)
    fixture["available"] = []  # Task 25 already consumed this tag.
    assert fixture["run"]()["status"] == "complete"
    assert fixture["writes"] == [26]


def test_restart_after_task26_pass_never_repeats_mutations(monkeypatch):
    prior = {"tag_allocation": load(), "task25_result": completed(25), "task26_result": completed(26)}
    _, fixture = setup_runner(monkeypatch, mode="execute", events=prior)
    fixture["available"] = []
    assert fixture["run"]()["status"] == "complete"
    assert fixture["writes"] == []


def test_execute_still_requires_exact_approval(monkeypatch):
    _, fixture = setup_runner(monkeypatch, mode="execute")
    monkeypatch.setenv("METRC_PACKAGE_EVAL_APPROVAL", "OTHER")
    with pytest.raises(RuntimeError): fixture["run"]()
    assert fixture["paths"] == fixture["writes"] == []


def test_existing_record_claim_is_atomic_and_does_not_hold_connection_for_io():
    ns = runner_functions()
    fake = MagicMock(); fake.__enter__.return_value = fake
    fake.execute.return_value.scalar_one.return_value = True
    fake.scalars.return_value = []
    ns.update(Session=lambda *_: fake, select=MagicMock(), text=lambda sql: sql, AuditEvent=MagicMock())
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    ns["_record"](engine, RUN, "test-org", "test-facility", "task25_started", {}, ())
    assert "pg_try_advisory_xact_lock" in fake.execute.call_args.args[0]
    assert fake.add.call_count == 1
    assert fake.begin.return_value.__exit__.call_count == 1
    # A later worker seeing the marker cannot insert another one.
    fake.scalars.return_value = [SimpleNamespace(entity_id=RUN, action="task25_started", changes_json="{}")]
    with pytest.raises(RuntimeError, match="already claimed"):
        ns["_record"](engine, RUN, "test-org", "test-facility", "task25_started", {}, ())
    assert fake.add.call_count == 1


def test_other_run_cannot_claim_same_facility_checkpoint():
    ns = runner_functions()
    fake = MagicMock(); fake.__enter__.return_value = fake
    fake.execute.return_value.scalar_one.return_value = True
    fake.scalars.return_value = [SimpleNamespace(entity_id="OTHER", action="tag_allocation", changes_json="{}")]
    ns.update(Session=lambda *_: fake, select=MagicMock(), text=lambda sql: sql, AuditEvent=MagicMock())
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    with pytest.raises(RuntimeError, match="Another package run"):
        ns["_record"](engine, RUN, "test-org", "test-facility", "tag_allocation", load(), ())
    fake.add.assert_not_called()
