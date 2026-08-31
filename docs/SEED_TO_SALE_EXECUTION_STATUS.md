# Seed-to-Sale Execution Status

Implementation branch: `feat/seed-to-sale-material-backbone`

## Phase 1 — Material backbone / Harvest -> Inventory

- [x] Canonical material transformation models
- [x] Alembic migration 0059
- [x] Harvest output preview
- [x] Harvest output canonical lot creation
- [x] Harvest output append-only inventory transactions
- [x] Harvest -> plant ancestry edges
- [x] Wet/dry measurement-basis over-allocation protection
- [x] Regression coverage for harvest child inventory and plant trace
- [ ] Harvest 360 operator UI for output allocation
- [ ] Harvest allocation stale-preview token before commit

## Phase 2 — Production actual material consumption

- [x] Governed `consume_materials` Run 360 action
- [x] Existing Run 360 preview fingerprint / stale-state protection
- [x] Physical `production_consume` ledger decrement
- [x] Reservation reduction / consumed state
- [x] Actual-vs-BOM variance
- [x] Production source -> output genealogy
- [x] Completion blocker when required actual consumption is missing
- [x] QA release blocker when required actual consumption is missing
- [x] Regression coverage for 100 g -> consume 10 g -> 90 g source balance
- [ ] Production Run 360 Actual Materials operator UI

## Phase 3 — Unified lineage

- [x] Recursive canonical lot graph
- [x] Harvest / source plants in graph
- [x] Production order / actual source lots / outputs in graph
- [x] Existing Package Studio durable input/output graph folded into query
- [x] Tenant/facility-scoped lineage lookup
- [ ] Package 360 UI consumes the recursive graph
- [ ] Recall blast-radius query

## Later approved phases

- [ ] Extraction intermediates / preflight / closeout on canonical graph
- [ ] Cultivation batch/nursery UX
- [ ] Cross-license / cross-facility transfer edges
- [ ] Recall 360
- [ ] Doobie Agent lineage and recall tools
