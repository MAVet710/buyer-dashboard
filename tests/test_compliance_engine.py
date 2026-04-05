from datetime import date

from compliance_engine import ComplianceRepository, ComplianceSource, format_compliance_answer


def test_repository_query_matches_state_scope_and_topic():
    repo = ComplianceRepository(
        [
            ComplianceSource(
                state="CA",
                scope="adult-use",
                topic="packaging rules",
                answer="Use child-resistant packaging.",
                source_citation="16 CCR § 17407",
                source_url="https://example.com/ca/packaging",
                last_updated=date(2026, 1, 15),
                review_status="reviewed",
            ),
            ComplianceSource(
                state="CA",
                scope="medical",
                topic="labeling",
                answer="Medical labeling rule.",
                source_citation="16 CCR § 17408",
                source_url="https://example.com/ca/labeling",
                last_updated=date(2026, 1, 16),
                review_status="reviewed",
            ),
        ]
    )

    results = repo.query(state="CA", scope="adult-use", topic="packaging")
    assert len(results) == 1
    assert results[0].source_citation == "16 CCR § 17407"


def test_repository_query_scope_both_matches():
    repo = ComplianceRepository(
        [
            ComplianceSource(
                state="NV",
                scope="both",
                topic="transport",
                answer="Manifest required for transfers.",
                source_citation="NAC 453D.500",
                source_url="https://example.com/nv/transport",
                last_updated=date(2026, 2, 2),
                review_status="reviewed",
            )
        ]
    )

    results = repo.query(state="NV", scope="medical", topic="transport")
    assert len(results) == 1


def test_format_compliance_answer_contains_required_fields():
    sources = [
        ComplianceSource(
            state="CO",
            scope="adult-use",
            topic="storage",
            answer="Store inventory in secure areas.",
            source_citation="1 CCR 212-3",
            source_url="https://example.com/co/storage",
            last_updated=date(2026, 3, 1),
            review_status="reviewed",
        )
    ]

    text = format_compliance_answer(sources)
    assert "State: CO" in text
    assert "Scope: adult-use" in text
    assert "Source citation: 1 CCR 212-3" in text
    assert "Source URL: https://example.com/co/storage" in text
    assert "Last updated date: 2026-03-01" in text
    assert "Confidence / review status: reviewed" in text
