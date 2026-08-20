"""Shared application navigation components."""

from modules.navigation.workspace_shell import (
    normalize_workspace_state,
    render_workspace_selector,
)
from modules.navigation.product_360_master import install_product_360_master_patch


# Product Master is an additive read-side enrichment. Install it at the package
# boundary so direct Product 360 imports and the workspace shell share one
# canonical search/snapshot implementation while retaining legacy fallbacks.
install_product_360_master_patch()


__all__ = ["normalize_workspace_state", "render_workspace_selector"]
