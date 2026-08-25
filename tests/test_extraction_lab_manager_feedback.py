from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_extraction_jurisdiction_catalog_covers_regulated_states_dc_and_territories():
    source = (ROOT / "frontend" / "src" / "lib" / "cannabisJurisdictions.ts").read_text(encoding="utf-8")
    codes = re.findall(r'\{ code: "([A-Z]{2})", name:', source)

    assert len(codes) == 46
    assert len(set(codes)) == 46
    for code in ["MN", "DC", "GU", "PR", "VI", "MP"]:
        assert code in codes
    assert 'code: "MN", name: "Minnesota", program: "adult-use-and-medical"' in source
    assert 'code: "MP", name: "Northern Mariana Islands", program: "adult-use", territory: true' in source


def test_extraction_run_entry_applies_lab_manager_feedback():
    source = (ROOT / "frontend" / "src" / "pages" / "ExtractionCommandCenterPage.tsx").read_text(encoding="utf-8")

    assert "CANNABIS_JURISDICTION_OPTIONS" in source
    assert source.count("cannabisJurisdictionLabel(value)") == 2
    assert 'PRODUCT_TYPE_OPTIONS=["Isolate","THCa"' in source
    assert 'diamond_fraction_g:"THCa Fraction (g)"' in source
    assert "Diamonds (THCa)" not in source
    assert "Diamond Fraction (g)" not in source

    assert "Residual Loss (auto, g)" in source
    assert "readOnly" in source
    assert "Math.max(0,runForm.intermediate_output_g-finalPreview)" in source
    assert "{...runForm,residual_loss_g:calculatedResidualLoss}" in source
