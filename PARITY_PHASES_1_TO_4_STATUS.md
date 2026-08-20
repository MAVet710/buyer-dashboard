# Parity Phases 1–4 Status

## Requested priority order
1. Buyer Dashboard full parity
2. Extraction Command Center full parity
3. Slow Movers + Delivery Impact full parity
4. PO Builder full parity

## Current status
These four phases are **not fully complete yet**. The modular app has the architecture and Doobie integration, but the original `app.py` still contains the most complete operational logic.

## What is complete already
- Modular shell app existed as `app_v5.py` (removed as dead code — the modular-shell approach described here was not carried forward; `app.py` retains the operational logic directly)
- Doobie-only intelligence routes exist
- Command Center, Extraction Analytics, Smart PO, and Learning views exist
- Migration parity tracker exists

## What must be completed before replacement of `app.py`
### Phase 1 — Buyer Dashboard full parity
- Inventory Dashboard controls
- target DOH, velocity adjustment, and sales period controls
- category DOS quick view
- forecast table
- product-level rows toggle
- SKU Inventory Buyer View tabs
- export table logic
- Doobie replacement for legacy AI inventory check

### Phase 2 — Extraction Command Center full parity
- executive overview
- run analytics
- toll processing
- compliance / METRC
- data input tab
- manual run entry
- manual toll job entry
- Doobie replacement for legacy AI ops brief

### Phase 3 — Slow Movers + Delivery Impact full parity
- full filter bar and KPI strip
- delivery manifest parsing + WoW analysis + charts + lift tables
- exports and debug tools

### Phase 4 — PO Builder full parity
- reorder cross-reference from Inventory Dashboard
- add-all reorder ASAP lines
- manual PO line entry
- inventory cross-check
- totals / taxes / PDF
- smart PO merged in without removing original capabilities

## Safe implementation rule
This rule is now moot: `app_v5.py` was removed as dead code, and the modular-shell migration path it described was not carried forward. `app.py` remains the live implementation; any future re-attempt at a modular shell should not be promoted to `app.py` until it reaches parity with all four phases above, verified against the original workflow.
