"""One-shot MA sandbox prerequisite for package evaluation task 26.

The workbook package-item step requires a second compatible Item. The current
resume run only has the source ``Immature Plants`` item, so this helper creates
one distinct, run-owned alternate clone item through the existing reviewed
master-data evaluation adapter. It is runtime-gated by an exact approval-bound
run ID and is idempotent by exact provider name/readback.
"""
from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationConfiguration
from services.metrc_evaluation_master_data import execute_master_data_evaluation_action
from ..auth import RequestContext
from ..config import Settings
from .metrc_context import resolve_metrc_context
from . import metrc_package_eval_resume as package_runner

EVALUATION_BASE_RUN = package_runner.EVALUATION_BASE_RUN
ALT_ITEM_NAME = f"{EVALUATION_BASE_RUN}-Clones-Alt"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,48}$")


class MetrcPackageAltItemError(RuntimeError):
    pass


def _configuration(run_id: str) -> dict[str, str]:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise MetrcPackageAltItemError("A valid one-shot run ID is required.")
    if os.environ.get("METRC_PACKAGE_ALT_ITEM_APPROVAL") != run_id:
        raise MetrcPackageAltItemError("Alternate-item creation requires approval bound to the exact run ID.")
    names = {
        "organization_id": "METRC_PACKAGE_EVAL_ORGANIZATION_ID",
        "facility_id": "METRC_PACKAGE_EVAL_FACILITY_ID",
        "source_label": "METRC_PACKAGE_EVAL_SOURCE_LABEL",
        "source_id": "METRC_PACKAGE_EVAL_SOURCE_ID",
    }
    config = {key: str(os.environ.get(name) or "").strip() for key, name in names.items()}
    if any(not value for value in config.values()):
        raise MetrcPackageAltItemError("Explicit organization, facility, and source package identity are required.")
    return config


def _metrc_context(engine: Engine, settings: Settings, org: str, facility: str):
    with Session(engine) as session:
        configs = list(session.scalars(select(IntegrationConfiguration).where(
            IntegrationConfiguration.organization_id == org,
            IntegrationConfiguration.facility_id == facility,
            IntegrationConfiguration.scope_type == "user",
            IntegrationConfiguration.provider == "metrc",
            IntegrationConfiguration.status == "connected",
        )))
    if len(configs) != 1:
        raise MetrcPackageAltItemError("Exactly one connected Metrc integration must match the approved facility.")
    parts = configs[0].scope_key.split("|")
    if len(parts) != 2 or not parts[0] or parts[1] != facility:
        raise MetrcPackageAltItemError("Saved credential does not match the explicit facility scope.")
    context = RequestContext(parts[0], org, facility, "dev")
    _, metrc = resolve_metrc_context(engine, settings, context)
    if not (
        metrc.configured
        and metrc.trusted_mapping
        and metrc.environment == "sandbox"
        and metrc.state.upper() == "MA"
        and metrc.status == "connected"
    ):
        raise MetrcPackageAltItemError("Trusted Massachusetts sandbox credential context is not ready.")
    return metrc


def _validate_candidate(item: dict[str, Any], *, strain_name: str) -> dict[str, Any]:
    if str(item.get("Name") or "") != ALT_ITEM_NAME:
        raise MetrcPackageAltItemError("Alternate item identity mismatch.")
    if str(item.get("ProductCategoryName") or "") != "Immature Plants":
        raise MetrcPackageAltItemError("Alternate item is not an Immature Plants item.")
    if str(item.get("QuantityType") or "") != "CountBased":
        raise MetrcPackageAltItemError("Alternate item is not count based.")
    if str(item.get("UnitOfMeasureName") or "") != "Each":
        raise MetrcPackageAltItemError("Alternate item does not use Each.")
    if str(item.get("ApprovalStatus") or "") != "Approved":
        raise MetrcPackageAltItemError("Alternate item is not provider-approved.")
    if strain_name and str(item.get("StrainName") or "") != strain_name:
        raise MetrcPackageAltItemError("Alternate item strain does not match the source package item.")
    return item


def run_prepare_alternate_item(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    config = _configuration(run_id)
    metrc = _metrc_context(engine, settings, config["organization_id"], config["facility_id"])
    provider = package_runner._Provider(metrc)

    source, source_read = provider.package(config["source_label"])
    package_runner.verify_package(
        source,
        label=config["source_label"],
        item_name=package_runner.SOURCE_ITEM,
        quantity=3,
        unit="Each",
        provider_id=config["source_id"],
    )
    if source.get("PackageType") != "ImmaturePlant":
        raise MetrcPackageAltItemError("Source package is not the expected current-run immature package.")
    source_item = source.get("Item") or {}
    strain_name = str(source_item.get("StrainName") or "").strip()
    if not strain_name:
        raise MetrcPackageAltItemError("Source package item does not expose a strain for safe alternate-item creation.")

    items, _ = provider.pages("items/v2/active")
    existing = [item for item in items if str(item.get("Name") or "") == ALT_ITEM_NAME]
    if len(existing) > 1:
        raise MetrcPackageAltItemError("Multiple alternate items share the run-owned name; execution is ambiguous.")
    if len(existing) == 1:
        candidate = _validate_candidate(existing[0], strain_name=strain_name)
        return {
            "status": "already_prepared",
            "passed": True,
            "provider_id": str(candidate.get("Id") or ""),
            "name": ALT_ITEM_NAME,
            "source_readback_http": source_read.get("http_status"),
        }

    evidence = execute_master_data_evaluation_action(
        operation_type="item_create",
        payload={
            "name": ALT_ITEM_NAME,
            "item_category": "Immature Plants",
            "unit_of_measure": "Each",
            "strain": strain_name,
        },
        license_number=metrc.license_number,
        integrator_api_key=metrc.integrator_api_key,
        user_api_key=metrc.user_api_key,
        state="MA",
        environment="sandbox",
    )
    if evidence.get("passed") is not True or int(evidence.get("http_status") or 0) != 200:
        return {
            "status": "create_failed",
            "passed": False,
            "http_status": int(evidence.get("http_status") or 0),
            "stage": evidence.get("stage"),
            "message": evidence.get("message"),
        }

    items_after, _ = provider.pages("items/v2/active")
    candidates = [item for item in items_after if str(item.get("Name") or "") == ALT_ITEM_NAME]
    if len(candidates) != 1:
        raise MetrcPackageAltItemError("Provider accepted alternate item but exact active-item reconciliation is ambiguous.")
    candidate = _validate_candidate(candidates[0], strain_name=strain_name)
    provider_id = str(candidate.get("Id") or evidence.get("provider_id") or "")
    if not provider_id:
        raise MetrcPackageAltItemError("Alternate item was created without a verifiable provider ID.")
    return {
        "status": "complete",
        "passed": True,
        "http_status": 200,
        "provider_id": provider_id,
        "name": ALT_ITEM_NAME,
        "source_readback_http": source_read.get("http_status"),
    }
