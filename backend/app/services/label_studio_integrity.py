"""Integrity normalization for Label Studio's selected testing-label source.

Label Studio may display several dates from operational records, but a testing
label's test date has one meaning: the date reported by the verified COA that is
being used as test evidence.  In particular, ``LotQualityEvidence.verified_at``
is an audit timestamp and must never be presented as the laboratory test date.

This module also keeps the selected current package identity synchronized across
the label, QR, and barcode projection.  COA evidence may legitimately come from
an ancestor package after a recorded split/repack, but the physical label always
identifies the current package.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COA_AUTHORITATIVE_FIELDS = frozenset(
    {
        "lab_testing_state",
        "laboratory",
        "lab_license_number",
        "test_date",
        "coa_reference",
        "potency",
        "total_thc",
        "total_cbd",
        "total_cannabinoids",
        "total_terpenes",
    }
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _percent(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):g}%"
    except (TypeError, ValueError):
        return ""


def normalize_testing_label_source(source: dict[str, Any]) -> dict[str, Any]:
    """Return a source whose regulated identity/date fields cannot contradict it.

    The detailed Label Studio projection is already assembled from Product
    Master, facility, lot, packaging, QA and COA records.  This final boundary
    normalization makes the cross-record contract explicit before the payload
    reaches the browser.
    """

    normalized = deepcopy(source)
    label = dict(normalized.get("label") or {})
    coa = dict(normalized.get("coa") or {})
    package_id = _text(normalized.get("package_id"))

    # The selected inventory package is the physical identity being labeled.
    label["package_id"] = package_id
    label["qr_value"] = package_id
    qr = dict(normalized.get("qr") or {})
    if qr:
        qr["value"] = package_id
        normalized["qr"] = qr
    barcode = dict(normalized.get("barcode") or {})
    if barcode:
        barcode["value"] = package_id
        normalized["barcode"] = barcode

    # A QA verification timestamp is not a lab test date.  Only a verified COA
    # can provide the testing-label Test date used by the pre-release review.
    coa_available = bool(coa.get("available"))
    label["test_date"] = _text(coa.get("date_tested")) if coa_available else ""

    # When verified COA evidence exists, keep the duplicated label fields in
    # lock-step with that structured source rather than stale lot metadata.
    if coa_available:
        status = _text(coa.get("overall_status")).casefold()
        if status in {"pass", "passed"}:
            label["lab_testing_state"] = "Passed"
        elif status in {"fail", "failed"}:
            label["lab_testing_state"] = "Failed"

        if _text(coa.get("lab_name")):
            label["laboratory"] = _text(coa.get("lab_name"))
        if _text(coa.get("lab_license_number")):
            label["lab_license_number"] = _text(coa.get("lab_license_number"))
        if _text(coa.get("lab_id")):
            label["coa_reference"] = _text(coa.get("lab_id"))

        for source_key, label_key in (
            ("total_thc", "total_thc"),
            ("total_cbd", "total_cbd"),
            ("total_cannabinoids", "total_cannabinoids"),
            ("total_terpenes", "total_terpenes"),
        ):
            if coa.get(source_key) is not None:
                label[label_key] = _percent(coa.get(source_key))

    normalized["label"] = label
    return normalized


def testing_source_mismatches(source: dict[str, Any]) -> list[str]:
    """Return deterministic integrity violations for diagnostics/tests."""

    mismatches: list[str] = []
    label = source.get("label") or {}
    coa = source.get("coa") or {}
    package_id = _text(source.get("package_id"))

    if _text(label.get("package_id")) != package_id:
        mismatches.append("label.package_id")
    if source.get("qr") and _text((source.get("qr") or {}).get("value")) != package_id:
        mismatches.append("qr.value")
    if source.get("barcode") and _text((source.get("barcode") or {}).get("value")) != package_id:
        mismatches.append("barcode.value")

    expected_test_date = _text(coa.get("date_tested")) if coa.get("available") else ""
    if _text(label.get("test_date")) != expected_test_date:
        mismatches.append("label.test_date")

    return mismatches
