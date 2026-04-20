from ai.llm_client import get_chat_model, get_llm_client

SYSTEM_PROMPT = """
You are a cannabis buyer intelligence assistant.

Rules:
- Prioritize retrieved documents over assumptions.
- Do not invent regulations, pricing rules, or buyer metrics.
- Focus on assortment gaps, DOS/DOH, velocity, pricing ladders, category coverage, vendor performance, and margin-aware buying.
- If the retrieved context is weak, say that clearly.
"""


def detect_module(question: str) -> str:
    q = question.lower()

    if any(word in q for word in ["coa", "terpene", "potency", "thca", "delta-8", "delta 8"]):
        return "coa"
    if any(word in q for word in ["bho", "rosin", "co2", "yield", "extraction", "solvent"]):
        return "extraction"
    if any(word in q for word in ["regulation", "label", "packaging", "compliance", "metrc"]):
        return "compliance"
    return "buyer"


def answer_buyer_question(question: str, state: str = "MA", program: str = "medical") -> str:
    client = get_llm_client()
    if not client.enabled:
        return "Doobie AI is currently unavailable."

    module = detect_module(question)
    model = get_chat_model()

    payload = {
        "question": question,
        "state": state,
        "program": program,
        "module": module,
        "model": model,
        "system_prompt": SYSTEM_PROMPT.strip(),
    }

    response = client.copilot(
        question=question,
        data=payload,
        persona="buyer_assistant",
    )
    if str(response.get("mode", "")).lower() == "fallback":
        return "Doobie AI is currently unavailable."

    return str(response.get("answer") or "Doobie AI is currently unavailable.")
