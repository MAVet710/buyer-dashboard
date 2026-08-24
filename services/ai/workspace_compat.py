from __future__ import annotations

import os
from typing import Mapping

import pandas as pd

from services.agent_registry import AgentProfile, PROFILES, resolve_agent_profile
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL

from .datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec
from .providers import DoobieProvider, GeminiProvider, LocalOpenAIProvider, OpenAIProvider
from .router import ProviderRouter
from .runtime import AgentRuntime


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().casefold() not in {"0", "false", "no", "off"}


def _operation_type(app_mode: str, profile: AgentProfile) -> str:
    mode = str(app_mode or "").casefold()
    if "production" in mode or profile.key in {"coman", "extraction", "repack", "cultivation"}:
        return "production"
    return "retail"


class DoobieWorkspaceAgent:
    """Compatibility adapter that routes legacy current-view DataFrames through AgentRuntime."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        profile: AgentProfile | None = None,
    ) -> None:
        self.profile = profile or PROFILES["buyer"]
        self._gemini_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self._gemini_model = str(model or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite").strip()
        self._last_model = ""
        self._last_provider = ""

    def _providers(self) -> tuple[dict[str, object], list[str], bool]:
        providers: dict[str, object] = {}
        local_base = str(os.getenv("LOCAL_LLM_BASE_URL") or "").strip()
        local_model = str(os.getenv("LOCAL_LLM_MODEL") or "").strip()
        if local_base and local_model:
            providers["local"] = LocalOpenAIProvider(
                base_url=local_base,
                model=local_model,
                api_key=str(os.getenv("LOCAL_LLM_API_KEY") or "").strip(),
                timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS") or 30),
                max_tokens=int(os.getenv("LOCAL_LLM_MAX_TOKENS") or 1400),
                temperature=float(os.getenv("LOCAL_LLM_TEMPERATURE") or 0.2),
            )
        if self._gemini_key:
            providers["gemini"] = GeminiProvider(api_key=self._gemini_key, model=self._gemini_model)
        openai_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
        openai_model = str(os.getenv("OPENAI_MODEL") or "").strip()
        if openai_key and openai_model:
            providers["openai"] = OpenAIProvider(
                api_key=openai_key,
                model=openai_model,
                base_url=str(os.getenv("OPENAI_BASE_URL") or "https://api.openai.com").strip(),
                timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS") or 30),
            )
        doobie_key = str(os.getenv("DOOBIE_API_KEY") or "").strip()
        if doobie_key:
            providers["doobie"] = DoobieProvider(
                base_url=str(os.getenv("DOOBIE_BASE_URL") or DEFAULT_DOOBIE_BASE_URL).strip(),
                api_key=doobie_key,
                model=str(os.getenv("DOOBIE_AI_MODEL") or "doobie-cloud").strip(),
            )
        order = [value.strip().casefold() for value in str(os.getenv("AI_PROVIDER_ORDER") or "local,gemini,openai,doobie").split(",") if value.strip()]
        mode = str(os.getenv("AI_PROVIDER_MODE") or "local_first").strip().casefold()
        if mode == "local_only":
            order = ["local"]
        allow_cloud = _truthy(os.getenv("AI_ALLOW_CLOUD_FALLBACK"), True) and mode != "local_only"
        return providers, order, allow_cloud

    @property
    def enabled(self) -> bool:
        providers, order, _allow_cloud = self._providers()
        return any(name in providers for name in order)

    @property
    def model(self) -> str:
        return self._last_model or self._gemini_model

    @property
    def provider(self) -> str:
        return self._last_provider

    def run(
        self,
        question: str,
        datasets: Mapping[str, pd.DataFrame],
        app_mode: str = "",
        section: str = "",
        history: list[dict[str, str]] | None = None,
        profile: AgentProfile | None = None,
        organization_id: str = "streamlit-current-org",
        facility_id: str = "streamlit-current-facility",
    ) -> str:
        active = profile or self.profile or resolve_agent_profile(app_mode, section)
        registry = DatasetRegistry()
        for raw_name, raw_frame in dict(datasets or {}).items():
            if not isinstance(raw_frame, pd.DataFrame):
                continue
            name = str(raw_name or "").strip().casefold()
            if not name:
                continue
            frame = raw_frame.copy()
            registry.register(DatasetSpec(
                key=name,
                domain=active.key,
                description=f"Current authorized {name.replace('_', ' ')} view",
                loader=lambda _access, value=frame: value.copy(),
                allowed_agents=(active.key,),
                allow_business_columns=True,
                freshness="current Streamlit workspace view",
                max_tool_rows=50,
            ))
        providers, order, allow_cloud = self._providers()
        runtime = AgentRuntime(
            provider_router=ProviderRouter(providers, order=order, allow_cloud_fallback=allow_cloud),
            dataset_registry=registry,
        )
        operation = _operation_type(app_mode, active)
        capabilities = frozenset({"retail", "production", "cultivation", "commercial"})
        result = runtime.run(
            profile=active,
            access=DatasetAccessContext(
                organization_id or "streamlit-current-org",
                facility_id or "streamlit-current-facility",
                "streamlit-current-user",
                "dev",
                capabilities,
                operation_type=operation,
            ),
            question=str(question or "").strip(),
            history=history,
        )
        self._last_model = result.model
        self._last_provider = result.provider
        if result.provider == "unavailable":
            raise RuntimeError(result.answer)
        return result.answer
