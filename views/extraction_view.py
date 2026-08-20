"""Canonical Extraction view.

The durable ERP workspace is primary. The optional ``run_df`` argument remains
for compatibility with older callers and powers a small AI fallback only when a
database/tenant context is unavailable.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from doobie_panels import run_extraction_doobie
from modules.extraction.elite_runtime import install_extraction_performance_ui
from modules.extraction.ui import render_extraction_workspace


def render_extraction_view(run_df: pd.DataFrame | None = None) -> None:
    install_extraction_performance_ui()
    render_extraction_workspace(st.session_state)

    organization_id = str(st.session_state.get("active_organization_id") or "").strip()
    facility_id = str(st.session_state.get("active_facility_id") or "").strip()
    if organization_id and facility_id:
        return

    if isinstance(run_df, pd.DataFrame) and not run_df.empty:
        st.divider()
        st.caption("Legacy read-only extraction brief")
        if st.button("Generate AI Extraction Brief", key="extraction_ai_brief_btn"):
            run_extraction_doobie(run_df)
