from typing import List


def get_embedding(text: str) -> List[float]:
    _ = text
    raise RuntimeError("Local embedding backends are disabled. Buyer Dashboard now routes AI through DoobieLogic only.")
