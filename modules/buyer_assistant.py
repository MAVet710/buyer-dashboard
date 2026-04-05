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
    model = get_chat_model()

    module = detect_module(question)
    from ai.retriever import retrieve_context

    retrieved = retrieve_context(
        question=question,
        module=module,
        state=state,
        program=program,
        n_results=6,
    )

    docs = retrieved.get("documents", [[]])[0]
    metas = retrieved.get("metadatas", [[]])[0]

    context_blocks = []
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        source = meta.get("source", "unknown_source")
        topic = meta.get("topic", "general")
        context_blocks.append(f"[Source {i} | {source} | {topic}]\n{doc}")

    context_text = "\n\n".join(context_blocks) if context_blocks else "No relevant context found."

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Use the context below to answer the buyer question.

Context:
{context_text}

Question:
{question}
""",
            },
        ],
    )

    return response.choices[0].message.content or ""
