import os
from datetime import datetime

import streamlit as st

from ai.compliance_store import SQLiteComplianceStore
from ai.retriever import retrieve_context
from ai_providers import build_provider


COMPLIANCE_REQUIRED_FIELDS = [
    "State",
    "Scope (medical/adult-use)",
    "Source citation",
    "Source URL",
    "Last updated date",
    "Confidence / review status",
]

SYSTEM_PROMPT = """
You are a cannabis intelligence assistant.
Use supplied retrieval context and never invent regulations.
If context is weak, say that clearly and ask for more sources.
""".strip()


def _format_context(results: dict) -> str:
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return "No relevant context found in vector database."

    chunks = []
    for idx, (doc, meta) in enumerate(zip(docs, metas), start=1):
        source = meta.get("source", "unknown")
        topic = meta.get("topic", "general")
        state = meta.get("state", "unknown")
        program = meta.get("program", "unknown")
        chunks.append(
            f"[Chunk {idx}] source={source}, topic={topic}, state={state}, program={program}\n{doc}"
        )

    return "\n\n".join(chunks)


def _render_compliance_answer(store: SQLiteComplianceStore, state: str, scope: str, topic: str) -> None:
    rows = store.search(state=state, scope=scope, topic=topic)

    if not rows:
        st.error(
            "No structured compliance records found for this query. Add a reviewed source row to the compliance database first."
        )
        return

    st.success(f"Found {len(rows)} structured compliance source(s).")
    for row in rows:
        st.markdown(f"### {row.topic}")
        st.write(row.answer)
        st.markdown(f"- **State:** {row.state}")
        st.markdown(f"- **Scope:** {row.scope}")
        st.markdown(f"- **Source citation:** {row.source_citation}")
        st.markdown(f"- **Source URL:** {row.source_url}")
        st.markdown(f"- **Last updated date:** {row.last_updated_date}")
        st.markdown(f"- **Confidence / review status:** {row.review_status}")
        st.divider()


def _run_retrieval_assistant(question: str, module: str, state: str, program: str) -> tuple[str, str]:
    results = retrieve_context(
        question=question,
        module=module,
        state=state,
        program=program,
        n_results=6,
    )
    context = _format_context(results)

    preferred = os.getenv("AI_PROVIDER", "ollama")
    provider = build_provider(preferred=preferred, openai_api_key=os.getenv("OPENAI_API_KEY"))
    if provider is None:
        return (
            "No AI provider available. Configure OLLAMA or OPENAI_API_KEY.",
            context,
        )

    response = provider.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Context:\n{context}\n\nQuestion:\n{question}",
        max_tokens=700,
    )
    footer = f"\n\n_Provider: {response.provider} | Model: {response.model}_"
    return response.text + footer, context


def main() -> None:
    st.set_page_config(page_title="Cannabis AI", page_icon="🌿", layout="wide")
    st.title("🌿 Cannabis AI Workspace")
    st.caption("Separate AI app for compliance, retail buying, and extraction support.")

    with st.sidebar:
        st.header("Context")
        state = st.selectbox("State", ["CA", "CO", "MA", "MI", "NY", "NV", "OR", "WA"], index=2)
        program = st.selectbox("Program", ["medical", "adult-use"], index=0)
        st.markdown("---")
        st.subheader("Compliance guardrails")
        for field in COMPLIANCE_REQUIRED_FIELDS:
            st.markdown(f"- {field}")

    tab_compliance, tab_buyer, tab_extraction = st.tabs(
        ["🧾 Compliance AI", "🛒 Buyer AI", "🧪 Extraction AI"]
    )

    with tab_compliance:
        st.subheader("Structured compliance answer")
        topic = st.text_input("Compliance topic", placeholder="e.g., packaging label requirements")
        if st.button("Answer compliance question", type="primary"):
            if not topic.strip():
                st.warning("Enter a compliance topic first.")
            else:
                store = SQLiteComplianceStore(os.getenv("COMPLIANCE_DB_PATH", "./data/compliance/compliance.db"))
                try:
                    _render_compliance_answer(store, state=state, scope=program, topic=topic)
                finally:
                    store.close()

    with tab_buyer:
        st.subheader("Buyer intelligence Q&A")
        buyer_q = st.text_area(
            "Ask buyer AI",
            placeholder="Where am I overstocked in vapes and what reorder changes should I make?",
            height=120,
        )
        if st.button("Run buyer AI"):
            if not buyer_q.strip():
                st.warning("Enter a question first.")
            else:
                with st.spinner("Running retrieval and AI reasoning..."):
                    answer, context = _run_retrieval_assistant(
                        question=buyer_q,
                        module="buyer",
                        state=state,
                        program=program,
                    )
                st.markdown(answer)
                with st.expander("Retrieved context"):
                    st.code(context)

    with tab_extraction:
        st.subheader("Extraction operations Q&A")
        extraction_q = st.text_area(
            "Ask extraction AI",
            placeholder="How can we improve rosin yield without compromising terpene retention?",
            height=120,
        )
        if st.button("Run extraction AI"):
            if not extraction_q.strip():
                st.warning("Enter a question first.")
            else:
                with st.spinner("Running retrieval and AI reasoning..."):
                    answer, context = _run_retrieval_assistant(
                        question=extraction_q,
                        module="extraction",
                        state=state,
                        program=program,
                    )
                st.markdown(answer)
                with st.expander("Retrieved context"):
                    st.code(context)

    st.markdown("---")
    st.caption(f"Session started: {datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
