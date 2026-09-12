"""Behavioral tests: no real credentials and no provider network calls."""
from types import SimpleNamespace

import pytest

from backend.app.services import metrc_package_eval_resume as subject
from services.metrc_evaluation_lifecycle import build_lifecycle_evaluation_payload
from services.metrc_resume_response import ResumeResponseError


def test_scope_is_mandatory(monkeypatch):
    for name in ("ORGANIZATION_ID", "FACILITY_ID", "SOURCE_LABEL", "SOURCE_ID"):
        monkeypatch.delenv("METRC_PACKAGE_EVAL_" + name, raising=False)
    with pytest.raises(subject.MetrcPackageResumeError, match="Explicit organization"):
        subject._configuration("RUN-1")


def configure(monkeypatch):
    for name, value in {"ORGANIZATION_ID": "org", "FACILITY_ID": "facility", "SOURCE_LABEL": "A" * 24, "SOURCE_ID": "10"}.items():
        monkeypatch.setenv("METRC_PACKAGE_EVAL_" + name, value)


def test_default_is_read_only_preflight(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("METRC_PACKAGE_EVAL_MODE", raising=False)
    assert subject._configuration("RUN-1")["mode"] == "preflight"


def test_execution_approval_is_bound_to_run(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("METRC_PACKAGE_EVAL_MODE", "execute")
    monkeypatch.setenv("METRC_PACKAGE_EVAL_APPROVAL", "OTHER-RUN")
    with pytest.raises(subject.MetrcPackageResumeError, match="approval"):
        subject._configuration("RUN-1")
    monkeypatch.setenv("METRC_PACKAGE_EVAL_APPROVAL", "RUN-1")
    assert subject._configuration("RUN-1")["mode"] == "execute"


def test_run_id_cannot_be_silently_truncated():
    with pytest.raises(subject.MetrcPackageResumeError, match="never truncated"):
        subject._configuration("X" * 37)


def test_intent_is_saved_before_dispatch():
    seen = []
    events = {}
    def execute():
        assert seen[0] == "task25_started"
        assert "task25_started" in events
        return {"passed": True}
    result = subject._once("task25", events, lambda name, data: seen.append(name), execute)
    assert result["passed"] is True
    assert seen == ["task25_started", "task25_result"]


@pytest.mark.parametrize("name", ["tag_generation", "task25", "task26"])
def test_uncertain_attempt_is_never_reissued(name):
    def forbidden():
        pytest.fail("A mutation was retried")
    result = subject._once(name, {name + "_started": {}}, lambda *args: None, forbidden)
    assert result == {"passed": False, "stage": "outcome_uncertain", "retry_blocked": True}


def test_failed_result_is_not_overwritten():
    result = {"passed": False, "http_status": 401}
    assert subject._once("task25", {"task25_result": result}, None, None) is result


def test_timeout_is_recorded_without_exception_secret():
    saved = []
    def execute():
        raise TimeoutError("DO-NOT-PERSIST-ME")
    result = subject._once("task26", {}, lambda name, data: saved.append(data), execute)
    assert result["retry_blocked"] is True
    assert "DO-NOT-PERSIST-ME" not in str(saved)


def test_secret_redaction_is_not_only_a_boolean_claim():
    result = subject._sanitize({"UserApiKey": "key", "body": "contains a-secret", "nested": [{"password": "bad", "ok": 0}]}, ("a-secret",))
    assert result == {"body": "contains [REDACTED]", "nested": [{"ok": 0}]}


def test_alternate_item_cannot_cross_product_category():
    source = {"Item": {"ProductCategoryName": "Immature Plants"}}
    item = {"Id": 2, "Name": "DoobieLogic MA Eval Clone Alternate", "QuantityType": "CountBased",
            "UnitOfMeasureName": "Each", "ApprovalStatus": "Approved", "ProductCategoryName": "Edibles"}
    with pytest.raises(subject.MetrcPackageResumeError):
        subject._alternate_item([item], source)
    item["ProductCategoryName"] = "Immature Plants"
    assert subject._alternate_item([item], source)["Id"] == 2


def test_optional_lab_batches_preserves_documented_null():
    payload = {"tag": "A" * 24, "item": "Clones", "quantity": 1, "unit_of_measure": "Each",
               "actual_date": "2026-09-12", "ingredients": [{"package": "B" * 24, "quantity": 1, "unit_of_measure": "Each"}],
               "required_lab_test_batches": None}
    assert build_lifecycle_evaluation_payload("package_create", payload)[0]["RequiredLabTestBatches"] is None
    payload["required_lab_test_batches"] = True
    assert build_lifecycle_evaluation_payload("package_create", payload)[0]["RequiredLabTestBatches"] is True


def provider():
    return subject._Provider(SimpleNamespace(license_number="TEST-LICENSE", integrator_api_key="vendor-test", user_api_key="user-test"))


def test_customer_type_call_has_no_unapproved_license_query(monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: ["Consumer", "Patient"])
    monkeypatch.setattr(subject.requests, "get", get)
    body, evidence = provider().get("sales/v2/customertypes", scoped=False)
    assert body == ["Consumer", "Patient"]
    assert calls[0]["params"] == {}
    assert calls[0]["allow_redirects"] is False
    assert evidence["http_status"] == 200


def test_top_level_pagination_reads_every_page(monkeypatch):
    calls = []
    p = provider()
    def get(path, **kwargs):
        page = kwargs["query"]["pageNumber"]
        calls.append(page)
        return {"Data": [{"Id": page}], "TotalPages": 2}, {"http_status": 200}
    monkeypatch.setattr(p, "get", get)
    rows, captures = p.pages("items/v2/active")
    assert calls == [1, 2]
    assert len(rows) == len(captures) == 2


def test_generated_tag_requires_original_success_response(monkeypatch):
    p = provider()
    monkeypatch.setattr(subject.requests, "post", lambda *args, **kwargs: SimpleNamespace(
        status_code=401, content=b"{}", json=lambda: {}))
    result = subject._generate_tag(p, "Marijuana Package", set(), lambda *args: None)
    assert result["passed"] is False
    assert result["http_status"] == 401
    assert "tag" not in result


def test_tag_cannot_be_taken_from_preexisting_inventory(monkeypatch):
    p = provider()
    label = "A" * 24
    monkeypatch.setattr(subject.requests, "post", lambda *args, **kwargs: SimpleNamespace(
        status_code=200, content=b"{}", json=lambda: {"Count": 1, "TagType": "Marijuana Package", "Labels": [label]}))
    assert subject._generate_tag(p, "Marijuana Package", {label}, lambda *args: None)["passed"] is False
    assert subject._generate_tag(p, "Marijuana Package", set(), lambda *args: None)["tag"] == label


def test_id_only_adapter_success_cannot_pass_wrong_item(monkeypatch):
    p = provider()
    label = "A" * 24
    saved = []
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", lambda **kwargs: {
        "passed": True, "http_status": 200, "provider_id": "20", "stage": "complete"})
    monkeypatch.setattr(p, "package", lambda value: ({
        "Id": 20, "Label": label, "Quantity": 1, "UnitOfMeasureName": "Each",
        "Item": {"Name": "Wrong Item"}, "IsFinished": False, "IsOnHold": False}, {"http_status": 200}))
    with pytest.raises(ResumeResponseError, match="item differs"):
        subject._task(p, 26, {}, lambda name, data: saved.append(name), label=label, item="Correct Item", expected_id="20")
    assert "task26_evidence" not in saved
