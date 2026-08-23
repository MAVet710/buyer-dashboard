from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from tests.test_web_inventory_api import _engine


ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-Organization-Id":"org-1","X-Facility-Id":"facility-1","X-User-Id":"buyer@example.com","X-User-Role":"buyer"}


def _post(payload):
    engine=_engine();app.dependency_overrides[get_engine]=lambda:engine;client=TestClient(app)
    try:return client.post("/api/v1/parity-tools/ma-flower-equivalency",headers=HEADERS,json=payload)
    finally:app.dependency_overrides.clear()


def test_web_equivalency_preserves_decimal_precision_and_exact_validation():
    precise=_post({"mode":"concentrate_vape","quantity":"7","grams":"0.123456789"})
    blank=_post({"mode":"edible","quantity":"1","active_thc_mg":""})
    fractional=_post({"mode":"edible","quantity":"1.5","active_thc_mg":"100"})
    assert precise.status_code==200
    assert precise.json()["per_unit_display"]=="0.6914"
    assert precise.json()["package_total_display"]=="4.8395"
    assert blank.status_code==422 and blank.json()["detail"]=="Enter labeled active THC in milligrams per unit to calculate flower equivalency."
    assert fractional.status_code==422 and fractional.json()["detail"]=="package quantity must be a positive whole number."


def test_web_infused_preroll_returns_exact_breakdown_displays():
    response=_post({"mode":"infused_preroll","quantity":"5","finished_grams_per_joint":"1","infusion_grams_per_joint":"0.25"})
    assert response.status_code==200
    assert response.json()["flower_weight_display"]=="0.75"
    assert response.json()["infusion_equivalency_display"]=="1.4"
    assert response.json()["per_unit_display"]=="2.15"
    assert response.json()["package_total_display"]=="10.75"


def test_react_equivalency_preserves_streamlit_source_order_and_labels():
    source=(ROOT/"frontend"/"src"/"pages"/"MAFlowerEquivalencyPage.tsx").read_text(encoding="utf-8")
    labels=["RETAIL OPS · PACKAGE CONFIGURATION","Calculate the Dutchie flower-equivalency value for one package.","Operational package-entry calculator.","Product category","Dabs / Concentrate","Vape Cart","Disposable Vape","Infused Edible / Beverage","Grams/concentration per unit (g)","Labeled active THC per unit (mg)","Finished weight per joint (g)","Infusion material per joint (g)","Joints in package (whole number)","Calculate equivalency","Calculation breakdown","Dutchie entry value","Unformatted numeric result","Copy value"]
    for label in labels:assert label in source
    category_block=source[source.index("const CATEGORIES"):source.index("as const")]
    assert [category_block.index(label) for label in labels[4:8]]==sorted(category_block.index(label) for label in labels[4:8])
    assert "Complete the required fields, then calculate the package value." in source
    assert "Calculator basis" not in source
