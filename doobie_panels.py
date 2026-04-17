import streamlit as st

from doobie_settings import doobie_config_summary
from services.doobie_client import DoobieClient


def _get_client() -> DoobieClient:
    cfg = doobie_config_summary()
    return DoobieClient(base_url=cfg["url"], api_key=cfg["api_key"])


def _normalize_payload(df_like) -> dict:
    if hasattr(df_like, "to_dict"):
        payload = df_like.to_dict(orient="records")
    elif isinstance(df_like, dict):
        payload = df_like
    else:
        payload = {}
    return payload if isinstance(payload, dict) else {"rows": payload}


def _render_doobie_response(response: dict):
    st.markdown("#### ✨ Answer")
    st.success(response.get("answer", "No answer returned."))

    explanation = str(response.get("explanation") or "").strip()
    if explanation:
        with st.expander("Explanation", expanded=False):
            st.write(explanation)

    recommendations = response.get("recommendations", [])
    if isinstance(recommendations, list) and recommendations:
        st.markdown("#### Recommendations")
        for rec in recommendations:
            st.write(f"- {rec}")

    c1, c2 = st.columns([1, 4])
    with c1:
        st.caption(f"Confidence: {response.get('confidence', 'low')}")
    with c2:
        mode = str(response.get("mode", "fallback")).lower()
        if mode == "fallback":
            st.caption("AI unavailable")

    for optional_key in ("risk_flags", "inefficiencies"):
        values = response.get(optional_key, [])
        if isinstance(values, list) and values:
            st.markdown(f"#### {optional_key.replace('_', ' ').title()}")
            for item in values:
                st.write(f"- {item}")


def render_doobie_status():
    cfg = doobie_config_summary()
    if not cfg["configured"]:
        st.info("AI unavailable")
    else:
        st.success(f"DoobieLogic connected → {cfg['url']}")


def _cached_or_call(cache_key: str, call_fn):
    cache = st.session_state.setdefault("_doobie_cache", {})
    if cache_key in cache:
        return cache[cache_key]
    response = call_fn()
    cache[cache_key] = response
    return response


def _run_guarded(call_key: str, spinner_message: str, call_fn):
    if st.session_state.get(call_key):
        st.info("Please wait for the current AI request to finish.")
        return None
    st.session_state[call_key] = True
    try:
        with st.spinner(spinner_message):
            return call_fn()
    finally:
        st.session_state[call_key] = False


def run_buyer_doobie(by_product_df, state: str = "MA"):
    client = _get_client()
    if not client.enabled:
        _render_doobie_response({"mode": "fallback", "answer": "Doobie is currently unavailable."})
        return
    rows = by_product_df.to_dict(orient="records") if hasattr(by_product_df, "to_dict") else []
    payload = {"inventory": rows}
    cache_key = f"buyer_brief::{state}::{hash(str(payload))}"
    response = _run_guarded(
        "doobie_buyer_inflight",
        "Doobie is thinking...",
        lambda: _cached_or_call(cache_key, lambda: client.buyer_brief(payload, state=state)),
    )
    if response:
        _render_doobie_response(response)


def run_inventory_doobie(data_df, state: str = "MA"):
    client = _get_client()
    if not client.enabled:
        _render_doobie_response({"mode": "fallback", "answer": "Doobie is currently unavailable."})
        return
    rows = data_df.to_dict(orient="records") if hasattr(data_df, "to_dict") else []
    payload = {"inventory": rows}
    cache_key = f"inventory_check::{state}::{hash(str(payload))}"
    response = _run_guarded(
        "doobie_inventory_inflight",
        "Doobie is thinking...",
        lambda: _cached_or_call(cache_key, lambda: client.inventory_check(payload, state=state)),
    )
    if response:
        _render_doobie_response(response)


def run_extraction_doobie(run_df, state: str = "MA"):
    client = _get_client()
    if not client.enabled:
        _render_doobie_response({"mode": "fallback", "answer": "Doobie is currently unavailable."})
        return
    rows = run_df.to_dict(orient="records") if hasattr(run_df, "to_dict") else []
    payload = {"runs": rows}
    cache_key = f"extraction_brief::{state}::{hash(str(payload))}"
    response = _run_guarded(
        "doobie_extraction_inflight",
        "Doobie is thinking...",
        lambda: _cached_or_call(cache_key, lambda: client.extraction_brief(payload, state=state)),
    )
    if response:
        _render_doobie_response(response)
