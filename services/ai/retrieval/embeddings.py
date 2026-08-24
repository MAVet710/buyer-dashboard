from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests


@dataclass(frozen=True)
class EmbeddingHealth:
    configured: bool
    reachable: bool
    model: str
    detail: str = ""


class LocalEmbeddingProvider:
    """OpenAI-compatible local embeddings. Retrieval remains lexical if offline."""

    def __init__(self, *, base_url: str, model: str, api_key: str = "", timeout_seconds: float = 20.0) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = str(model or "").strip()
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def _endpoint(self) -> str:
        return f"{self.base_url}/embeddings" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/embeddings"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> EmbeddingHealth:
        if not self.base_url or not self.model:
            return EmbeddingHealth(False, False, self.model, "not configured")
        try:
            response = requests.post(self._endpoint(), headers=self._headers(), json={"model": self.model, "input": ["health"]}, timeout=min(self.timeout_seconds, 5.0))
            return EmbeddingHealth(True, response.ok, self.model, "ok" if response.ok else f"HTTP {response.status_code}")
        except requests.RequestException as exc:
            return EmbeddingHealth(True, False, self.model, exc.__class__.__name__)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        values = [str(text or "") for text in texts]
        if not values or not self.base_url or not self.model:
            return []
        try:
            response = requests.post(self._endpoint(), headers=self._headers(), json={"model": self.model, "input": values}, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json().get("data") or []
            ordered = sorted(data, key=lambda item: int(item.get("index") or 0))
            return [[float(value) for value in item.get("embedding") or []] for item in ordered]
        except (requests.RequestException, ValueError, TypeError):
            return []
