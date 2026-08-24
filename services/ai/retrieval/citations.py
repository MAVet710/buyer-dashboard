from __future__ import annotations

from typing import Any


def public_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip retrieved chunk text while preserving source provenance for callers."""
    output = []
    seen = set()
    for row in results:
        key = (row.get("title"), row.get("url"), row.get("page_or_section"))
        if key in seen:
            continue
        seen.add(key)
        output.append({
            field: row.get(field)
            for field in (
                "title", "source", "source_type", "authority_level", "jurisdiction",
                "effective_date", "updated_at", "version", "url", "page_or_section",
                "score", "precedence_score", "precedence_status",
            )
        })
    return output
