from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_label_production_schema_preserves_one_finished_tag_and_many_sources():
    source = _read("modules/label_studio_workflow.py")
    assert 'UniqueConstraint("organization_id", "metrc_package_tag"' in source
    assert 'UniqueConstraint("run_id", "source_lot_id"' in source
    assert 'label_snapshot_json' in source
    assert '"draft", "validated", "tagged", "printed", "applied", "released", "fulfilled", "archived"' in source
    assert 'event_type="reprinted"' not in source  # events are emitted through the shared helper, never mutable columns
    assert 'self._event(session, run, "reprinted"' in source
    assert 'A reprint reason is required after the first print.' in source


def test_label_production_api_is_parallel_to_existing_label_studio_routes():
    router = _read("backend/app/routers/label_printing.py")
    for route in (
        '@router.post("/production-runs", status_code=201)',
        '@router.post("/production-runs/{run_id}/tag")',
        '@router.post("/production-runs/{run_id}/print")',
        '@router.post("/production-runs/{run_id}/transition")',
    ):
        assert route in router
    assert '@router.get("/inventory-sources")' in router
    assert '@router.post("/coas", status_code=201)' in router
    assert '@router.post("/jobs", status_code=201)' in router


def test_label_studio_workspace_keeps_existing_page_and_adds_simple_operator_flow():
    wrapper = _read("frontend/src/pages/LabelStudioWorkspacePage.tsx")
    workflow = _read("frontend/src/components/InventoryDrivenLabelWorkflow.tsx")
    app = _read("frontend/src/App.tsx")
    assert "<InventoryDrivenLabelWorkflow />" in wrapper
    assert "<LabelStudioPage />" in wrapper
    assert 'page === "Label Studio" ? <LabelStudioWorkspacePage />' in app
    for step in ("1. Source batch", "2. End product", "3. Finished quantity", "4. Build & validate label preview", "5. Scan METRC package tag", "6. Finalize & print"):
        assert step in workflow
    assert 'Retail unit {index+1} of {run.quantity}' in workflow
    assert 'Reason required for reprint' in workflow
    assert '/api/v1/label-printing/inventory-sources?summary=true' in workflow
    assert '/api/v1/product-master?operation=production&search=&status=active&item_type=finished_good' in workflow
