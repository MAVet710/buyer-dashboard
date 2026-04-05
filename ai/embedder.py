import os
from typing import List

import requests



def get_embedding(text: str) -> List[float]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_EMBED_MODEL", "embeddinggemma")

    resp = requests.post(
        f"{base_url}/api/embed",
        json={"model": model, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"][0]
