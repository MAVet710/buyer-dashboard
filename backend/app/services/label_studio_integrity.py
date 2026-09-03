"""Integrity normalization for Label Studio testing-label sources.

Label Studio may display several dates from operational records, but a testing
label's test date has one meaning: the date reported by the verified COA that is
being used as test evidence. In particular, ``LotQualityEvidence.verified_at``
is an audit timestamp and must never be presented as the laboratory test date.

This module also keeps the selected current package identity synchronized across
the label, QR, and barcode projection. COA evidence may legitimately come from
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


def _result_percent(coa: dict[str, Any], key: str) -> str:
    for result in coa.get("results") or []:
        if _text(result.get("key")).casefold() != key.casefold():
            continue
        value = result.get("value")
        units = _text(result.get("units"))
        if value is None:
            return ""
        if units == "%" or not units:
            return _percent(value)
        return f"{float(value):g} {units}" if isinstance(value, (int, float)) else f"{value} {units}".strip()
    return ""


def _coa_potency(coa: dict[str, Any]) -> str:
    entries: list[str] = []
    thca = _result_percent(coa, "thca")
    if thca:
        entries.append(f"THCA {thca}")
    for label, key in (
        ("Total THC", "total_thc"),
        ("TAC", "total_cannabinoids"),
        ("Total terpenes", "total_terpenes"),
    ):
        value = _percent(coa.get(key))
        if value:
            entries.append(f"{label} {value}")
    return " · ".join(entries)


def normalize_testing_label_source(source: dict[str, Any]) -> dict[str, Any]:
    """Return a source whose regulated identity/COA fields cannot contradict it.

    The detailed Label Studio projection is assembled from Product Master,
    facility, lot, packaging, QA and COA records. This final boundary makes the
    source-of-truth contract explicit before the payload reaches the browser.
    Unverified QA/lot metadata may remain available elsewhere operationally, but
    it is never allowed to masquerade as verified laboratory evidence on a
    testing label.
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

    # Clear every field whose authority belongs to verified COA evidence before
    # copying the selected COA. This prevents stale QA or lot metadata from
    # surviving when an authoritative COA omits a field.
    for field in COA_AUTHORITATIVE_FIELDS:
        label[field] = ""

    if bool(coa.get("available")):
        status = _text(coa.get("overall_status")).casefold()
        if status in {"pass", "passed"}:
            label["lab_testing_state"] = "Passed"
        elif status in {"fail", "failed"}:
            label["lab_testing_state"] = "Failed"

        label["laboratory"] = _text(coa.get("lab_name"))
        label["lab_license_number"] = _text(coa.get("lab_license_number"))
        label["test_date"] = _text(coa.get("date_tested"))
        # A document filename is still an authoritative COA reference when the
        # laboratory did not print its own report ID.
        label["coa_reference"] = _text(coa.get("lab_id")) or _text(coa.get("filename"))
        label["potency"] = _coa_potency(coa)
        label["total_thc"] = _percent(coa.get("total_thc"))
        label["total_cbd"] = _percent(coa.get("total_cbd"))
        label["total_cannabinoids"] = _percent(coa.get("total_cannabinoids"))
        label["total_terpenes"] = _percent(coa.get("total_terpenes"))

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

    if not coa.get("available"):
        for field in COA_AUTHORITATIVE_FIELDS:
            if _text(label.get(field)):
                mismatches.append(f"label.{field}")

    return mismatches
