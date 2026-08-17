"""Safe column-mapping assistance for Data Hub imports.

Only column names and requirement aliases are sent to Gemini. Row values are
never included. Suggestions are advisory and must be validated by the caller
before a file is normalized or published.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import os
import re
from typing import Any, Mapping, Sequence

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _score(source: str, aliases: Sequence[str]) -> float:
    source_norm = _norm(source)
    source_tokens = set(source_norm.split())
    best = 0.0
    for alias in aliases:
        alias_norm = _norm(alias)
        if not alias_norm:
            continue
        if source_norm == alias_norm:
            return 1.0
        alias_tokens = set(alias_norm.split())
        overlap = len(source_tokens & alias_tokens) / max(1, len(source_tokens | alias_tokens))
        ratio = SequenceMatcher(None, source_norm, alias_norm).ratio()
        containment = 0.9 if alias_norm in source_norm or source_norm in alias_norm else 0.0
        best = max(best, overlap, ratio, containment)
    return min(1.0, best)


def _parse_json_payload(text: str) -> list[dict[str, Any]]:
    value = str(text or "").strip()
    if not value:
        return []
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("[")
        end = value.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            parsed = json.loads(value[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("mappings") or parsed.get("proposals") or []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _validate_proposals(
    proposals: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str],
    requirements: Mapping[str, Sequence[str]],
    already_mapped: Mapping[str, str],
) -> list[dict[str, Any]]:
    allowed_columns = {str(column): str(column) for column in columns}
    allowed_fields = set(requirements)
    used_columns = {str(value) for value in already_mapped.values() if value}
    output: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for raw in proposals:
        field = str(raw.get("required_field") or raw.get("field") or "").strip()
        source = str(raw.get("source_column") or raw.get("column") or "").strip()
        if field not in allowed_fields or source not in allowed_columns:
            continue
        if field in already_mapped or field in seen_fields or source in used_columns:
            continue
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.5:
            continue
        output.append(
            {
                "required_field": field,
                "source_column": allowed_columns[source],
                "confidence": round(confidence, 2),
                "reason": str(raw.get("reason") or "Header meaning appears compatible.")[:240],
            }
        )
        used_columns.add(source)
        seen_fields.add(field)
    return output


def _heuristic_proposals(
    columns: Sequence[str],
    requirements: Mapping[str, Sequence[str]],
    already_mapped: Mapping[str, str],
) -> list[dict[str, Any]]:
    used = {str(value) for value in already_mapped.values() if value}
    proposals: list[dict[str, Any]] = []
    for field, aliases in requirements.items():
        if field in already_mapped:
            continue
        candidates = [
            (column, _score(str(column), (field, *tuple(aliases))))
            for column in columns
            if str(column) not in used
        ]
        if not candidates:
            continue
        source, score = max(candidates, key=lambda item: item[1])
        if score < 0.62:
            continue
        proposals.append(
            {
                "required_field": field,
                "source_column": str(source),
                "confidence": round(score, 2),
                "reason": "Header similarity to the required field/known aliases.",
            }
        )
        used.add(str(source))
    return proposals


def suggest_column_mapping(
    columns: Sequence[str],
    requirements: Mapping[str, Sequence[str]],
    *,
    existing_matches: Mapping[str, str] | None = None,
    dataset_label: str = "uploaded dataset",
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Suggest unresolved mappings without reading or transmitting row values."""
    clean_columns = [str(column) for column in columns if str(column).strip()]
    matches = {str(k): str(v) for k, v in dict(existing_matches or {}).items() if v}
    unresolved = [field for field in requirements if field not in matches]
    if not unresolved:
        return {"provider": "deterministic", "proposals": [], "unresolved": []}

    heuristic = _heuristic_proposals(clean_columns, requirements, matches)
    confident = [proposal for proposal in heuristic if proposal["confidence"] >= 0.86]
    provisional_matches = {**matches, **{p["required_field"]: p["source_column"] for p in confident}}
    still_unresolved = [field for field in requirements if field not in provisional_matches]

    key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    ai_proposals: list[dict[str, Any]] = []
    if still_unresolved and key and genai is not None and types is not None:
        requirement_payload = {
            field: [str(alias) for alias in requirements[field]]
            for field in still_unresolved
        }
        prompt = (
            "You are a read-only data-column mapping assistant. Map required fields to the most likely "
            "source columns using ONLY the column headers below. Do not infer or request row values. "
            "Return JSON only as an array of objects with required_field, source_column, confidence "
            "(0 to 1), and reason. Use an exact source_column string from the provided list. If uncertain, "
            "omit the field rather than guessing. A source column should not satisfy multiple required fields.\n\n"
            f"Dataset: {dataset_label}\n"
            f"Source columns: {json.dumps(clean_columns)}\n"
            f"Required fields and known aliases: {json.dumps(requirement_payload)}\n"
        )
        try:
            response = genai.Client(api_key=key).models.generate_content(
                model=str(model or DEFAULT_GEMINI_MODEL),
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=800,
                    response_mime_type="application/json",
                ),
            )
            ai_proposals = _validate_proposals(
                _parse_json_payload(str(getattr(response, "text", "") or "")),
                columns=clean_columns,
                requirements=requirements,
                already_mapped=provisional_matches,
            )
        except Exception:
            ai_proposals = []

    merged: dict[str, dict[str, Any]] = {
        proposal["required_field"]: proposal for proposal in confident
    }
    for proposal in ai_proposals:
        merged[proposal["required_field"]] = proposal

    # If Gemini is unavailable or declines a field, expose moderate-confidence
    # heuristics as a reviewable suggestion rather than silently applying them.
    for proposal in heuristic:
        merged.setdefault(proposal["required_field"], proposal)

    proposals = list(merged.values())
    mapped_fields = set(matches) | {proposal["required_field"] for proposal in proposals}
    return {
        "provider": "Gemini + header matcher" if ai_proposals else "header matcher",
        "proposals": proposals,
        "unresolved": [field for field in requirements if field not in mapped_fields],
        "privacy_note": "Only column headers were evaluated; uploaded row values were not sent to the mapping agent.",
    }
