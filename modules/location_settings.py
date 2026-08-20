"""Facility-scoped settings surfaced under Data & Settings → Location."""

from __future__ import annotations

from collections.abc import MutableMapping

import streamlit as st

from modules.inventory_receiving import (
    load_location_receive_settings,
    save_location_receive_settings,
)


def render_location_settings(state: MutableMapping[str, object]) -> None:
    organization = str(state.get("active_organization_name") or "Organization")
    facility = str(state.get("active_facility_name") or "Facility")
    settings = load_location_receive_settings(state)

    st.caption("DATA & SETTINGS / LOCATION")
    st.markdown("## Location settings")
    st.caption(f"{organization} · {facility}")
    st.markdown(
        "These settings apply only to the selected facility and are stored durably with that facility's Buyer Dash data."
    )

    with st.container(border=True):
        st.markdown("#### Inventory receiving")
        auto_map = st.toggle(
            "Auto-map products during receive",
            value=bool(settings.get("auto_map_products_during_receive", False)),
            key="location_auto_map_receive",
            help=(
                "When enabled, Buyer Dash remembers prior approved incoming-item → Catalog product mappings "
                "for this facility and preselects them the next time the same incoming product is received. "
                "The receiver can always choose a different Catalog product."
            ),
        )
        default_room = st.text_input(
            "Default receiving room",
            value=str(settings.get("default_receiving_room") or "Receiving"),
            key="location_default_receiving_room",
            placeholder="Receiving",
        )
        st.caption(
            "Auto-map never guesses a new catalog relationship. It reuses only mappings that were previously reviewed and posted at this facility."
        )
        if st.button("Save location settings", type="primary", width="stretch", key="save_location_settings"):
            try:
                save_location_receive_settings(
                    state,
                    auto_map_products_during_receive=bool(auto_map),
                    default_receiving_room=str(default_room),
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success("Location settings saved.")
