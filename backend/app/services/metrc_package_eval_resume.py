from __future__ import annotations

from datetime import datetime
import json
import re
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
from .metrc_context import MetrcContext, resolve_metrc_context
from .metrc_resume_diagnostics import _get, _paged, _reference, _rows, _scope_user_id

EVALUATION_BASE_RUN = "DL-EVAL-20260912-RESUME-01"
SOURCE_ITEM = f"{EVALUATION_BASE_RUN}-Clones"
TIMEOUT_SECONDS = 30
_TAG_RE = re.compile(r"^[A-Z0-9]{20,32}$", re.IGNORECASE)


class MetrcPackageResumeError(RuntimeError):
    pass


def _events(engine: Engine, run_id: str) -> list[AuditEvent]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "metrc_package_eval_resume",
                    AuditEvent.entity_id == run_id,
                ).order_by(AuditEvent.occurred_at.asc())
            )
        )


def _event_payload(event: AuditEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.changes_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _find_event(events: list[AuditEvent], action: str) -> dict[str, Any] | None:
    return next((_event_payload(row) for row in reversed(events) if row.action == action), None)


def _audit(
    engine: Engine,
    *,
    run_id: str,
    organization_id: str,
    facility_id: str,
    action: str,
    payload: dict[str, Any],
) -> None:
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


def _package_item_name(row: dict[str, Any]) -> str:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    return str(item.get("Name") or item.get("name") or row.get("ItemName") or "").strip()


def _package_item_id(row: dict[str, Any]) -> str:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    return str(item.get("Id") or item.get("id") or row.get("ItemId") or "").strip()


def _source_package(row: dict[str, Any]) -> bool:
    return (
        _package_item_name(row) == SOURCE_ITEM
        and str(row.get("PackageType") or row.get("packageType") or "").strip().casefold() == "immatureplant"
        and float(row.get("Quantity") or row.get("quantity") or 0) >= 2
        and not bool(row.get("IsFinished") if "IsFinished" in row else row.get("isFinished"))
        and not bool(row.get("IsOnHold") if "IsOnHold" in row else row.get("isOnHold"))
    )


def _resolve_source_context(
    engine: Engine, settings: Settings
) -> tuple[RequestContext, MetrcContext, dict[str, Any]]:
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

    matches: list[tuple[RequestContext, MetrcContext, dict[str, Any]]] = []
    seen: set[str] = set()
    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if state != "MA" or not base_url or "sandbox" not in base_url.casefold():
        raise MetrcPackageResumeError("Verified MA sandbox routing is unavailable.")

    for config in configs:
        context = RequestContext(
            _scope_user_id(config),
            str(config.organization_id or ""),
            str(config.facility_id or ""),
            "dev",
        )
        _service, metrc = resolve_metrc_context(engine, settings, context)
        if not (
            metrc.configured
            and metrc.trusted_mapping
            and metrc.environment == "sandbox"
            and metrc.state.upper() == "MA"
            and metrc.license_number
            and metrc.user_api_key
            and metrc.integrator_api_key
        ):
            continue
        if metrc.license_number in seen:
            continue
        seen.add(metrc.license_number)
        status, packages = _paged(
            base_url,
            "packages/v2/active",
            (metrc.integrator_api_key, metrc.user_api_key),
            metrc.license_number,
        )
        if status != 200:
            continue
        sources = [row for row in packages if _source_package(row)]
        if len(sources) == 1:
            matches.append((context, metrc, sources[0]))

    if len(matches) != 1:
        raise MetrcPackageResumeError(
            f"Expected exactly one trusted MA sandbox source package for {SOURCE_ITEM}; found {len(matches)}."
        )
    return matches[0]


def _item_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "name": row.get("Name") or row.get("name"),
        "unit": row.get("UnitOfMeasureName") or row.get("unitOfMeasureName"),
        "quantity_type": row.get("QuantityType") or row.get("quantityType"),
        "category": row.get("ProductCategoryName") or row.get("productCategoryName"),
        "category_type": row.get("ProductCategoryType") or row.get("productCategoryType"),
    }


def _alternate_item(items: list[dict[str, Any]], source_item: str) -> dict[str, Any]:
    summaries = [_item_summary(row) for row in items]
    candidates = [
        row
        for row in summaries
        if str(row.get("name") or "").strip() != source_item
        and str(row.get("unit") or "").strip().casefold() == "each"
        and str(row.get("quantity_type") or "").strip().casefold() == "countbased"
    ]
    preferred = [
        row for row in candidates
        if "doobielogic" in str(row.get("name") or "").casefold()
        and "clone" in str(row.get("name") or "").casefold()
    ]
    selected = preferred[0] if preferred else candidates[0] if candidates else None
    if not selected or not selected.get("name"):
        raise MetrcPackageResumeError(
            "No distinct active CountBased/Each item is available for workbook task 26; no package mutation was sent."
        )
    return selected


def _tag_labels(payload: Any) -> list[str]:
    labels: list[str] = []

    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        token = value.strip()
        if _TAG_RE.fullmatch(token) and token not in labels:
            labels.append(token)

    def visit(value: Any) -> None:
        if isinstance(value, str):
            add(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key in ("Label", "label", "Tag", "tag", "Tags", "tags", "Labels", "labels"):
                if key in value:
                    visit(value[key])
            for key in ("Data", "data", "Results", "results"):
                if key in value:
                    visit(value[key])

    visit(payload)
    return labels


def _available_tags(base_url: str, auth: tuple[str, str], license_number: str) -> list[str]:
    status, payload = _get(
        base_url,
        "tags/v2/package/available",
        auth,
        {"licenseNumber": license_number},
    )
    if status != 200:
        raise MetrcPackageResumeError(f"Available package-tag read returned HTTP {status}.")
    labels = _tag_labels(payload)
    if not labels:
        for row in _rows(payload):
            token = str(row.get("Label") or row.get("label") or "").strip()
            if _TAG_RE.fullmatch(token) and token not in labels:
                labels.append(token)
    return labels


def _package_tag_type(base_url: str, auth: tuple[str, str], license_number: str) -> str:
    status, rows = _reference(base_url, "sandbox/v2/tagtypes", auth, license_number)
    if status != 200:
        raise MetrcPackageResumeError(f"Sandbox tag-type discovery returned HTTP {status}.")
    names = [
        str(row.get("Name") or row.get("name") or row.get("TagType") or row.get("tagType") or "").strip()
        for row in rows
    ]
    candidates = [name for name in names if "package" in name.casefold() and "plant" not in name.casefold()]
    if not candidates:
        raise MetrcPackageResumeError("MA sandbox returned no package tag type; no package mutation was sent.")
    return candidates[0]


def _fresh_tag(
    base_url: str,
    auth: tuple[str, str],
    license_number: str,
    before: list[str],
) -> tuple[int, str, Any]:
    tag_type = _package_tag_type(base_url, auth, license_number)
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
        response_payload = response.json() if response.content else None
    except ValueError:
        response_payload = None
    if status != 200:
        return status, "", response_payload
    direct = _tag_labels(response_payload)
    if len(direct) == 1:
        return status, direct[0], response_payload
    after = _available_tags(base_url, auth, license_number)
    delta = [label for label in after if label not in set(before)]
    return status, delta[0] if len(delta) == 1 else "", response_payload


def _provider_package_by_label(
    base_url: str,
    auth: tuple[str, str],
    license_number: str,
    label: str,
) -> tuple[int, dict[str, Any] | None]:
    status, payload = _get(
        base_url,
        f"packages/v2/{label}",
        auth,
        {"licenseNumber": license_number},
    )
    if status != 200:
        return status, None
    if isinstance(payload, dict) and not isinstance(payload.get("Data"), list):
        return status, payload
    rows = _rows(payload)
    return status, rows[0] if len(rows) == 1 else None


def _label_from_evidence(evidence: dict[str, Any], fallback: str) -> str:
    readback = evidence.get("readback")
    if isinstance(readback, dict):
        for record in readback.get("records") or []:
            if not isinstance(record, dict):
                continue
            source = record.get("source") if isinstance(record.get("source"), dict) else {}
            token = str(source.get("Label") or source.get("label") or record.get("label") or "").strip()
            if token:
                return token
    return fallback


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def run_package_tasks_25_26(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    """Run workbook tasks 25-26 using the regulator-permitted existing-package path.

    The Packages worksheet permits task 25 to source from an existing package.
    This runner intentionally stops after task 26 so downstream package finalization
    cannot consume inventory needed by lab, sales, delivery, or template tasks.
    """
    run_id = str(run_id or "").strip()[:64]
    if not run_id:
        raise MetrcPackageResumeError("A package evaluation run ID is required.")

    events = _events(engine, run_id)
    e25 = _find_event(events, "task25_evidence")
    e26 = _find_event(events, "task26_evidence")
    if e25 and e26 and e25.get("passed") is True and e26.get("passed") is True:
        return {"run_id": run_id, "status": "already_completed", "task25": e25, "task26": e26}

    context, metrc, source = _resolve_source_context(engine, settings)
    organization_id = context.organization_id
    facility_id = context.facility_id
    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if state != "MA" or not base_url:
        raise MetrcPackageResumeError("Verified MA sandbox route is unavailable.")
    auth = (metrc.integrator_api_key, metrc.user_api_key)

    source_label = str(source.get("Label") or source.get("label") or "").strip()
    source_item = _package_item_name(source)
    source_unit = str(source.get("UnitOfMeasureName") or source.get("UnitOfMeasure") or "").strip()
    location = source.get("Location") if isinstance(source.get("Location"), dict) else {}
    source_location = str(location.get("Name") or location.get("name") or source.get("LocationName") or "").strip()
    if not source_label or source_item != SOURCE_ITEM or source_unit.casefold() != "each":
        raise MetrcPackageResumeError("Fresh provider preflight no longer matches the expected evaluation clone package.")

    items_status, items = _paged(base_url, "items/v2/active", auth, metrc.license_number)
    if items_status != 200:
        raise MetrcPackageResumeError(f"Active-item preflight returned HTTP {items_status}.")
    alternate = _alternate_item(items, source_item)

    plan = _find_event(events, "plan")
    if plan:
        if plan.get("source_label") != source_label or plan.get("alternate_item") != alternate.get("name"):
            raise MetrcPackageResumeError("Saved task25 plan no longer matches live provider state; refusing mutation.")
        before = [str(value) for value in plan.get("available_tags_before") or []]
    else:
        before = _available_tags(base_url, auth, metrc.license_number)
        _audit(
            engine,
            run_id=run_id,
            organization_id=organization_id,
            facility_id=facility_id,
            action="plan",
            payload={
                "source_label": source_label,
                "source_provider_id": source.get("Id") or source.get("id"),
                "source_item": source_item,
                "source_quantity": source.get("Quantity") or source.get("quantity"),
                "source_unit": source_unit,
                "source_location": source_location,
                "alternate_item": alternate.get("name"),
                "alternate_item_id": alternate.get("id"),
                "available_tags_before": before,
                "dependency_basis": "Packages worksheet explicitly permits task 25 to create from another existing package; task 21 is not intrinsic on this path.",
            },
        )
        events = _events(engine, run_id)

    tag_event = _find_event(events, "tag_generated")
    if tag_event and tag_event.get("tag"):
        new_tag = str(tag_event["tag"])
    else:
        current = _available_tags(base_url, auth, metrc.license_number)
        delta = [label for label in current if label not in set(before)]
        if len(delta) > 1:
            raise MetrcPackageResumeError("More than one new package tag appeared after the saved plan; ownership is ambiguous.")
        if len(delta) == 1:
            generation_status, new_tag, generation_response = 200, delta[0], {"reconciled_from_tag_delta": True}
        else:
            generation_status, new_tag, generation_response = _fresh_tag(
                base_url, auth, metrc.license_number, before
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
                "mutation_type": "sandbox_prerequisite_tag_generation",
            },
        )
        if generation_status != 200 or not new_tag:
            raise MetrcPackageResumeError(
                f"Fresh package-tag generation did not yield exactly one attributable tag (HTTP {generation_status})."
            )

    if e25 is not None and e25.get("passed") is not True:
        return {"run_id": run_id, "status": "task25_failed", "task25": e25}

    if e25 is None:
        attempt = _find_event(events, "task25_attempt_started")
        if attempt:
            status, existing = _provider_package_by_label(base_url, auth, metrc.license_number, new_tag)
            if status == 200 and existing:
                _audit(
                    engine,
                    run_id=run_id,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    action="task25_outcome_uncertain",
                    payload={"tag": new_tag, "provider_id": existing.get("Id") or existing.get("id"), "message": "Package exists but original write evidence is incomplete; blind retry blocked."},
                )
                return {"run_id": run_id, "status": "task25_outcome_uncertain"}
            if status not in {404, 410}:
                return {"run_id": run_id, "status": "task25_reconciliation_required", "readback_http": status}

        _audit(
            engine,
            run_id=run_id,
            organization_id=organization_id,
            facility_id=facility_id,
            action="task25_attempt_started",
            payload={"tag": new_tag, "source_label": source_label, "source_quantity": 1, "source_unit": source_unit},
        )
        e25 = execute_lifecycle_evaluation_action(
            operation_type="package_create",
            payload={
                "tag": new_tag,
                "item": source_item,
                "quantity": 1,
                "unit_of_measure": source_unit,
                "actual_date": _today(),
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
        e25["task_number"] = 25
        e25["sheet"] = "Packages"
        e25["step"] = "Step 1"
        e25["dependency_basis"] = "Regulator workbook existing-package path."
        _audit(
            engine,
            run_id=run_id,
            organization_id=organization_id,
            facility_id=facility_id,
            action="task25_evidence",
            payload=e25,
        )
        if e25.get("passed") is not True:
            return {"run_id": run_id, "status": "task25_failed", "task25": e25}

    provider_id = str(e25.get("provider_id") or "").strip()
    new_label = _label_from_evidence(e25, new_tag)
    if not provider_id or not new_label:
        raise MetrcPackageResumeError("Task 25 lacks exact package identity; task 26 will not execute.")

    if e26 is not None:
        return {
            "run_id": run_id,
            "status": "complete" if e26.get("passed") is True else "task26_failed",
            "task25": e25,
            "task26": e26,
        }

    attempt26 = _find_event(events, "task26_attempt_started")
    if attempt26:
        status, existing = _provider_package_by_label(base_url, auth, metrc.license_number, new_label)
        if status == 200 and existing and _package_item_name(existing) == str(alternate["name"]):
            _audit(
                engine,
                run_id=run_id,
                organization_id=organization_id,
                facility_id=facility_id,
                action="task26_outcome_uncertain",
                payload={"label": new_label, "provider_id": provider_id, "item": alternate["name"], "message": "Target item is already present but original PUT evidence is incomplete; blind retry blocked."},
            )
            return {"run_id": run_id, "status": "task26_outcome_uncertain", "task25": e25}

    _audit(
        engine,
        run_id=run_id,
        organization_id=organization_id,
        facility_id=facility_id,
        action="task26_attempt_started",
        payload={"label": new_label, "provider_id": provider_id, "target_item": alternate["name"]},
    )
    e26 = execute_lifecycle_evaluation_action(
        operation_type="package_item",
        payload={"package_id": int(provider_id), "label": new_label, "item": str(alternate["name"])},
        license_number=metrc.license_number,
        integrator_api_key=metrc.integrator_api_key,
        user_api_key=metrc.user_api_key,
        state="MA",
        environment="sandbox",
    )
    e26["task_number"] = 26
    e26["sheet"] = "Packages"
    e26["step"] = "Step 2"
    _audit(
        engine,
        run_id=run_id,
        organization_id=organization_id,
        facility_id=facility_id,
        action="task26_evidence",
        payload=e26,
    )
    return {
        "run_id": run_id,
        "status": "complete" if e26.get("passed") is True else "task26_failed",
        "task25": e25,
        "task26": e26,
    }
