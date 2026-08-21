"""Runtime safety guard for Streamlit dataframe row selections in Inventory.

Streamlit can retain a selected positional row across a rerun while filters or
hydrated tenant data change the dataframe length.  The Inventory command center
historically passed those positions directly to ``DataFrame.iloc``.  This guard
records the row count of the rendered Inventory dataframe and drops stale or
invalid positions before they can reach Pandas.
"""
from __future__ import annotations

from typing import Any


def install_inventory_selection_guard() -> None:
    from modules import inventory_command_center as inventory

    if getattr(inventory._selected_rows, "_inventory_selection_safe", False):
        return

    original_selected_rows = inventory._selected_rows
    real_streamlit = inventory.st

    class InventoryStreamlitProxy:
        def dataframe(self, data: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                inventory._inventory_rendered_row_count = max(int(len(data)), 0)
            except Exception:
                inventory._inventory_rendered_row_count = None
            return real_streamlit.dataframe(data, *args, **kwargs)

        def __getattr__(self, name: str) -> Any:
            return getattr(real_streamlit, name)

    def safe_selected_rows(event: Any) -> list[int]:
        try:
            raw = original_selected_rows(event)
        except Exception:
            raw = []
        limit = getattr(inventory, "_inventory_rendered_row_count", None)
        positions: list[int] = []
        seen: set[int] = set()
        for value in raw or []:
            try:
                position = int(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if position < 0:
                continue
            if limit is not None and position >= int(limit):
                continue
            if position in seen:
                continue
            seen.add(position)
            positions.append(position)
        return positions

    safe_selected_rows._inventory_selection_safe = True
    inventory._selected_rows = safe_selected_rows
    inventory.st = InventoryStreamlitProxy()
