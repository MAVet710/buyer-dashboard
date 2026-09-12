"""Validate an explicitly allocated existing tag; never provision sandbox tags.

Checkpoint hashes are provenance references, not signatures or proof that a tag
is still available. A fresh, facility-scoped provider read is always required.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class ExistingPackageTagError(ValueError):
    """The operator-supplied allocation or current provider state is unsafe."""


_LABEL = re.compile(r"[A-Z0-9]{20,32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FIELDS = {
    "schema_version", "run_id", "evaluation_run_id", "state", "environment",
    "license_number", "source_id", "source_label", "destination_label",
    "protected_labels", "task17_reserved_label", "checkpoint_sha256",
    "reservation_evidence_sha256",
}


def load_existing_tag_allocation(raw: str, *, run_id: str, evaluation_run_id: str,
                                 license_number: str, source_id: str,
                                 source_label: str) -> dict[str, Any]:
    """Require explicit run/facility/source binding and a protected Task 17 tag."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 65536:
        raise ExistingPackageTagError("A bounded existing-tag allocation JSON is required.")
    try:
        plan = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ExistingPackageTagError("Existing-tag allocation is not valid JSON.") from exc
    if not isinstance(plan, dict) or set(plan) != _FIELDS:
        raise ExistingPackageTagError("Existing-tag allocation fields are incomplete or unrecognized.")
    expected = {"run_id": run_id, "evaluation_run_id": evaluation_run_id,
                "state": "MA", "environment": "sandbox", "license_number": license_number,
                "source_id": source_id, "source_label": source_label}
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ExistingPackageTagError("Unsupported existing-tag allocation version.")
    if any(not value or plan.get(key) != value for key, value in expected.items()):
        raise ExistingPackageTagError("Existing-tag allocation does not match this run, facility or source.")
    for key in ("source_label", "destination_label", "task17_reserved_label"):
        if not isinstance(plan[key], str) or not _LABEL.fullmatch(plan[key]):
            raise ExistingPackageTagError("Existing-tag allocation contains an invalid label.")
    for key in ("checkpoint_sha256", "reservation_evidence_sha256"):
        if not isinstance(plan[key], str) or not _SHA256.fullmatch(plan[key]):
            raise ExistingPackageTagError("Checkpoint and reservation evidence hashes are required.")
    protected = plan["protected_labels"]
    if (not isinstance(protected, list) or not protected
            or any(not isinstance(label, str) or not _LABEL.fullmatch(label) for label in protected)
            or len(protected) != len(set(protected))):
        raise ExistingPackageTagError("Protected labels must be a nonempty, unique list of valid tags.")
    if plan["task17_reserved_label"] not in protected or source_label not in protected:
        raise ExistingPackageTagError("Task 17's reserved tag and the source tag must be protected.")
    if plan["destination_label"] in protected:
        raise ExistingPackageTagError("Destination tag is protected by another evaluation task.")
    plan["protected_labels"] = sorted(protected)
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return {**plan, "allocation_sha256": hashlib.sha256(encoded).hexdigest()}


def verify_existing_tag_available(plan: dict[str, Any], rows: list[dict], *,
                                   provider_facility_id: Any) -> dict:
    """Validate exactly one selected label from fresh /tags/v2/package/available."""
    if not str(provider_facility_id or "").isdigit() or isinstance(provider_facility_id, bool):
        raise ExistingPackageTagError("Fresh facility discovery did not identify the provider facility.")
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("Label") == plan["destination_label"]]
    if len(matches) != 1:
        raise ExistingPackageTagError("Allocated tag is absent or ambiguous in current available inventory.")
    row = matches[0]
    if (str(row.get("FacilityId") or "") != str(provider_facility_id)
            or row.get("TagInventoryTypeName") != "CannabisPackage"
            or isinstance(row.get("Id"), bool) or not str(row.get("Id") or "").isdigit()):
        raise ExistingPackageTagError("Allocated tag has the wrong facility, inventory type or identity.")
    return dict(row)


def verify_allocation_resume(plan: dict[str, Any], events: dict[str, dict]) -> None:
    """A restart never silently changes a tag or bypasses an uncertain write."""
    if any(key.startswith("tag_generation_") for key in events):
        raise ExistingPackageTagError("Existing-tag mode cannot replace a prior tag-generation attempt.")
    saved = events.get("tag_allocation")
    if saved and saved.get("allocation_sha256") != plan["allocation_sha256"]:
        raise ExistingPackageTagError("Existing-tag allocation changed after its durable reservation.")
    for task in ("task25", "task26"):
        started, result = events.get(task + "_started"), events.get(task + "_result")
        if started is not None and result is None:
            raise ExistingPackageTagError("A previous package mutation has an uncertain outcome; readback is required.")
        if result is not None:
            if (not saved or result.get("passed") is not True
                    or result.get("http_status") != 200 or result.get("stage") != "complete"
                    or result.get("postconditions_verified") is not True
                    or result.get("label") != plan["destination_label"]):
                raise ExistingPackageTagError("Prior package evidence is incomplete or belongs to another allocation.")
