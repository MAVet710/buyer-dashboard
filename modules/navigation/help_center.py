"""Compact in-app help and downloadable training guide."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


def render_help_center() -> None:
    with st.sidebar.expander("Help & Training", expanded=False):
        st.markdown("**Fast path**")
        st.caption("1. Confirm company/facility  ·  2. Open Home  ·  3. Choose a task")
        st.markdown("**Data questions**")
        st.caption("Use Data Import Center to upload, inspect, and publish shared sources.")
        st.markdown("**Mobile inventory counts**")
        st.caption("Inventory Counts supports cameras, Bluetooth/USB scanners, and typed codes.")
        guide_path = Path(__file__).resolve().parents[2] / "docs" / "USER_GUIDE.md"
        if guide_path.exists():
            st.download_button(
                "Download full user guide",
                data=guide_path.read_bytes(),
                file_name="DoobieLogic_Buyer_Dash_User_Guide.md",
                mime="text/markdown",
                width="stretch",
            )
