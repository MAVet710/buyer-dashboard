"""Settle PUT /packages/v2/adjust quantity semantics from live sandbox evidence.

The Massachusetts sandbox accepted a -5.0 adjustment against a 5.0 Grams package
and then reported that package at -5.0.  Two readings of the endpoint explain
that observation equally well and imply opposite corrective writes:

    delta     final = current + Quantity   (the value sent is a signed change)
    absolute  final = Quantity             (the value sent is the new balance)

This module decides between them using a disposable probe package rather than
the anomalous one.  It refuses to aim at a quarantined package, refuses when the
probe package's current quantity cannot distinguish the two readings, and
reports UNKNOWN instead of picking a reading the evidence does not support.

Nothing here provisions credentials, and no credential reaches the evidence.
"""

from __future__ import annotations

from math import isclose
from typing import Any, Callable

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import (
    MetrcLifecycleEvaluationError,
    execute_lifecycle_evaluation_action,
)


class MetrcAdjustSemanticsProbeError(RuntimeError):
    """Raised before dispatch when the probe cannot be proven safe or decisive."""


ABSOLUTE = "absolute"
DELTA = "delta"
UNKNOWN = "unknown"

_TOLERANCE = 1e-9


def _text(value: Any) -> str:
    return str(value or "").strip()


def _close(left: float, right: float) -> bool:
    return isclose(left, right, abs_tol=_TOLERANCE, rel_tol=0.0)


def _record_source(readback: Any, provider_id: str) -> dict[str, Any] | None:
    if not isinstance(readback, dict) or not readback.get("ok"):
        return None
    wanted = _text(provider_id)
    for record in readback.get("records") or []:
        if not isinstance(record, dict):
            continue
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        found = _text(record.get("provider_id") or source.get("Id") or source.get("id"))
        if found == wanted:
            return dict(source)
    return None


def _quantity(source: dict[str, Any] | None) -> float | None:
    if not source:
        return None
    for key in ("Quantity", "quantity", "CurrentQuantity"):
        if source.get(key) is None:
            continue
        try:
            return float(source[key])
        except (TypeError, ValueError):
            return None
    return None


def _unit_of_measure(source: dict[str, Any] | None) -> str:
    if not source:
        return ""
    for key in ("UnitOfMeasureName", "UnitOfMeasure", "UnitOfMeasureAbbreviation"):
        token = _text(source.get(key))
        if token:
            return token
    return ""


def choose_probe_quantity(current_quantity: float) -> float:
    """Pick a positive value whose delta and absolute outcomes cannot be confused.

    Both predictions stay positive, so neither reading leaves the probe package
    in a nonsensical state, and neither prediction equals the current quantity
    (which would make a rejected write look like a successful one).
    """

    if _close(current_quantity, 0.0):
        raise MetrcAdjustSemanticsProbeError(
            "A probe package at zero cannot distinguish delta from absolute semantics."
        )
    if current_quantity < 0.0:
        raise MetrcAdjustSemanticsProbeError(
            "The probe package must hold a positive quantity; it cannot itself be anomalous."
        )
    candidate = 1.0
    if _close(candidate, current_quantity) or _close(candidate + current_quantity, current_quantity):
        candidate = 2.0
    return candidate


def validate_probe_quantity(current_quantity: float, probe_quantity: float) -> float:
    value = float(probe_quantity)
    if value <= 0.0:
        raise MetrcAdjustSemanticsProbeError("The probe quantity must be positive so neither reading yields a negative package.")
    if _close(value, current_quantity):
        raise MetrcAdjustSemanticsProbeError(
            "A probe quantity equal to the current quantity cannot distinguish an absolute write from a rejected one."
        )
    if _close(value, current_quantity + value):
        raise MetrcAdjustSemanticsProbeError("The probe quantity cannot distinguish the two readings for this package.")
    return value


def classify_semantics(*, current_quantity: float, probe_quantity: float, observed_quantity: float | None) -> str:
    if observed_quantity is None:
        return UNKNOWN
    if _close(observed_quantity, probe_quantity):
        return ABSOLUTE
    if _close(observed_quantity, current_quantity + probe_quantity):
        return DELTA
    return UNKNOWN


def recommended_correction(verdict: str, observed_quantity: float | None) -> float | None:
    """The Quantity that drives an anomalous package to zero under a proven reading."""

    if observed_quantity is None:
        return None
    if verdict == ABSOLUTE:
        return 0.0
    if verdict == DELTA:
        return -float(observed_quantity)
    return None


def _restoration_quantity(verdict: str, current_quantity: float, probe_quantity: float) -> float | None:
    if verdict == ABSOLUTE:
        return current_quantity
    if verdict == DELTA:
        return -probe_quantity
    return None


def probe_package_adjust_semantics(
    *,
    package_id: int | str,
    package_label: str,
    adjustment_reason: str,
    adjustment_date: str,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    quarantined_package_ids: tuple[str, ...] = (),
    quarantined_package_labels: tuple[str, ...] = (),
    quarantined_observed_quantity: float | None = None,
    unit_of_measure: str = "",
    probe_quantity: float | None = None,
    reason_note: str = "",
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    read_fn: Callable[..., dict[str, Any]] | None = None,
    execute_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run exactly one disposable adjustment and report which reading it proves."""

    state_code = _text(state).upper()
    environment_code = _text(environment).casefold()
    provider_id = _text(package_id)
    label = _text(package_label)
    reason = _text(adjustment_reason)

    evidence: dict[str, Any] = {
        "passed": False,
        "stage": "preflight",
        "verdict": UNKNOWN,
        "state": state_code,
        "environment": environment_code,
        "probe_package_id": provider_id,
        "probe_package_label": label,
        "current_quantity": None,
        "probe_quantity": None,
        "predicted_if_delta": None,
        "predicted_if_absolute": None,
        "observed_quantity": None,
        "write_sent": False,
        "http_status": 0,
        "write_evidence": None,
        "recommended_correction": None,
        "probe_restoration_quantity": None,
        "message": "",
    }

    if state_code != "MA" or environment_code != "sandbox":
        raise MetrcAdjustSemanticsProbeError("This probe is restricted to the verified Massachusetts sandbox.")
    if not provider_id or not label:
        raise MetrcAdjustSemanticsProbeError("The probe requires both the package provider ID and its exact label.")
    if not reason:
        raise MetrcAdjustSemanticsProbeError("An exact current Metrc adjustment reason is required; do not guess one.")
    if not _text(adjustment_date):
        raise MetrcAdjustSemanticsProbeError("An adjustment date is required.")
    if not _text(license_number):
        raise MetrcAdjustSemanticsProbeError("A Massachusetts sandbox facility license number is required.")

    quarantined_ids = {_text(value) for value in quarantined_package_ids if _text(value)}
    quarantined_labels = {_text(value).casefold() for value in quarantined_package_labels if _text(value)}
    if provider_id in quarantined_ids or label.casefold() in quarantined_labels:
        raise MetrcAdjustSemanticsProbeError(
            "The probe refuses to write to a quarantined package; use a disposable package instead."
        )

    reader = read_fn or fetch_metrc_resource
    before = reader(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="packages_by_id",
        environment=environment_code,
        license_number=_text(license_number),
        path_parameters={"id": provider_id},
        timeout_seconds=timeout_seconds,
    )
    source = _record_source(before, provider_id)
    if source is None:
        evidence["message"] = "The probe package could not be read back before the write; nothing was sent."
        return evidence

    current = _quantity(source)
    if current is None:
        evidence["message"] = "The probe package readback carried no usable quantity; nothing was sent."
        return evidence

    evidence["current_quantity"] = current
    unit = _text(unit_of_measure) or _unit_of_measure(source)
    if not unit:
        evidence["message"] = "The probe package readback carried no unit of measure; nothing was sent."
        return evidence

    chosen = choose_probe_quantity(current) if probe_quantity is None else validate_probe_quantity(current, probe_quantity)
    evidence["probe_quantity"] = chosen
    evidence["predicted_if_delta"] = current + chosen
    evidence["predicted_if_absolute"] = chosen

    payload = {
        "package_id": int(provider_id),
        "label": label,
        "quantity": chosen,
        "unit_of_measure": unit,
        "adjustment_reason": reason,
        "adjustment_date": _text(adjustment_date),
    }
    if _text(reason_note):
        payload["reason_note"] = _text(reason_note)

    executor = execute_fn or execute_lifecycle_evaluation_action
    try:
        write_evidence = executor(
            operation_type="package_adjust",
            payload=payload,
            license_number=_text(license_number),
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
            state=state_code,
            environment=environment_code,
            timeout_seconds=timeout_seconds,
        )
    except MetrcLifecycleEvaluationError as exc:
        evidence["message"] = f"The probe write was refused before dispatch: {exc}"
        return evidence

    evidence["write_sent"] = True
    evidence["stage"] = "write"
    evidence["write_evidence"] = write_evidence
    evidence["http_status"] = int(write_evidence.get("http_status") or 0)

    if evidence["http_status"] != 200:
        evidence["message"] = (
            f"Metrc returned HTTP {evidence['http_status']} for the probe adjustment; "
            "the semantics remain undecided and the anomalous package stays untouched."
        )
        return evidence

    observed = _quantity(_record_source(write_evidence.get("readback"), provider_id))
    if observed is None:
        after = reader(
            state=state_code,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="packages_by_id",
            environment=environment_code,
            license_number=_text(license_number),
            path_parameters={"id": provider_id},
            timeout_seconds=timeout_seconds,
        )
        observed = _quantity(_record_source(after, provider_id))

    evidence["observed_quantity"] = observed
    evidence["stage"] = "readback"
    verdict = classify_semantics(current_quantity=current, probe_quantity=chosen, observed_quantity=observed)
    evidence["verdict"] = verdict
    evidence["probe_restoration_quantity"] = _restoration_quantity(verdict, current, chosen)

    if verdict == UNKNOWN:
        evidence["message"] = (
            "The probe package read back at "
            f"{observed!r}, which matches neither the delta prediction "
            f"({current + chosen}) nor the absolute prediction ({chosen}). "
            "Do not send a corrective write; escalate to the Metrc API team."
        )
        return evidence

    evidence["passed"] = True
    evidence["stage"] = "complete"
    correction = recommended_correction(verdict, quarantined_observed_quantity)
    evidence["recommended_correction"] = correction
    detail = (
        f" The quarantined package reported at {quarantined_observed_quantity} reaches zero with Quantity={correction}."
        if correction is not None
        else " Supply the quarantined package's observed quantity to derive its corrective Quantity."
    )
    evidence["message"] = (
        f"PUT /packages/v2/adjust treats Quantity as {'an absolute balance' if verdict == ABSOLUTE else 'a signed delta'}: "
        f"{current} with Quantity={chosen} became {observed}.{detail}"
    )
    return evidence
