from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_restores_streamlit_executive_report_pack_controls():
    streamlit = read("app.py")
    web = read("frontend/src/pages/ExecutiveReportsPage.tsx")

    for label in (
        "Download Retail Ops Pack",
        "Download Production Ops Pack",
        "Download Company Executive Pack",
    ):
        assert label in streamlit
        assert label in web

    for filename in (
        "retail_ops_executive_pack_",
        "production_ops_executive_pack_",
        "company_executive_pack_",
    ):
        assert filename in streamlit
        assert filename in web


def test_report_pack_api_reuses_retained_streamlit_pdf_builders():
    backend = read("backend/app/routers/executive_reports.py")

    assert "from reports.executive_system import combine_report_pdfs" in backend
    assert "_build_buyer_executive_report_pdf" in backend
    assert "_build_white_label_repack_report_pdf" in backend
    assert "_build_coman_executive_report_pdf" in backend
    assert "_build_extraction_executive_report_pdf" in backend
    assert '@router.post("/packs/retail.pdf")' in backend
    assert '@router.post("/packs/production.pdf")' in backend
    assert '@router.post("/packs/company.pdf")' in backend
    assert 'title="DoobieLogic Retail Ops Executive Pack"' in backend
    assert 'division="Retail Ops"' in backend
    assert 'title="DoobieLogic Company Executive Pack"' in backend
    assert 'division="All Operations"' in backend


def test_white_label_report_payload_is_session_scoped_for_pack_reuse():
    api = read("frontend/src/lib/api.ts")
    web = read("frontend/src/pages/ExecutiveReportsPage.tsx")

    assert 'path === "/api/v1/executive-reports/white-label.pdf"' in api
    assert 'sessionStorage.setItem("white-label-current-report-payload"' in api
    assert 'sessionStorage.getItem("white-label-current-report-payload")' in web
    assert '{ white_label: whiteLabel }' in web
