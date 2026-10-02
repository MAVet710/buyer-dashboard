from __future__ import annotations

import pytest

from services.metrc_adjust_semantics_probe import (
    ABSOLUTE,
    DELTA,
    UNKNOWN,
    MetrcAdjustSemanticsProbeError,
    choose_probe_quantity,
    classify_semantics,
    probe_package_adjust_semantics,
    recommended_correction,
)

PROBE_ID = "70001"
PROBE_LABEL = "AAA0A0300001A30000000099"


def _readback(provider_id: str, quantity: float, unit: str = "Grams") -> dict:
    return {
        "ok": True,
        "records": [
            {
                "provider_id": provider_id,
                "source": {"Id": int(provider_id), "Quantity": quantity, "UnitOfMeasureName": unit},
            }
        ],
    }


def _reader(quantity: float, unit: str = "Grams"):
    def read_fn(**kwargs):
        return _readback(str(kwargs["path_parameters"]["id"]), quantity, unit)

    return read_fn


def _executor(final_quantity: float, *, http_status: int = 200, captured: list | None = None):
    def execute_fn(**kwargs):
        if captured is not None:
            captured.append(kwargs)
        package_id = str(kwargs["payload"]["package_id"])
        return {
            "http_status": http_status,
            "readback": _readback(package_id, final_quantity) if http_status == 200 else None,
        }

    return execute_fn


def _probe(**overrides):
    arguments = dict(
        package_id=PROBE_ID,
        package_label=PROBE_LABEL,
        adjustment_reason="Over/Under Pulled",
        adjustment_date="2026-09-15",
        license_number="MR281212",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    arguments.update(overrides)
    return probe_package_adjust_semantics(**arguments)


def test_absolute_semantics_is_proven_when_the_package_lands_on_the_value_sent():
    evidence = _probe(read_fn=_reader(10.0), execute_fn=_executor(1.0), quarantined_observed_quantity=-5.0)

    assert evidence["verdict"] == ABSOLUTE
    assert evidence["passed"] is True
    assert evidence["current_quantity"] == 10.0
    assert evidence["probe_quantity"] == 1.0
    assert evidence["observed_quantity"] == 1.0
    assert evidence["recommended_correction"] == 0.0
    assert evidence["probe_restoration_quantity"] == 10.0


def test_delta_semantics_is_proven_when_the_package_lands_on_the_sum():
    evidence = _probe(read_fn=_reader(10.0), execute_fn=_executor(11.0), quarantined_observed_quantity=-5.0)

    assert evidence["verdict"] == DELTA
    assert evidence["passed"] is True
    assert evidence["observed_quantity"] == 11.0
    assert evidence["recommended_correction"] == 5.0
    assert evidence["probe_restoration_quantity"] == -1.0


def test_a_third_outcome_is_reported_unknown_and_recommends_no_correction():
    evidence = _probe(read_fn=_reader(10.0), execute_fn=_executor(-1.0))

    assert evidence["verdict"] == UNKNOWN
    assert evidence["passed"] is False
    assert evidence["recommended_correction"] is None
    assert "escalate" in evidence["message"]


def test_the_probe_sends_the_packages_own_unit_and_the_chosen_quantity():
    captured: list = []
    _probe(read_fn=_reader(10.0, "Ounces"), execute_fn=_executor(1.0, captured=captured))

    assert len(captured) == 1
    payload = captured[0]["payload"]
    assert payload["unit_of_measure"] == "Ounces"
    assert payload["quantity"] == 1.0
    assert payload["label"] == PROBE_LABEL
    assert captured[0]["operation_type"] == "package_adjust"
    assert captured[0]["environment"] == "sandbox"


@pytest.mark.parametrize(
    "overrides",
    [
        {"package_id": "64801"},
        {"package_label": "AAA0A0300001A30000000041"},
        {"package_label": "aaa0a0300001a30000000041"},
    ],
)
def test_the_probe_refuses_to_write_to_the_quarantined_package(overrides):
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="quarantined"):
        _probe(
            quarantined_package_ids=("64801",),
            quarantined_package_labels=("AAA0A0300001A30000000041",),
            read_fn=_reader(5.0),
            execute_fn=_executor(0.0),
            **overrides,
        )


def test_a_probe_package_at_zero_cannot_decide_anything_and_is_refused():
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="zero"):
        _probe(read_fn=_reader(0.0), execute_fn=_executor(1.0))


def test_a_negative_probe_package_is_refused():
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="positive quantity"):
        _probe(read_fn=_reader(-5.0), execute_fn=_executor(1.0))


def test_an_explicit_probe_quantity_matching_the_current_quantity_is_refused():
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="cannot distinguish"):
        _probe(read_fn=_reader(4.0), execute_fn=_executor(4.0), probe_quantity=4.0)


def test_a_non_positive_explicit_probe_quantity_is_refused():
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="must be positive"):
        _probe(read_fn=_reader(4.0), execute_fn=_executor(0.0), probe_quantity=-1.0)


def test_nothing_is_sent_when_the_probe_package_cannot_be_read_first():
    def failed_read(**kwargs):
        return {"ok": False, "records": []}

    captured: list = []
    evidence = _probe(read_fn=failed_read, execute_fn=_executor(1.0, captured=captured))

    assert evidence["write_sent"] is False
    assert evidence["verdict"] == UNKNOWN
    assert captured == []


def test_a_non_200_leaves_the_semantics_undecided_and_says_so():
    evidence = _probe(read_fn=_reader(10.0), execute_fn=_executor(0.0, http_status=400))

    assert evidence["write_sent"] is True
    assert evidence["http_status"] == 400
    assert evidence["verdict"] == UNKNOWN
    assert evidence["passed"] is False


@pytest.mark.parametrize("environment,state", [("production", "MA"), ("sandbox", "CA")])
def test_the_probe_is_restricted_to_the_massachusetts_sandbox(environment, state):
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="Massachusetts sandbox"):
        _probe(environment=environment, state=state, read_fn=_reader(10.0), execute_fn=_executor(1.0))


def test_an_exact_adjustment_reason_is_required_rather_than_guessed():
    with pytest.raises(MetrcAdjustSemanticsProbeError, match="do not guess"):
        _probe(adjustment_reason="  ", read_fn=_reader(10.0), execute_fn=_executor(1.0))


def test_the_default_probe_quantity_never_collides_with_the_current_quantity():
    assert choose_probe_quantity(10.0) == 1.0
    assert choose_probe_quantity(1.0) == 2.0


def test_classification_and_correction_are_pure_functions():
    assert classify_semantics(current_quantity=5.0, probe_quantity=1.0, observed_quantity=1.0) == ABSOLUTE
    assert classify_semantics(current_quantity=5.0, probe_quantity=1.0, observed_quantity=6.0) == DELTA
    assert classify_semantics(current_quantity=5.0, probe_quantity=1.0, observed_quantity=None) == UNKNOWN
    assert recommended_correction(ABSOLUTE, -5.0) == 0.0
    assert recommended_correction(DELTA, -5.0) == 5.0
    assert recommended_correction(UNKNOWN, -5.0) is None
