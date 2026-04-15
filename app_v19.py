import streamlit as st
from ui_branding import BACKGROUND_URL, brand_header_html


def _hybrid_theme() -> str:
    return f"""
    <style>
    .stApp {{
        background:
            linear-gradient(rgba(18, 16, 14, 0.78), rgba(10, 10, 10, 0.88)),
            url('{BACKGROUND_URL}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    [data-testid="stHeader"] {{
        background: rgba(0,0,0,0) !important;
    }}

    .block-container {{
        max-width: 1450px;
        padding-top: 1rem;
        padding-bottom: 1.5rem;
    }}

    .v19-shell {{
        display: flex;
        justify-content: space-between;
        align-items: stretch;
        gap: 1rem;
        margin-bottom: 1rem;
    }}

    .v19-hero {{
        flex: 1;
        border-radius: 22px;
        padding: 1.1rem 1.25rem;
        background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04));
        border: 1px solid rgba(255,255,255,0.10);
        backdrop-filter: blur(18px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.30);
    }}

    .v19-kicker {{
        color: #ff9a3c;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.75rem;
        font-weight: 800;
        margin-bottom: 0.35rem;
    }}

    .v19-title {{
        color: #ffffff;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.04;
        margin-bottom: 0.35rem;
    }}

    .v19-sub {{
        color: rgba(255,255,255,0.74);
        font-size: 0.95rem;
    }}

    .v19-nav {{
        width: 360px;
        border-radius: 22px;
        padding: 0.95rem 1rem;
        background: linear-gradient(135deg, rgba(255,154,60,0.18), rgba(255,255,255,0.06));
        border: 1px solid rgba(255,154,60,0.28);
        backdrop-filter: blur(18px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.30);
    }}

    .v19-label {{
        color: rgba(255,255,255,0.72);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        margin-bottom: 0.25rem;
        font-weight: 800;
    }}

    div[data-baseweb="select"] > div,
    div[data-baseweb="select"] input,
    .stSelectbox label,
    .stTextInput label,
    .stMultiSelect label {{
        color: white !important;
    }}

    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    .stTextInput > div > div > input {{
        background: rgba(16,16,16,0.72) !important;
        border: 1px solid rgba(255,154,60,0.22) !important;
        border-radius: 12px !important;
        color: white !important;
    }}

    div[data-testid="stMetric"] {{
        background: rgba(14,14,14,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 0.8rem 0.95rem;
        backdrop-filter: blur(14px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.24);
    }}

    .stTabs [data-baseweb="tab"] {{
        border-radius: 12px 12px 0 0;
        background: rgba(255,255,255,0.05);
        color: rgba(255,255,255,0.8);
    }}

    .stTabs [aria-selected="true"] {{
        background: rgba(255,154,60,0.18) !important;
        color: white !important;
    }}
    </style>
    """


st.markdown(_hybrid_theme(), unsafe_allow_html=True)
st.markdown(brand_header_html(), unsafe_allow_html=True)

_top = st.container()
with _top:
    st.markdown('<div class="v19-shell">', unsafe_allow_html=True)
    st.markdown(
        '''
        <div class="v19-hero">
          <div class="v19-kicker">DoobieLogic Hybrid v19</div>
          <div class="v19-title">Original Engine, Smarter Shell</div>
          <div class="v19-sub">Preserves the original buyer logic, upload intelligence, and operational workflows while adding a cleaner executive-facing control surface.</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="v19-nav">', unsafe_allow_html=True)
    st.markdown('<div class="v19-label">Workspace</div>', unsafe_allow_html=True)
    _workspace_placeholder = st.empty()
    st.markdown('<div class="v19-label" style="margin-top:0.75rem;">Module</div>', unsafe_allow_html=True)
    _section_placeholder = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


_original_radio = st.radio
_original_sidebar_radio = st.sidebar.radio
_original_file_uploader = st.file_uploader
_original_sidebar_file_uploader = st.sidebar.file_uploader


def _should_expand_types(label: str, provided_types):
    label_l = str(label).lower()
    known = [
        "inventory file",
        "product sales report",
        "optional extra sales detail",
        "quarantine list",
        "upload csv run log",
        "sales report",
        "upload sales report",
        "upload extraction runs file",
    ]
    if any(k in label_l for k in known):
        return True
    if provided_types is None:
        return False
    types_l = [str(t).lower() for t in provided_types]
    return types_l == ["csv"] or types_l == ["xlsx", "xls"]


def _expand_types(types):
    if types is None:
        return ["csv", "xlsx", "xls", "pdf"]
    merged = []
    for t in list(types) + ["csv", "xlsx", "xls"]:
        if t not in merged:
            merged.append(t)
    return merged


def _radio_router(label, options, index=0, horizontal=False, **kwargs):
    if label == "Workspace":
        default_idx = int(st.session_state.get("v19_workspace_idx", index))
        default_idx = min(max(default_idx, 0), len(options) - 1)
        value = _workspace_placeholder.selectbox(
            "",
            options,
            index=default_idx,
            key="v19_workspace_select",
            label_visibility="collapsed",
        )
        st.session_state["v19_workspace_idx"] = list(options).index(value)
        return value
    if label == "App Section":
        default_idx = int(st.session_state.get("v19_section_idx", index))
        default_idx = min(max(default_idx, 0), len(options) - 1)
        value = _section_placeholder.selectbox(
            "",
            options,
            index=default_idx,
            key="v19_section_select",
            label_visibility="collapsed",
        )
        st.session_state["v19_section_idx"] = list(options).index(value)
        return value
    return _original_radio(label, options, index=index, horizontal=horizontal, **kwargs)


def _sidebar_radio_router(label, options, index=0, **kwargs):
    if label == "App Section":
        default_idx = int(st.session_state.get("v19_section_idx", index))
        default_idx = min(max(default_idx, 0), len(options) - 1)
        value = _section_placeholder.selectbox(
            "",
            options,
            index=default_idx,
            key="v19_section_select_sidebar",
            label_visibility="collapsed",
        )
        st.session_state["v19_section_idx"] = list(options).index(value)
        return value
    return _original_sidebar_radio(label, options, index=index, **kwargs)


def _file_uploader_router(label, type=None, **kwargs):
    actual_types = _expand_types(type) if _should_expand_types(label, type) else type
    return _original_file_uploader(label, type=actual_types, **kwargs)


def _sidebar_file_uploader_router(label, type=None, **kwargs):
    actual_types = _expand_types(type) if _should_expand_types(label, type) else type
    return _original_sidebar_file_uploader(label, type=actual_types, **kwargs)


st.radio = _radio_router
st.sidebar.radio = _sidebar_radio_router
st.file_uploader = _file_uploader_router
st.sidebar.file_uploader = _sidebar_file_uploader_router

import app  # noqa: E402,F401

st.markdown(_hybrid_theme(), unsafe_allow_html=True)
