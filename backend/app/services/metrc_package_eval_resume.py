"""Explicitly scoped, restart-safe MA sandbox package evaluation (tasks 25-26)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_evaluation_lifecycle import execute_lifecycle_evaluation_action
from services.metrc_resume_response import (
    ResumeResponseError, collection_values, numeric, object_rows, package_record,
    reference_names, total_pages, validate_sandbox_url, verify_package,
)
from ..auth import RequestContext
from ..config import Settings
from .metrc_context import resolve_metrc_context

EVALUATION_BASE_RUN = "DL-EVAL-20260912-RESUME-01"
SOURCE_ITEM = f"{EVALUATION_BASE_RUN}-Clones"
ENTITY_TYPE = "metrc_package_eval_resume"
TAG_PATTERN = re.compile(r"^[A-Z0-9]{20,32}$")
TIMEOUT_SECONDS = 20


class MetrcPackageResumeError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configuration(run_id: str) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", run_id):
        raise MetrcPackageResumeError("A 1-36 character diagnostic run ID is required; IDs are never truncated.")
    names = {
        "organization_id": "METRC_PACKAGE_EVAL_ORGANIZATION_ID",
        "facility_id": "METRC_PACKAGE_EVAL_FACILITY_ID",
        "source_label": "METRC_PACKAGE_EVAL_SOURCE_LABEL",
        "source_id": "METRC_PACKAGE_EVAL_SOURCE_ID",
    }
    config = {key: str(os.environ.get(name) or "").strip() for key, name in names.items()}
    if any(not value for value in config.values()):
        raise MetrcPackageResumeError("Explicit organization, facility and source package identity are required.")
    if not TAG_PATTERN.fullmatch(config["source_label"]) or not config["source_id"].isdigit():
        raise MetrcPackageResumeError("Invalid explicit source package identity.")
    config["mode"] = str(os.environ.get("METRC_PACKAGE_EVAL_MODE") or "preflight").strip()
    if config["mode"] not in {"preflight", "execute"}:
        raise MetrcPackageResumeError("Package evaluation mode must be preflight or execute.")
    if config["mode"] == "execute" and os.environ.get("METRC_PACKAGE_EVAL_APPROVAL") != run_id:
        raise MetrcPackageResumeError("Execution requires approval bound to this exact run ID.")
    return config


def _sanitize(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize(item, secrets) for key, item in value.items()
                if re.sub(r"[^a-z]", "", str(key).lower()) not in {
                    "authorization", "password", "apikey", "userapikey", "vendorapikey",
                    "integratorapikey", "userkey", "vendorkey", "xmetrckey"}}
    if isinstance(value, list):
        return [_sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


@contextmanager
def _facility_lock(engine: Engine, organization_id: str, facility_id: str):
    if engine.dialect.name != "postgresql":
        raise MetrcPackageResumeError("Live execution requires the configured PostgreSQL database.")
    # Transaction-scoped locking remains correct with Supabase transaction pooling.
    token = f"metrc-package-eval:{organization_id}:{facility_id}:{EVALUATION_BASE_RUN}"
    key = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big", signed=True)
    with engine.begin() as connection:
        locked = connection.execute(text("select pg_try_advisory_xact_lock(:key)"), {"key": key}).scalar_one()
        if not locked:
            raise MetrcPackageResumeError("Another package evaluation owns the facility execution lock.")
        yield


def _events(engine: Engine, run_id: str, org: str, facility: str) -> dict[str, dict]:
    with Session(engine) as session:
        rows = session.scalars(select(AuditEvent).where(
            AuditEvent.entity_type == ENTITY_TYPE, AuditEvent.entity_id == run_id,
            AuditEvent.organization_id == org, AuditEvent.facility_id == facility,
        ).order_by(AuditEvent.occurred_at))
        return {row.action: json.loads(row.changes_json) for row in rows}


def _record(engine: Engine, run_id: str, org: str, facility: str,
            action: str, payload: dict, secrets: tuple[str, ...]) -> None:
    value = _sanitize({**payload, "run_id": run_id, "evaluation_run_id": EVALUATION_BASE_RUN,
                       "state": "MA", "environment": "sandbox"}, secrets)
    with Session(engine) as session, session.begin():
        session.add(AuditEvent(
            organization_id=org, facility_id=facility, entity_type=ENTITY_TYPE,
            entity_id=run_id, action=action, actor="system:approved-metrc-package-evaluation",
            changes_json=json.dumps(value, sort_keys=True, default=str),
        ))


def _once(name: str, events: dict, record: Callable, action: Callable) -> dict:
    """Never reissue a submitted mutation, including after a missing response."""
    if name not in {"tag_generation", "task25", "task26"}:
        raise MetrcPackageResumeError("Unreviewed evaluation operation.")
    if name + "_result" in events:
        return events[name + "_result"]
    if name + "_started" in events:
        return {"passed": False, "stage": "outcome_uncertain", "retry_blocked": True}
    marker = {"started_at": _now(), "passed": False}
    record(name + "_started", marker)
    events[name + "_started"] = marker
    try:
        result = action()
    except Exception as exc:
        result = {"passed": False, "stage": "outcome_uncertain", "retry_blocked": True,
                  "error_type": type(exc).__name__, "completed_at": _now()}
    record(name + "_result", result)
    events[name + "_result"] = result
    return result


class _Provider:
    def __init__(self, metrc):
        origin, state = resolve_metrc_base_url("MA", environment="sandbox")
        if state != "MA":
            raise MetrcPackageResumeError("Massachusetts routing is required.")
        self.origin = validate_sandbox_url(origin or "")
        self.metrc = metrc

    def get(self, path: str, *, scoped: bool = True, query: dict | None = None) -> tuple[Any, dict]:
        allowed = {"facilities/v2/", "packages/v2/active", "items/v2/active",
                   "tags/v2/package/available", "sandbox/v2/tagtypes", "sales/v2/customertypes"}
        if path not in allowed and not re.fullmatch(r"packages/v2/[A-Z0-9]{20,32}", path):
            raise MetrcPackageResumeError("Unreviewed diagnostic read path.")
        params = {"licenseNumber": self.metrc.license_number} if scoped else {}
        params.update(query or {})
        started = _now()
        response = requests.get(self.origin + "/" + path, params=params,
            auth=(self.metrc.integrator_api_key, self.metrc.user_api_key),
            headers={"Accept": "application/json"}, timeout=TIMEOUT_SECONDS,
            allow_redirects=False)
        evidence = {"method": "GET", "path": path, "query": params,
                    "started_at": started, "completed_at": _now(), "http_status": response.status_code}
        if response.status_code != 200:
            raise MetrcPackageResumeError(f"Read {path} returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError as exc:
            raise MetrcPackageResumeError("Provider read returned invalid JSON.") from exc
        evidence["response"] = body
        return body, evidence

    def pages(self, path: str) -> tuple[list[dict], list[dict]]:
        records: list[dict] = []
        captures: list[dict] = []
        page = maximum = 1
        expected_pages = None
        while page <= maximum:
            body, evidence = self.get(path, query={"pageNumber": page, "pageSize": 20})
            maximum = total_pages(body)
            if expected_pages is not None and maximum != expected_pages:
                raise MetrcPackageResumeError("Provider pagination changed mid-read; completeness is uncertain.")
            expected_pages = maximum
            records.extend(object_rows(body))
            captures.append(evidence)
            page += 1
        return records, captures

    def package(self, label: str) -> tuple[dict, dict]:
        body, evidence = self.get("packages/v2/" + label)
        return package_record(body, label), evidence


def _alternate_item(items: list[dict], source: dict) -> dict:
    source_item = source.get("Item") or {}
    candidates = [item for item in items
        if item.get("Name") != SOURCE_ITEM
        and item.get("ProductCategoryName") == source_item.get("ProductCategoryName") == "Immature Plants"
        and item.get("QuantityType") == "CountBased" and item.get("UnitOfMeasureName") == "Each"
        and item.get("ApprovalStatus") == "Approved"
        and "clone" in str(item.get("Name") or "").lower()
        and (str(item.get("Name") or "").startswith(EVALUATION_BASE_RUN)
             or str(item.get("Name") or "").startswith("DoobieLogic MA Eval"))]
    if not candidates:
        raise MetrcPackageResumeError("No compatible approved evaluation clone item exists for task 26.")
    return sorted(candidates, key=lambda item: str(item["Name"]))[0]


def _generate_tag(provider: _Provider, tag_type: str, before: set[str], record: Callable) -> dict:
    started = _now()
    body = {"TagType": tag_type, "Count": 1}
    response = requests.post(provider.origin + "/sandbox/v2/facility/tags",
        auth=(provider.metrc.integrator_api_key, provider.metrc.user_api_key),
        params={"licenseNumber": provider.metrc.license_number}, json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=TIMEOUT_SECONDS, allow_redirects=False)
    result = {"passed": False, "stage": "prerequisite", "http_status": response.status_code,
              "started_at": started, "completed_at": _now(),
              "request": {"method": "POST", "path": "sandbox/v2/facility/tags", "body": body}}
    result["response"] = response.json() if response.content else None
    record("tag_generation_transport", result)
    returned = result["response"]
    if response.status_code != 200 or not isinstance(returned, dict):
        return result
    labels = returned.get("Labels")
    if not isinstance(labels, list) or len(labels) != 1 or not isinstance(labels[0], str):
        return result
    if returned.get("Count") != 1 or returned.get("TagType") != tag_type:
        return result
    label = labels[0]
    if not TAG_PATTERN.fullmatch(label) or label in before:
        return result
    result.update(passed=True, stage="complete", tag=label)
    return result


def _task(provider: _Provider, number: int, payload: dict, record: Callable,
          *, label: str, item: str, source_label: str = "", source_id: str = "",
          expected_id: str | None = None) -> dict:
    operation = "package_create" if number == 25 else "package_item"
    method = "POST" if number == 25 else "PUT"
    path = "packages/v2/" if number == 25 else "packages/v2/item"

    def transport(verb: str, url: str, **kwargs):
        if verb != method or url != provider.origin + "/" + path:
            raise MetrcPackageResumeError("Evaluation transport escaped the reviewed operation.")
        kwargs["allow_redirects"] = False
        started = _now()
        response = requests.request(verb, url, **kwargs)
        record(f"task{number}_transport", {
            "task_number": number, "started_at": started, "completed_at": _now(),
            "http_status": response.status_code,
            "request": {"method": verb, "path": path, "query": kwargs.get("params"), "body": kwargs.get("json")},
            "response": response.json() if response.content else None,
        })
        return response

    evidence = execute_lifecycle_evaluation_action(
        operation_type=operation, payload=payload, license_number=provider.metrc.license_number,
        integrator_api_key=provider.metrc.integrator_api_key, user_api_key=provider.metrc.user_api_key,
        state="MA", environment="sandbox", request_fn=transport,
    )
    evidence.update(task_number=number, sheet="Packages", step=f"Step {number-24}")
    record(f"task{number}_adapter_result", evidence)
    adapter_verified = evidence.get("passed") is True and evidence.get("http_status") == 200
    evidence["passed"] = False
    if not adapter_verified:
        return evidence
    current, readback = provider.package(label)
    verify_package(current, label=label, item_name=item, quantity=1, unit="Each",
                   provider_id=expected_id or evidence.get("provider_id"))
    evidence["verified_package_readback"] = readback
    if number == 25:
        source, source_readback = provider.package(source_label)
        verify_package(source, label=source_label, item_name=SOURCE_ITEM, quantity=2,
                       unit="Each", provider_id=source_id)
        evidence["verified_source_readback"] = source_readback
    evidence.update(passed=True, stage="complete", postconditions_verified=True,
                    completed_at=_now(), label=label)
    record(f"task{number}_evidence", evidence)
    return evidence


def run_package_tasks_25_26(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    config = _configuration(run_id)
    org, facility = config["organization_id"], config["facility_id"]
    with _facility_lock(engine, org, facility):
        events = _events(engine, run_id, org, facility)
        if "completed" in events:
            return {"status": "already_completed", **events["completed"]}
        with Session(engine) as session:
            configs = list(session.scalars(select(IntegrationConfiguration).where(
                IntegrationConfiguration.organization_id == org,
                IntegrationConfiguration.facility_id == facility,
                IntegrationConfiguration.scope_type == "user", IntegrationConfiguration.provider == "metrc",
                IntegrationConfiguration.status == "connected",
            )))
        if len(configs) != 1:
            raise MetrcPackageResumeError("Exactly one connected integration must match the approved facility.")
        saved = configs[0]
        parts = saved.scope_key.split("|")
        if len(parts) != 2 or not parts[0] or parts[1] != facility:
            raise MetrcPackageResumeError("Saved credential does not match the explicit facility scope.")
        context = RequestContext(parts[0], org, facility, "dev")
        _, metrc = resolve_metrc_context(engine, settings, context)
        if not (metrc.configured and metrc.trusted_mapping and metrc.environment == "sandbox"
                and metrc.state.upper() == "MA" and metrc.status == "connected"):
            raise MetrcPackageResumeError("Trusted MA sandbox credential context is not ready.")
        secrets = (metrc.integrator_api_key, metrc.user_api_key)
        record = lambda action, data: _record(engine, run_id, org, facility, action, data, secrets)
        provider = _Provider(metrc)
        try:
            # Fresh explicit facility discovery must precede every remaining operation.
            facilities, facility_read = provider.get("facilities/v2/", scoped=False)
            selected = [row for row in object_rows(facilities)
                        if str(row.get("LicenseNumber") or (row.get("License") or {}).get("Number") or "") == metrc.license_number]
            if len(selected) != 1:
                raise MetrcPackageResumeError("Authorized facility was absent or ambiguous in fresh discovery.")
            e25 = events.get("task25_result")
            if e25 and e25.get("passed") is not True:
                return {"status": "task25_failed_or_uncertain", "task25": e25}
            source, source_read = provider.package(config["source_label"])
            verify_package(source, label=config["source_label"], item_name=SOURCE_ITEM,
                           quantity=2 if e25 else 3, unit="Each", provider_id=config["source_id"])
            if source.get("PackageType") != "ImmaturePlant":
                raise MetrcPackageResumeError("Source is not the expected current-run immature package.")
            items, _ = provider.pages("items/v2/active")
            alternate = _alternate_item(items, source)
            customer_payload, _ = provider.get("sales/v2/customertypes", scoped=False)
            customers = reference_names(customer_payload)
            type_payload, type_read = provider.get("sandbox/v2/tagtypes")
            types = [row for row in object_rows(type_payload) if row.get("TagInventoryType") == "Package"]
            if len(types) != 1 or not types[0].get("Name"):
                raise MetrcPackageResumeError("An unambiguous package tag type is required.")
            available, _ = provider.pages("tags/v2/package/available")
            before = {str(row.get("Label") or "") for row in available}
            if any(not TAG_PATTERN.fullmatch(label) for label in before):
                raise MetrcPackageResumeError("Available tag response contains an unrecognized label.")
            record("preflight", {"read_only": True, "mutations_sent": 0,
                "source_readback": source_read, "source_id": config["source_id"],
                "alternate_item": alternate, "tag_type_readback": type_read,
                "available_tag_count": len(before), "sales_customer_types": customers,
                "license_number": metrc.license_number,
                "task17_capability": (selected[0].get("FacilityType") or {}).get("CanCreateImmaturePlantPackagesFromPlants"),
                "facility_discovery_http": facility_read["http_status"],
                "dependency_basis": "Packages Step 1 explicitly permits an existing package; tasks 17-24 remain outstanding."})
            if config["mode"] != "execute":
                return {"status": "preflight_complete", "mutations_sent": 0}
            tag = _once("tag_generation", events, record,
                        lambda: _generate_tag(provider, types[0]["Name"], before, record))
            if tag.get("passed") is not True:
                return {"status": "tag_generation_blocked", "prerequisite": tag}
            new_label = tag["tag"]
            location = source.get("LocationName") or (source.get("Location") or {}).get("Name")
            payload = {"tag": new_label, "item": SOURCE_ITEM, "quantity": 1, "unit_of_measure": "Each",
                "actual_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
                "ingredients": [{"package": config["source_label"], "quantity": 1, "unit_of_measure": "Each"}],
                "location": location, "use_same_item": False, "required_lab_test_batches": None}
            e25 = _once("task25", events, record, lambda: _task(provider, 25, payload, record,
                        label=new_label, item=SOURCE_ITEM, source_label=config["source_label"], source_id=config["source_id"]))
            if e25.get("passed") is not True:
                return {"status": "task25_failed_or_uncertain", "task25": e25}
            target, _ = provider.package(new_label)
            verify_package(target, label=new_label, item_name=SOURCE_ITEM, quantity=1,
                           unit="Each", provider_id=e25["provider_id"])
            e26 = _once("task26", events, record, lambda: _task(provider, 26,
                {"package_id": int(e25["provider_id"]), "label": new_label, "item": alternate["Name"]},
                record, label=new_label, item=alternate["Name"], expected_id=e25["provider_id"]))
            status = "complete" if e26.get("passed") is True else "task26_failed_or_uncertain"
            result = {"status": status, "task25": e25, "task26": e26}
            if status == "complete":
                record("completed", result)
            return result
        except Exception as exc:
            message = str(exc) if isinstance(exc, (MetrcPackageResumeError, ResumeResponseError)) else type(exc).__name__
            result = {"status": "blocked", "error_type": type(exc).__name__, "message": message}
            record("blocked", result)
            return result
