"""Install the Buyer Dash cohesion layer before the legacy composition root loads.

The durable services remain authoritative. This runtime only changes presentation:
- Inventory exposes a first-class Products / Product Master board.
- Extraction uses the durable run board + Run 360 instead of the legacy long editor.
- Existing pages remain available as compatibility code, but are no longer the
  default operator path.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Mapping, MutableMapping, Sequence

from modules.product_master.ui import PRODUCT_MASTER_SURFACE


def product_master_secondary_choices(
    choices: Sequence[tuple[str, str, str]],
    *,
    category: str,
    operation_mode: str,
) -> list[tuple[str, str, str]]:
    """Insert Products beside Inventory without exposing implementation architecture."""
    result = list(choices)
    if category != "Inventory" or operation_mode == "Production Ops":
        return result
    if any(kind == "virtual" and value == PRODUCT_MASTER_SURFACE for _, kind, value in result):
        return result
    product_choice = ("Products", "virtual", PRODUCT_MASTER_SURFACE)
    insert_at = 1 if result else 0
    result.insert(insert_at, product_choice)
    return result


def prepare_ux_cohesion_runtime(st: Any) -> None:
    """Patch presentation surfaces once, before ``app.py`` imports references."""
    if getattr(st, "_buyer_dash_ux_cohesion_installed", False):
        return
    st._buyer_dash_ux_cohesion_installed = True

    from modules.navigation import workspace_shell as shell
    from modules.navigation.operation_context_bar import PRODUCTION_OPERATION
    from services.workspace_navigation import EXTRACTION_WORKSPACE

    # Make Product Master a normal Inventory destination on desktop and mobile.
    original_secondary = shell._secondary_choices
    if not getattr(original_secondary, "_ux_cohesion_wrapper", False):
        @wraps(original_secondary)
        def cohesive_secondary(
            category: str,
            groups: Mapping[str, Sequence[str]],
            section_groups: Mapping[str, Sequence[str]],
            *,
            operation_mode: str = "Retail Ops",
        ) -> list[tuple[str, str, str]]:
            choices = original_secondary(
                category,
                groups,
                section_groups,
                operation_mode=operation_mode,
            )
            return product_master_secondary_choices(
                choices,
                category=category,
                operation_mode=operation_mode,
            )

        cohesive_secondary._ux_cohesion_wrapper = True
        shell._secondary_choices = cohesive_secondary

    # Inventory command center remains the normal Inventory overview. Selecting
    # Products swaps only the content surface, then the existing shell st.stop()
    # behavior prevents the old app page from rendering underneath it.
    try:
        import modules.inventory_command_center as inventory_center

        original_inventory = inventory_center.render_inventory_command_center
        if not getattr(original_inventory, "_ux_cohesion_wrapper", False):
            @wraps(original_inventory)
            def cohesive_inventory(
                state: MutableMapping[str, Any],
                *args: Any,
                operation_mode: str = "Retail Ops",
                **kwargs: Any,
            ) -> Any:
                if (
                    operation_mode != PRODUCTION_OPERATION
                    and str(state.get("flat_virtual_surface") or "") == PRODUCT_MASTER_SURFACE
                ):
                    from modules.product_master.ui import render_product_master_workspace

                    return render_product_master_workspace(state)
                return original_inventory(
                    state,
                    *args,
                    operation_mode=operation_mode,
                    **kwargs,
                )

            cohesive_inventory._ux_cohesion_wrapper = True
            inventory_center.render_inventory_command_center = cohesive_inventory
    except Exception:
        # Compatibility-safe: if the optional command center cannot import, the
        # existing shell remains untouched instead of breaking app startup.
        pass

    # The legacy extraction editor is still present for compatibility, but the
    # default Extraction workspace now terminates at the durable board + Run 360.
    original_selector = shell.render_workspace_selector
    if not getattr(original_selector, "_ux_cohesion_wrapper", False):
        @wraps(original_selector)
        def cohesive_selector(*args: Any, **kwargs: Any) -> tuple[str, str]:
            group, workspace = original_selector(*args, **kwargs)
            if workspace == EXTRACTION_WORKSPACE:
                from views.extraction_view import render_extraction_view

                render_extraction_view()
                st.stop()
            return group, workspace

        cohesive_selector._ux_cohesion_wrapper = True
        shell.render_workspace_selector = cohesive_selector
