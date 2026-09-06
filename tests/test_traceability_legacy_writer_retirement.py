from __future__ import annotations

from pathlib import Path

from modules.traceability.runtime_context import TraceabilityRuntime, resolve_streamlit_traceability_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_traceability_console_no_longer_imports_legacy_processor():
    source = (ROOT / "modules/traceability/ui.py").read_text(encoding="utf-8")

    assert "process_queued" not in source
    assert "TraceabilityCredentials" not in source
    assert "resolve_streamlit_traceability_runtime" in source
    assert "runtime.provider_dispatch(transaction.id)" in source


def test_extraction_legacy_executor_cannot_submit_provider_work():
    source = (ROOT / "modules/extraction/traceability.py").read_text(encoding="utf-8")

    assert "process_transaction" not in source
    assert 'operation_type="package_create"' in source
    assert "require_metrc_write_contract" in source
    assert "Legacy extraction package-create execution is disabled" in source


def test_streamlit_runtime_fails_closed_without_canonical_identity():
    runtime = resolve_streamlit_traceability_runtime(
        {
            "active_organization_id": "org-1",
            "active_facility_id": "fac-1",
            "auth_username": "legacy-user",
        }
    )

    assert isinstance(runtime, TraceabilityRuntime)
    assert runtime.ready is False
    assert runtime.provider_dispatch is None
    assert "canonical user id" in runtime.message.casefold()
