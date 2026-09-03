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


def test_finished_label_inherits_source_lineage_without_copying_source_packaging_claims():
    source = _read("modules/label_studio_workflow.py")
    for field in (
        '"harvest_date"',
        '"cultivated_by"',
        '"cultivator_license"',
        '"total_thc"',
        '"total_cbd"',
        '"total_terpenes"',
        '"laboratory"',
        '"test_date"',
        '"coa_reference"',
        '"batch_number"',
    ):
        assert field in source
    assert '"label": source_label' in source
    assert 'field in _SOURCE_INHERITED_LABEL_FIELDS' in source
    assert '"packaged_by"' not in source
    assert '"package_date"' not in source


def test_label_tag_validation_reuses_trusted_synced_metrc_inventory_without_provider_write():
    service = _read("modules/label_studio_workflow.py")
    router = _read("backend/app/routers/label_printing.py")
    assert "MetrcTagInventory" in service
    assert 'MetrcTagInventory.status == "available"' in service
    assert "not available in the synchronized METRC package-tag inventory" in service
    assert "resolve_metrc_context" in router
    assert "metrc.configured and metrc.trusted_mapping" in router
    assert "metrc_environment=metrc_environment" in router
    assert "fetch_all_available_package_tags" not in service


def test_label_production_api_preserves_existing_label_studio_routes():
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


def test_label_studio_workspace_integrates_simple_and_advanced_workflows():
    wrapper = _read("frontend/src/pages/LabelStudioWorkspacePage.tsx")
    workflow = _read("frontend/src/components/InventoryDrivenLabelWorkflow.tsx")
    app = _read("frontend/src/App.tsx")
    assert 'const [mode,setMode]=useState<LabelStudioMode>("create")' in wrapper
    assert "Create labels" in wrapper
    assert "Advanced LabelGuard & templates" in wrapper
    assert "<InventoryDrivenLabelWorkflow />" in wrapper
    assert "<LabelStudioPage />" in wrapper
    assert 'page === "Label Studio" ? <LabelStudioWorkspacePage />' in app
    for step in ("1. Source batch", "2. End product", "3. Finished quantity", "4. Build & validate label preview", "5. Scan METRC package tag", "6. Finalize & print"):
        assert step in workflow
    assert 'ariaLabel="Search source batches"' in workflow
    assert 'ariaLabel="Search finished products"' in workflow
    assert 'role="combobox"' in workflow
    assert 'Search strain, batch, SKU, or METRC package' in workflow
    assert 'Search product name, SKU, brand, or format' in workflow
    assert 'selectedSummary.on_hand' not in workflow
    assert 'theoretical material' not in workflow
    assert 'Expected material' not in workflow
    assert 'Retail unit {index+1} of {run.quantity}' in workflow
    assert '<strong>Source package:</strong> {sourcePackage}' in workflow
    assert '<strong>Source lot:</strong> {sourceLot}' in workflow
    assert 'Reason required for reprint' in workflow
    assert '/api/v1/label-printing/inventory-sources?summary=true' in workflow
    assert '/api/v1/product-master?operation=production&search=&status=active&item_type=finished_good' in workflow
