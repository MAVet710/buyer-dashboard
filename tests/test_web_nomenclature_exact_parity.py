from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_react_nomenclature_mapper_restores_streamlit_tabs_controls_and_release_gate():
    source = (ROOT / "frontend" / "src" / "pages" / "NomenclatureMapperPage.tsx").read_text(encoding="utf-8")
    for label in [
        "Dutchie-to-METRC Nomenclature",
        "Apply each dispensary&apos;s approved Dutchie product names to the item rows in a METRC manifest.",
        "Catalog Items",
        "Learned Mappings",
        "Export Shape",
        "1 - Dutchie Catalog",
        "2 - Apply Names to METRC",
        "Mapping Library",
        "Upload the store&apos;s approved catalog",
        "Dutchie catalog",
        "Save as this organization's Dutchie catalog",
        "Upload the METRC manifest to rename",
        "METRC manifest",
        "Unique METRC Names",
        "Ready",
        "Needs Review",
        "Unmatched",
        "Review suggested names",
        "Create New Product",
        "Create genuinely new Dutchie products",
        "I approve these new names for this organization&apos;s Dutchie catalog.",
        "Add new products to the Dutchie naming catalog",
        "I reviewed the suggested names and confirmed they match this store&apos;s Dutchie catalog.",
        "Confirm names and remember mappings",
        "Download Dutchie product names",
        "Organization naming source",
        "Correct Item Name",
    ]:
        assert label in source

    assert 'accept=".csv,.xlsx"' in source
    assert 'accept=".csv,.xlsx,.xls"' not in source
    assert "/nomenclature/catalog/preview" in source
    assert "setCatalogPreview" in source
    assert "setConfirmedSignature" in source
    assert "Confirm the reviewed names to unlock the one-column export." in source
    assert "Tenant Scope" not in source


def test_nomenclature_backend_supports_streamlit_preview_then_save_and_new_product_flow():
    source = (ROOT / "backend" / "app" / "routers" / "parity_tools.py").read_text(encoding="utf-8")
    assert '@router.post("/nomenclature/catalog/preview")' in source
    assert '"detected": len(frame)' in source
    assert '"preview": _catalog_records(frame, limit=100)' in source
    assert '@router.post("/nomenclature/catalog")' in source
    assert "replace_catalog" in source
    assert '@router.post("/nomenclature/catalog/items")' in source
    assert "add_catalog_items" in source
    assert '"proposed_new_name": propose_new_catalog_name' in source
    assert '@router.post("/nomenclature/confirm")' in source
    assert '@router.post("/nomenclature/export")' in source
    assert 'filename="Correct_METRC_Item_Names.xlsx"' in source
