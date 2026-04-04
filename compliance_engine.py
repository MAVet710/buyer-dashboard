"""Structured compliance retrieval scaffolding.

Compliance answers must be grounded in structured source rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass
class ComplianceSource:
    state: str
    scope: str  # medical | adult-use | both
    topic: str
    answer: str
    source_citation: str
    source_url: str
    last_updated: date
    review_status: str  # reviewed | draft | stale


REQUIRED_COMPLIANCE_FIELDS = [
    "state",
    "scope",
    "source citation",
    "source url",
    "last updated date",
    "confidence or review status",
]


class ComplianceRepository:
    def __init__(self, rows: Iterable[ComplianceSource] | None = None):
        self._rows = list(rows or [])

    def add(self, source: ComplianceSource) -> None:
        self._rows.append(source)

    def query(self, state: str, scope: str, topic: str) -> list[ComplianceSource]:
        state_n = state.strip().lower()
        scope_n = scope.strip().lower()
        topic_n = topic.strip().lower()

        def _match(row: ComplianceSource) -> bool:
            row_scope = row.scope.lower()
            scope_match = row_scope == "both" or row_scope == scope_n
            return (
                row.state.lower() == state_n
                and scope_match
                and topic_n in row.topic.lower()
            )

        return [r for r in self._rows if _match(r)]


def format_compliance_answer(sources: list[ComplianceSource]) -> str:
    if not sources:
        return (
            "No structured compliance source found for that query. "
            "Please add a reviewed source record before answering."
        )

    lines: list[str] = []
    for item in sources:
        lines.append(f"State: {item.state}")
        lines.append(f"Scope: {item.scope}")
        lines.append(f"Answer: {item.answer}")
        lines.append(f"Source citation: {item.source_citation}")
        lines.append(f"Source URL: {item.source_url}")
        lines.append(f"Last updated date: {item.last_updated.isoformat()}")
        lines.append(f"Confidence / review status: {item.review_status}")
        lines.append("---")

    return "\n".join(lines)
