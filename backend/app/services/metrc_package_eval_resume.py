from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_evaluation_lifecycle import execute_lifecycle_evaluation_action
from ..auth import RequestContext
from ..config import Settings
from .metrc_context import resolve_metrc_context
from .metrc_resume_diagnostics import _get, _paged, _reference, _rows, _scope_user_id

EVALUATION_BASE_RUN = "DL-EVAL-20260912-RESUME-01"
SOURCE_ITEM_SUFFIX = "-Clones"
TIMEOUT_SECONDS = 30


class MetrcPackageResumeError(RuntimeError):
    pass


def _audit_rows(engine: Engine, run_id: str) -> list[AuditEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "metrc_package_eval_resume",
                    AuditEvent.entity_id == run_id,
                ).order_by(AuditEvent.occurred_at.asc())
            )
        )


def _audit(engine: Engine, *, run_id: str, organization_id: str, facility_id: str, action: str, payload: dict[str, Any]) -> None:
    clean = dict(payload)
    clean["run_id"] = run_id
    clean["secrets_included"] = False
    with Session(engine) as session:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="metrc_package_eval_resume",
                entity_id=run_id,
                action=action,
                actor="system:metrc-package-eval-resume",
                changes_json=json.dumps(clean, sort_keys=True, default=str),
            )
        )
        session.commit()


def _payload(event: AuditEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.changes_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _facility_context(engine: Engine, settings: Settings) -> tuple[RequestContext, Any]:
    with Session(engine) as session:
        configs = list(
            session.scalars(
                select(IntegrationConfiguration).where(
                    IntegrationConfiguration.provider == "metrc",
                    IntegrationConfiguration.scope_type == "user",
                    IntegrationConfiguration.status == "connected",
                    IntegrationConfiguration.encrypted_secret != "",
                    IntegrationConfiguration.organization_id.is_not(None),
                    IntegrationConfiguration.facility_id.is_not(None),
                )
            )
        )
    candidates: list[tuple[RequestContext, Any]] = []
    for row in configs:
        context = RequestContext(
            _scope_user_id(row),
            str(row.organization_id or ""),
            str(row.facility_id or ""),
            "dev",
        )
        _service, metrc = resolve_metrc_context(engine, settings, context)
        if not (
            metrc.configured
            and metrc.trusted_mapping
            and metrc.environment == "sandbox"
            and metrc.state.upper() == "MA"
            and metrc.user_api_key
            and metrc.integrator_api_key
        ):
            continue
        base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
        if state != "MA" or not base_url:
            continue
        status, packages = _paged(base_url, "packages/v2/active", (metrc.integrator_api_key, metrc.user_api_key), metrc.license_number)
        if status != 200:
            continue
        source_matches = [
            row for row in packages
            if str(((row.get("Item") or {}) if isinstance(row.get("Item"), dict) else {}).get("Name") or row.get("ItemName") or "").strip()
            == f"{EVALUATION_BASE_RUN}{SOURCE_ITEM_SUFFIX}"
            and str(row.get("PackageType") or row.get("packageType") or "").strip().casefold() == "immatureplant"
            and float(row.get("Quantity") or row.get("quantity") or 0) >= 2
            and not bool(row.get("IsFinished") if "IsFinished" in row else row.get("isFinished"))
            and not bool(row.get("IsOnHold") if "IsOnHold" in row else row.get("isOnHold"))
        ]
        if len(source_matches) == 1:
            metrc._resume_source_package = source_matches[0]  # runtime-only helper; never persisted with credentials
            candidates.append((context, metrc))
    if len(candidates) != 1:
        raise MetrcPackageResumeError(f"Expected exactly one trusted MA sandbox facility with the evaluation clone package; found {len(candidates)}.")
    return candidates[0]


def _item_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "name": row.get("Name") or row.get("name"),
        "unit": row.get("UnitOfMeasureName") or row.get("unitOfMeasureName"),
        "quantity_type": row.get("QuantityType") or row.get("quantityType"),
        "category": row.get("ProductCategoryName") or row.get("productCategoryName"),
        "category_type": row.get("ProductCategoryType") or row.get("productCategoryType"),
    }


def _tag_labels(payload: Any) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            token = value.strip()
            if token and token not in found and len(token) >= 8:
                found.append(token)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key in ("Label", "label", "Tag", "tag", "Tags", "tags", "Labels", "labels", "Data", "data", "Results", "results"):
                if key in value:
                    visit(value[key])
    visit(payload)
    return found


def _available_package_tags(base_url: str, auth: tuple[str, str], license_number: str) -> list[str]:
    status, payload = _get(base_url, "tags/v2/package/available", auth, {"licenseNumber": license_number})
    if status != 200:
        raise MetrcPackageResumeError(f"Available package-tag read returned HTTP {status}.")
    labels = _tag_labels(payload)
    if not labels:
        rows = _rows(payload)
        labels = [str(row.get("Label") or row.get("label") or "").strip() for row in rows]
        labels = [label for label in labels if label]
    return labels


def _tag_type_name(base_url: str, auth: tuple[str, str], license_number: str) -> str:
    status, rows = _reference(base_url, "sandbox/v2/tagtypes", auth, license_number)
    if status != 200:
        raise MetrcPackageResumeError(f"Sandbox tag-type discovery returned HTTP {status}.")
    names = []
    for row in rows:
        name = str(row.get("Name") or row.get("name") or row.get("TagType") or row.get("tagType") or "").strip()
        if name:
            names.append(name)
    package_names = [name for name in names if "package" in name.casefold() and "plant" not in name.casefold()]
    if not package_names:
        raise MetrcPackageResumeError("No package tag type was returned by the MA sandbox.")
    return package_names[0]


def _generate_fresh_package_tag(base_url: str, auth: tuple[str, str], license_number: str, tag_type: str, before: list[str]) -> tuple[int, str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/sandbox/v2/facility/tags",
        auth=auth,
        params={"licenseNumber": license_number},
        json={"TagType": tag_type, "Count": 1},
        timeout=TIMEOUT_SECONDS,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    status = int(response.status_code)
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = None
    if status != 200:
        return status, "", body
    labels = _tag_labels(body)
    if len(labels) == 1:
        return status, labels[0], body
    after = _available_package_tags(base_url, auth, license_number)
    new_labels = [label for label in after if label not in set(before)]
    return status, new_labels[0] if len(new_labels) == 1 else "", body


def _source_record(metrc: Any) -> dict[str, Any]:
    value = getattr(metrc, "_resume_source_package", None)
    if not isinstance(value, dict):
        raise MetrcPackageResumeError("Evaluation source package was not retained from preflight.")
    return value


def _package_label_from_evidence(evidence: dict[str, Any], fallback: str) -> str:
    readback = evidence.get("readback")
    if isinstance(readback, dict):
        for record in readback.get("records") or []:
            if not isinstance(record, dict):
                continue
            source = record.get("source") if isinstance(record.get("source"), dict) else {}
            label = str(source.get("Label") or source.get("label") or record.get("label") or "").strip()
            if label:
                return label
    return fallback


def run_package_tasks_25_26(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    """Execute workbook package tasks 25-26 from the verified existing clone package.

    The workbook explicitly permits task 25 to use an existing package. This runner
    therefore does not depend on the blocked harvest chain. It never executes task
    27/28/29, preserving all downstream consumers.
    """
    run_id = str(run_id or "").strip()[:64]
    if not run_id:
        raise MetrcPackageResumeError("A package evaluation run ID is required.")
    events = _audit_rows(engine, run_id)
    evidence_25 = next((_payload(row) for row in events if row.action == "task25_evidence"), None)
    evidence_26 = next((_payload(row) for row in events if row.action == "task26_evidence"), None)
    if evidence_25 and evidence_26 and evidence_25.get("passed") is True and evidence_26.get("passed") is True:
        return {"run_id": run_id, "status": "already_completed", "task25": evidence_25, "task26": evidence_26}

    context, metrc = _facility_context(engine, settings)
    organization_id = context.organization_id
    facility_id = context.facility_id
    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if state != "MA" or not base_url:
        raise MetrcPackageResumeError("MA sandbox routing is unavailable.")
    auth = (metrc.integrator_api_key, metrc.user_api_key)
    source = _source_record(metrc)
    source_label = str(source.get("Label") or source.get("label") or "").strip()
    source_item = str(((source.get("Item") or {}) if isinstance(source.get("Item"), dict) else {}).get("Name") or source.get("ItemName") or "").strip()
    source_unit = str(source.get("UnitOfMeasureName") or source.get("UnitOfMeasure") or "").strip()
    source_location = str(((source.get("Location") or {}) if isinstance(source.get("Location"), dict) else {}).get("Name") or source.get("LocationName") or "").strip()
    if not source_label or not source_item or source_unit.casefold() != "each":
        raise MetrcPackageResumeError("The verified clone source package is not a usable Each-based package.")

    items_status, items = _paged(base_url, "items/v2/active", auth, metrc.license_number)
    if items_status != 200:
        raise MetrcPackageResumeError(f"Active-item preflight returned HTTP {items_status}.")
    item_summaries = [_item_summary(row) for row in items]
    alternate = next(
        (
            row for row in item_summaries
            if str(row.get("name") or "") != source_item
            and str(row.get("unit") or "").casefold() == "each"
            and str(row.get("quantity_type") or "").casefold() == "countbased"
            and EVALUATION_BASE_RUN.casefold() in str(row.get("name") or "").casefold()
        ),
        None,
    )
    if alternate is None:
        alternate = next(
            (
                row for row in item_summaries
                if str(row.get("name") or "") != source_item
                and str(row.get("unit") or "").casefold() == "each"
                and str(row.get("quantity_type") or "").casefold() == "countbased"
            ),
            None,
        )
    if not alternate or not alternate.get("name"):
        raise MetrcPackageResumeError("No distinct active CountBased/Each item is available for workbook task 26; no mutation was sent.")

    if evidence_25 and evidence_25.get("passed") is True:
        new_tag = _package_label_from_evidence(evidence_25, "")
        provider_id = str(evidence_25.get("provider_id") or "").strip()
    else:
        plan = next((_payload(row) for row in events if row.action == "plan"), None)
        tag_event = next((_payload(row) for row in events if row.action == "tag_generated"), None)
        before: list[str]
        if plan:
            if plan.get("source_label") != source_label or plan.get("alternate_item") != alternate.get("name"):
                raise MetrcPackageResumeError("Existing package-evaluation plan no longer matches live provider state; refusing to mutate.")
            before = [str(value) for value in plan.get("available_tags_before") or []]
        else:
            before = _available_package_tags(base_url, auth, metrc.license_number)
            _audit(
                engine,
                run_id=run_id,
                organization_id=organization_id,
                facility_id=facility_id,
                action="plan",
                payload={
                    "source_label": source_label,
                    "source_item": source_item,
                    "source_unit": source_unit,
                    "source_location": source_location,
                    "alternate_item": alternate.get("name"),
                    "alternate_item_id": alternate.get("id"),
                    "available_tags_before": before,
                    "workbook_dependency_waiver": "Task 25 uses an existing package as explicitly allowed by the Packages worksheet; harvest task 21 is not required for this execution path.",
                },
            )

        if tag_event and tag_event.get("tag"):
            new_tag = str(tag_event["tag"])
        else:
            current = _available_package_tags(base_url, auth, metrc.license_number)
            delta = [label for label in current if label not in set(before)]
            if len(delta) == 1:
                new_tag = delta[0]
                generation_status = 200
                generation_response = {"reconciled_from_available_tag_delta": True}
            elif len(delta) > 1:
                raise MetrcPackageResumeError("Multiple new package tags appeared since the saved plan; tag ownership is ambiguous and no package mutation was sent.")
            else:
                tag_type = _tag_type_name(base_url, auth, metrc.license_number)
                generation_status, new_tag, generation_response = _generate_fresh_package_tag(
                    base_url, auth, metrc.license_number, tag_type, before
                )
            _audit(
                engine,
                run_id=run_id,
                organization_id=organization_id,
                facility_id=facility_id,
                action="tag_generated",
                payload={
                    "http_status": generation_status,
                    "tag": new_tag,
                    "response": generation_response,
                    "mutations_sent": 1,
                    "mutation_type": "sandbox_prerequisite_tag_generation",
                },
            )
            if generation_status != 200 or not new_tag:
                raise MetrcPackageResumeError(f"Sandbox package-tag generation did not produce one attributable tag (HTTP {generation_status}).")

        evidence_25 = execute_lifecycle_evaluation_action(
            operation_type="package_create",
            payload={
                "tag": new_tag,
                "item": source_item,
                "quantity": 1,
                "unit_of_measure": source_unit,
                "actual_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
                "ingredients": [{"package": source_label, "quantity": 1, "unit_of_measure": source_unit}],
                "location": source_location,
                "use_same_item": True,
                "is_production_batch": False,
                "is_trade_sample": False,
                "is_donation": False,
                "product_requires_remediation": False,
                "required_lab_test_batches": False,
            },
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            state="MA",
            environment="sandbox",
        )
        evidence_25["task_number"] = 25
        evidence_25["sheet"] = "Packages"
        evidence_25["step"] = "Step 1"
        evidence_25["dependency_waiver"] = "Existing package path allowed by regulator workbook; task 21 is not intrinsic to task 25."
        _audit(engine, run_id=run_id, organization_id=organization_id, facility_id=facility_id, action="task25_evidence", payload=evidence_25)
        if evidence_25.get("passed") is not True:
            return {"run_id": run_id, "status": "task25_failed", "task25": evidence_25}
        provider_id = str(evidence_25.get("provider_id") or "").strip()

    new_label = _package_label_from_evidence(evidence_25, new_tag)
    if not new_label or not provider_id:
        raise MetrcPackageResumeError("Task 25 passed without a durable package identity; task 26 was not attempted.")

    if evidence_26 and evidence_26.get("passed") is True:
        return {"run_id": run_id, "status": "complete", "task25": evidence_25, "task26": evidence_26}

    evidence_26 = execute_lifecycle_evaluation_action(
        operation_type="package_item",
        payload={
            "package_id": int(provider_id),
            "label": new_label,
            "item": str(alternate["name"]),
        },
        license_number=metrc.license_number,
        integrator_api_key=metrc.integrator_api_key,
        user_api_key=metrc.user_api_key,
        state="MA",
        environment="sandbox",
    )
    evidence_26["task_number"] = 26
    evidence_26["sheet"] = "Packages"
    evidence_26["step"] = "Step 2"
    _audit(engine, run_id=run_id, organization_id=organization_id, facility_id=facility_id, action="task26_evidence", payload=evidence_26)
    return {
        "run_id": run_id,
        "status": "complete" if evidence_26.get("passed") is True else "task26_failed",
        "task25": evidence_25,
        "task26": evidence_26,
    }
