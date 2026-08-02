# Retail UX Notes

These notes capture the useful interaction patterns observed in the Dutchie
inventory and reporting workflow without copying Dutchie branding or visual
assets.

## Patterns worth carrying into DoobieLogic

- Keep a persistent operations context and show only the tools relevant to the
  selected task area.
- Use a clear page title, one-sentence purpose, and a small number of primary
  actions at the top of each workspace.
- Put filters and actions next to the table or form they affect.
- Prefer visible task groups over a long, mixed list of analysis,
  administration, and compliance pages.
- Make exports configurable, but keep the default output operationally useful.
- Preserve product identifiers internally while showing recognizable product
  names in user-facing tables and reports.
- Keep high-frequency workflows linear: choose scope, enter or scan data,
  review exceptions, then export or reconcile.

## Adjustments implemented

- Buyer Operations navigation is grouped into Overview, Inventory, Purchasing,
  Compliance, and Administration areas.
- Only the tools for the selected Retail area are visible, reducing sidebar
  clutter on desktop and mobile.
- MA Flower Equivalency lives under Inventory because it supports package
  configuration and inventory-entry work.
- The calculator uses a responsive input-to-result flow with inline validation,
  a visible breakdown, and a Dutchie-ready copy action.
- Buyer executive report action tables use product-level records and put the
  product name first instead of presenting anonymous quantities.

## Follow-up opportunities

- Add reusable filter/action bars above the largest Retail data tables.
- Add saved table views for common buyer and inventory roles.
- Add a global Retail search across SKU, product, package ID, batch, and vendor.
- Add export presets so users can reuse their preferred column selections.
- Continue replacing long forms with progressive task steps where the workflow
  has a clear sequence.
