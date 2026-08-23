from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.app.routers.compliance_qa import ComplianceQuery, template


ROOT = Path(__file__).resolve().parents[1]


def test_compliance_qa_defaults_and_template_match_streamlit_source():
    payload = ComplianceQuery()
    assert payload.state == "CA"
    assert payload.scope == "adult-use"
    assert payload.topic == "packaging"
    assert payload.question == "What are the packaging requirements for adult-use products?"

    response = template()
    assert response.headers["content-disposition"] == 'attachment; filename="compliance_sources_template.csv"'
    frame = pd.read_csv(BytesIO(response.body))
    assert frame.columns.tolist() == [
        "state",
        "scope",
        "topic",
        "answer",
        "source_citation",
        "source_url",
        "last_updated",
        "review_status",
    ]
    assert frame.to_dict("records") == [
        {
            "state": "CA",
            "scope": "adult-use",
            "topic": "packaging",
            "answer": "Child-resistant packaging is required before retail sale.",
            "source_citation": "16 CCR § 17407",
            "source_url": "https://cannabis.ca.gov/",
            "last_updated": "2026-01-15",
            "review_status": "reviewed",
        }
    ]


def test_react_compliance_qa_surface_matches_streamlit_labels_defaults_and_order():
    source = (ROOT / "frontend" / "src" / "pages" / "ComplianceQAPage.tsx").read_text(encoding="utf-8")
    for label in [
        "🧭 Compliance Q&amp;A",
        "Grounded compliance answers from structured sources only. Upload reviewed source rows and query by state/scope/topic.",
        "Required source columns",
        "Download compliance source template (CSV)",
        "compliance_sources_template.csv",
        "Upload structured compliance sources (CSV)",
        "METRC State",
        "Scope",
        "Topic",
        "Compliance question",
        "What are the packaging requirements for adult-use products?",
        "Answer from structured sources",
        "Upload structured compliance source rows first.",
    ]:
        assert label in source

    assert 'useState("CA")' in source
    assert 'useState("adult-use")' in source
    assert 'useState("packaging")' in source
    assert '<option value="adult-use">adult-use</option><option value="medical">medical</option>' in source
    assert 'accept=".csv,text/csv"' in source
    assert "Grounded Compliance Q&A" not in source
    assert 'value="both"' not in source
    assert "two-column-grid" not in source


def test_compliance_query_uses_exact_state_scope_topic_retrieval_not_question_ranking():
    source = (ROOT / "backend" / "app" / "routers" / "compliance_qa.py").read_text(encoding="utf-8")
    assert "repository.query(" in source
    assert "state=payload.state" in source
    assert "scope=payload.scope" in source
    assert "topic=payload.topic" in source
    assert "question_tokens" not in source
    assert "ranked = sorted" not in source
    assert 'WRITE_ROLES = {"dev", "admin", "buyer", "qa", "supervisor"}' in source
