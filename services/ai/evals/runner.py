from __future__ import annotations

import argparse
import json
import os
import uuid

from services.ai.providers import DoobieProvider, GeminiProvider, LocalOpenAIProvider, OpenAIProvider
from services.ai.schemas import AGENT_RESPONSE_SCHEMA, AIRequest
from services.ai.validation import parse_structured
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL

from .cases import CASES
from .scoring import score_case


def configured_providers() -> dict[str, object]:
    providers: dict[str, object] = {}
    local_url = os.getenv("LOCAL_LLM_BASE_URL", "").strip()
    local_model = os.getenv("LOCAL_LLM_MODEL", "").strip()
    if local_url and local_model:
        providers["local"] = LocalOpenAIProvider(
            base_url=local_url,
            model=local_model,
            api_key=os.getenv("LOCAL_LLM_API_KEY", ""),
            timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "30")),
        )
    if os.getenv("GEMINI_API_KEY"):
        providers["gemini"] = GeminiProvider(api_key=os.getenv("GEMINI_API_KEY", ""), model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"):
        providers["openai"] = OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
        )
    doobie_key = (os.getenv("DOOBIE_API_KEY") or os.getenv("DOOBIELOGIC_API_KEY") or "").strip()
    if doobie_key:
        providers["doobie"] = DoobieProvider(
            base_url=(os.getenv("DOOBIE_BASE_URL") or os.getenv("DOOBIELOGIC_URL") or DEFAULT_DOOBIE_BASE_URL).strip(),
            api_key=doobie_key,
            model=os.getenv("DOOBIE_AI_MODEL", "doobie-cloud"),
        )
    return providers


def _benchmark_prompt(case) -> str:
    tool_instruction = (
        f" For this sanitized case, the expected read-only deterministic tool is '{case.expected_tool}'. Return that exact name in a top-level JSON field called 'tool'."
        if case.expected_tool
        else " If no deterministic tool is specified, return an empty top-level JSON field called 'tool'."
    )
    return (
        "This is a sanitized DoobieLogic provider-parity evaluation. There is no customer data in this prompt. "
        "Do not invent operational values, regulations, sources, or mutations. Return JSON with answer, summary, warnings, missing_data, and tool."
        + tool_instruction
        + f"\n\nCase: {case.prompt}"
    )


def run_benchmark(provider_name: str) -> list[dict]:
    providers = configured_providers()
    provider = providers.get(provider_name)
    if provider is None:
        raise SystemExit(f"Provider '{provider_name}' is not configured.")
    rows = []
    for case in CASES:
        request = AIRequest(
            request_id=uuid.uuid4().hex,
            system_prompt="You are running a sanitized DoobieLogic provider-parity evaluation. Never invent customer data or regulatory sources.",
            messages=[{"role": "user", "content": _benchmark_prompt(case)}],
            response_schema=AGENT_RESPONSE_SCHEMA,
            max_tokens=600,
            metadata={"agent_key": case.agent, "sanitized_context": {}},
        )
        try:
            response = provider.generate(request)
            parsed = parse_structured(response)
            answer = str((parsed or {}).get("answer") or response.text)
            selected_tool = str((parsed or {}).get("tool") or "").strip()
            score = score_case(
                case,
                answer=answer,
                structured_valid=parsed is not None,
                tool_names=[selected_tool] if selected_tool else [],
                latency_ms=response.latency_ms,
                estimated_cost_usd=response.estimated_cost_usd,
            )
            score.update({"provider": response.provider, "model": response.model})
        except Exception as exc:
            score = {"case": case.key, "agent": case.agent, "provider": provider_name, "passed": False, "error": exc.__class__.__name__}
        rows.append(score)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="DoobieLogic sanitized provider parity benchmark")
    parser.add_argument("--provider", default="local", choices=("local", "gemini", "openai", "doobie", "all"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    names = list(configured_providers()) if args.provider == "all" else [args.provider]
    output = {name: run_benchmark(name) for name in names}
    if args.json:
        print(json.dumps(output, indent=2))
        return
    for name, rows in output.items():
        passed = sum(1 for row in rows if row.get("passed"))
        print(f"{name}: {passed}/{len(rows)} passed")
        for row in rows:
            print(f"  {row['case']}: {'PASS' if row.get('passed') else 'FAIL'}")


if __name__ == "__main__":
    main()
