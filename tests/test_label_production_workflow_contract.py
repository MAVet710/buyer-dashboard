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
    assert 'event_type="reprinted"' not in source
    assert 'self._event(session, run, "reprinted"' in source
    assert 'A reprint reason is required after the first print.' in source


def test_finished_label_snapshots_testing_lineage_without_becoming_inventory_consumption_math():
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
    assert 'field in _SOURCE_INHERITED_LABEL_FIELDS' in source
    assert '"label": dict(source.get("label") or {})' in source
    assert 'expected_material_quantity=0.0' in source
    assert 'planned_quantity=0.0' in source
    assert 'Source inventory is insufficient' not in source


def test_label_layout_contract_supports_single_split_duo_and_bulk_prints():
    packaging = _read("modules/product_master/packaging.py")
    workflow = _read("modules/label_studio_workflow.py")
    product_master = _read("frontend/src/pages/ProductMasterPage.tsx")
    label_ui = _read("frontend/src/components/InventoryDrivenLabelWorkflow.tsx")
    migration = _read("migrations/versions/0069_product_label_print_layouts.py")

    for value in ("compact_single", "compact_split", "bulk_barcode"):
        assert value in packaging
        assert value in label_ui
    assert "label_width_in" in packaging and "label_height_in" in packaging
    assert "label_source_count" in packaging
    assert 'source_count not in {1, 2}' in packaging
    assert "Two-source labels require the compact split layout" in packaging
    assert '"print_layout": print_layout' in workflow
    assert '"sources": source_snapshots' in workflow
    assert "secondary_source_lot_id" in workflow
    assert "This product needs two tested source batches for its Duo label." in workflow
    assert "Compact split · Duo / flower pouch" in product_master
    assert "1 source · flower / single product" in product_master
    assert "2 sources · Duo" in product_master
    assert "Second tested source" in label_ui
    assert "@page{size:${printLayout.width_in}in ${printLayout.height_in}in" in label_ui
    assert "BulkBarcodeLabel" in label_ui
    assert "CompactSplitLabel" in label_ui
    assert "label_source_count" in migration


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


def test_label_production_api_preserves_existing_routes_and_accepts_second_source():
    router = _read("backend/app/routers/label_printing.py")
    for route in (
        '@router.post("/production-runs", status_code=201)',
        '@router.post("/production-runs/{run_id}/tag")',
        '@router.post("/production-runs/{run_id}/print")',
        '@router.post("/production-runs/{run_id}/transition")',
    ):
        assert route in router
    assert "secondary_source_lot_id" in router
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
    assert 'does not reserve, consume, or validate a production quantity' in workflow
    assert 'aria-label="Printable retail labels"' in workflow
    assert 'Reason required for reprint' in workflow
    assert '/api/v1/label-printing/inventory-sources?summary=true' in workflow
    assert '/api/v1/product-master?operation=production&search=&status=active&item_type=finished_good' in workflow
