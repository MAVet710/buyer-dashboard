"""Provider-neutral, header-only Data Hub mapping assistance.

Flow: approved tenant memory -> deterministic aliases -> local-first AI for
unresolved headers -> validation -> human review -> approved memory. Row values
are never passed to the mapping model.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import os
import re
from typing import Any, Mapping, Sequence

from sqlalchemy import Engine

from services.ai.mapping_memory import MappingMemory
from services.ai.providers import GeminiProvider, LocalOpenAIProvider, OpenAIProvider
from services.ai.router import ProviderRouter
from services.ai.schemas import AIRequest
from services.ai.validation import parse_structured


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


def _validate_proposals(proposals: Sequence[Mapping[str, Any]], *, columns: Sequence[str], requirements: Mapping[str, Sequence[str]], already_mapped: Mapping[str, str]) -> list[dict[str, Any]]:
    allowed_columns = {str(column): str(column) for column in columns}
    allowed_fields = set(requirements)
    used_columns = {str(value) for value in already_mapped.values() if value}
    output: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for raw in proposals:
        field = str(raw.get("required_field") or raw.get("field") or "").strip()
        source = str(raw.get("source_column") or raw.get("column") or "").strip()
        if field not in allowed_fields or source not in allowed_columns or field in already_mapped or field in seen_fields or source in used_columns:
            continue
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.5:
            continue
        output.append({"required_field": field, "source_column": allowed_columns[source], "confidence": round(confidence, 2), "reason": str(raw.get("reason") or "Header meaning appears compatible.")[:240]})
        used_columns.add(source)
        seen_fields.add(field)
    return output


def _heuristic_proposals(columns: Sequence[str], requirements: Mapping[str, Sequence[str]], already_mapped: Mapping[str, str]) -> list[dict[str, Any]]:
    used = {str(value) for value in already_mapped.values() if value}
    proposals: list[dict[str, Any]] = []
    for field, aliases in requirements.items():
        if field in already_mapped:
            continue
        candidates = [(column, _score(str(column), (field, *tuple(aliases)))) for column in columns if str(column) not in used]
        if not candidates:
            continue
        source, score = max(candidates, key=lambda item: item[1])
        if score < 0.62:
            continue
        proposals.append({"required_field": field, "source_column": str(source), "confidence": round(score, 2), "reason": "Header similarity to the required field/known aliases."})
        used.add(str(source))
    return proposals


def _env_router() -> ProviderRouter:
    providers = {}
    local_url = os.getenv("LOCAL_LLM_BASE_URL", "").strip()
    local_model = os.getenv("LOCAL_LLM_MODEL", "").strip()
    if local_url and local_model:
        providers["local"] = LocalOpenAIProvider(base_url=local_url, model=local_model, api_key=os.getenv("LOCAL_LLM_API_KEY", ""), timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "30")), max_tokens=800, temperature=0.0)
    if os.getenv("GEMINI_API_KEY"):
        providers["gemini"] = GeminiProvider(api_key=os.getenv("GEMINI_API_KEY", ""), model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"):
        providers["openai"] = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY", ""), model=os.getenv("OPENAI_MODEL", ""), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"))
    order = [value.strip().casefold() for value in os.getenv("AI_PROVIDER_ORDER", "local,gemini,openai").split(",") if value.strip()]
    allow_cloud = os.getenv("AI_ALLOW_CLOUD_FALLBACK", "true").strip().casefold() not in {"0", "false", "no", "off"}
    return ProviderRouter(providers, order=order, allow_cloud_fallback=allow_cloud)


def record_approved_mappings(*, engine: Engine, organization_id: str, facility_id: str, dataset_type: str, source_vendor: str, columns: Sequence[str], mappings: Mapping[str, str]) -> None:
    memory = MappingMemory(engine)
    for canonical, source in mappings.items():
        if source:
            memory.save(organization_id=organization_id, facility_id=facility_id, dataset_type=dataset_type, source_vendor=source_vendor, source_header=str(source), canonical_field=str(canonical), columns=columns, confidence=1.0, origin="human_review", human_approved=True)


def suggest_column_mapping(
    columns: Sequence[str],
    requirements: Mapping[str, Sequence[str]],
    *,
    existing_matches: Mapping[str, str] | None = None,
    dataset_label: str = "uploaded dataset",
    api_key: str | None = None,
    model: str | None = None,
    engine: Engine | None = None,
    organization_id: str = "",
    facility_id: str = "",
    source_vendor: str = "",
    provider_router: ProviderRouter | None = None,
) -> dict[str, Any]:
    """Suggest unresolved mappings using headers only; never reads row values."""
    clean_columns = [str(column) for column in columns if str(column).strip()]
    matches = {str(key): str(value) for key, value in dict(existing_matches or {}).items() if value}
    memory_matches: dict[str, str] = {}
    memory_source = source_vendor or dataset_label
    if engine is not None and organization_id and facility_id:
        memory_matches = MappingMemory(engine).approved(organization_id=organization_id, facility_id=facility_id, dataset_type=dataset_label, source_vendor=memory_source, columns=clean_columns)
        for key, value in memory_matches.items():
            matches.setdefault(key, value)
    unresolved = [field for field in requirements if field not in matches]
    if not unresolved:
        return {"provider": "mapping memory" if memory_matches else "deterministic", "proposals": [], "unresolved": [], "memory_matches": memory_matches, "privacy_note": "Only column headers were evaluated; uploaded row values were not sent to the mapping agent."}

    heuristic = _heuristic_proposals(clean_columns, requirements, matches)
    confident = [proposal for proposal in heuristic if proposal["confidence"] >= 0.86]
    provisional_matches = {**matches, **{proposal["required_field"]: proposal["source_column"] for proposal in confident}}
    still_unresolved = [field for field in requirements if field not in provisional_matches]
    ai_proposals: list[dict[str, Any]] = []
    provider_name = ""
    if still_unresolved:
        requirement_payload = {field: [str(alias) for alias in requirements[field]] for field in still_unresolved}
        prompt = (
            "Map required fields to source columns using ONLY the provided column headers. Never request or infer row values. "
            "Return one JSON object with a mappings array. Each mapping must include required_field, source_column, confidence (0-1), and reason. "
            "Use an exact source_column from the list, omit uncertain mappings, and never reuse a source column.\n\n"
            f"Dataset: {dataset_label}\nSource columns: {json.dumps(clean_columns)}\nRequired fields and aliases: {json.dumps(requirement_payload)}"
        )
        router = provider_router or _env_router()
        if api_key:
            router = ProviderRouter({"gemini": GeminiProvider(api_key=api_key, model=model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))}, order=["gemini"], allow_cloud_fallback=True)
        try:
            request = AIRequest(request_id="mapping", system_prompt="You are DoobieLogic's read-only header mapper. Headers only; no row values.", messages=[{"role": "user", "content": prompt}], response_schema={"type": "object", "properties": {"mappings": {"type": "array"}}, "required": ["mappings"]}, temperature=0.0, max_tokens=800)
            decision = router.generate(request, validate=lambda response: (parse_structured(response) is not None, "malformed_mapping_json"), require_structured=True)
            parsed = parse_structured(decision.response) or {}
            raw = parsed.get("mappings") or parsed.get("proposals") or []
            ai_proposals = _validate_proposals([item for item in raw if isinstance(item, dict)], columns=clean_columns, requirements=requirements, already_mapped=provisional_matches)
            provider_name = decision.response.provider
        except Exception:
            ai_proposals = []

    merged = {proposal["required_field"]: proposal for proposal in confident}
    for proposal in ai_proposals:
        merged[proposal["required_field"]] = proposal
    for proposal in heuristic:
        merged.setdefault(proposal["required_field"], proposal)
    proposals = list(merged.values())
    mapped_fields = set(matches) | {proposal["required_field"] for proposal in proposals}
    return {"provider": f"{provider_name} + header matcher" if ai_proposals else "header matcher", "proposals": proposals, "unresolved": [field for field in requirements if field not in mapped_fields], "memory_matches": memory_matches, "privacy_note": "Only column headers were evaluated; uploaded row values were not sent to the mapping agent."}
