"""Responsive design utilities for mobile-first layouts."""

from __future__ import annotations

import streamlit as st


def get_viewport_width() -> int:
    """
    Detect current viewport width in pixels.
    Default to 1440px (desktop) when viewport detection is unavailable.
    """
    # In Streamlit, we can detect viewport via query params or session state
    if "viewport_width" in st.query_params:
        try:
            return int(st.query_params["viewport_width"])
        except (ValueError, TypeError):
            pass

    # Default based on typical Streamlit UI
    # Streamlit default is ~800px for desktop, can be wider
    return st.session_state.get("viewport_width", 1440)


def is_mobile() -> bool:
    """Check if current viewport is mobile (< 768px)."""
    return get_viewport_width() < 768


def is_tablet() -> bool:
    """Check if current viewport is tablet (768px-1024px)."""
    width = get_viewport_width()
    return 768 <= width < 1024


def is_desktop() -> bool:
    """Check if current viewport is desktop (>= 1024px)."""
    return get_viewport_width() >= 1024


def responsive_columns(count: int = 4) -> list:
    """
    Get responsive column layout based on viewport width.

    Args:
        count: Desired number of columns on desktop (1-5)

    Returns:
        List of columns from st.columns()
    """
    width = get_viewport_width()

    if width < 430:
        # Small mobile: always 1 column
        return st.columns(1)
    elif width < 768:
        # Large mobile: 2 columns
        responsive_count = min(2, count)
    elif width < 1024:
        # Tablet: 3 columns or less
        responsive_count = min(3, count)
    else:
        # Desktop: use requested count
        responsive_count = count

    return st.columns(responsive_count)


def responsive_metric_row(metrics: list[tuple[str, str, str | None]] = None, count: int = 4) -> None:
    """
    Render a responsive row of metrics that adapts to viewport.

    Args:
        metrics: List of (label, value, delta) tuples
        count: Desired columns on desktop
    """
    if not metrics:
        return

    cols = responsive_columns(count)

    for idx, (label, value, delta) in enumerate(metrics):
        with cols[idx % len(cols)]:
            st.metric(label, value, delta=delta if delta else None)


def responsive_layout_mode() -> str:
    """
    Get current responsive layout mode.

    Returns:
        "mobile" | "tablet" | "desktop"
    """
    if is_mobile():
        return "mobile"
    elif is_tablet():
        return "tablet"
    else:
        return "desktop"


def should_stack_vertically() -> bool:
    """Check if layouts should stack vertically (mobile/tablet)."""
    return get_viewport_width() < 1024


def get_dataframe_height() -> int | None:
    """Get responsive dataframe height for scrolling on small screens."""
    width = get_viewport_width()

    if width < 430:
        return 300  # Small mobile: short scroll
    elif width < 768:
        return 400  # Large mobile: medium scroll
    elif width < 1024:
        return 500  # Tablet: taller
    else:
        return None  # Desktop: auto-height
