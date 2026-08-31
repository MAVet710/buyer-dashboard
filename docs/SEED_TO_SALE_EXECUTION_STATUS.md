# Seed-to-Sale Execution Status

Implementation branch: `feat/seed-to-sale-material-backbone`

This document tracks the scope of the first material-backbone pull request. The PR must remain unmerged until its current head passes the full CI, React/FastAPI, browser, container/security, release-preview, and secret-history gates.

## Phase 1 — Material backbone / Harvest -> Inventory

- [x] Canonical material transformation models
- [x] Alembic migration 0059
- [x] Harvest output preview
- [x] Harvest output canonical lot creation
- [x] Harvest output append-only inventory transactions
- [x] Harvest -> plant ancestry edges
- [x] Wet/dry measurement-basis over-allocation protection
- [x] Harvest closeout blocks completion while measured material remains undisposed
- [x] Harvest allocation exact-preview fingerprint and stale-preview rejection
- [x] Harvest 360 operator UI for output allocation
- [x] Regression coverage for harvest child inventory, closeout, stale previews, and plant trace

## Phase 2 — Production actual material consumption

- [x] Governed `consume_materials` Run 360 action
- [x] Existing Run 360 preview fingerprint / stale-state protection
- [x] Physical `production_consume` ledger decrement
- [x] Reservation reduction / consumed state
- [x] Actual-vs-BOM variance
- [x] Production source -> output genealogy
- [x] Completion blocker when required actual consumption is missing
- [x] QA release blocker when required actual consumption is missing
- [x] Production Run 360 Actual Materials operator UI
- [x] Regression coverage for 100 g -> consume 10 g -> 90 g source balance

## Phase 3 — Unified lineage

- [x] Recursive canonical lot graph
- [x] Harvest / source plants in graph
- [x] Production order / actual source lots / outputs in graph
- [x] Existing Package Studio durable input/output graph folded into query
- [x] Tenant/facility-scoped lineage lookup
- [x] Package 360 consumes and displays the recursive graph
- [x] Continuous regression journey from plant -> harvest -> bulk lot -> production consumption -> finished lot -> completed run -> plant ancestry
- [x] Static operator-surface contracts for Harvest 360, Run 360, and Package 360

## Next approved phases — intentionally outside this PR

- [ ] Extraction intermediates / preflight / closeout on canonical graph
- [ ] Cultivation batch/nursery UX expansion
- [ ] Cross-license / cross-facility transfer edges
- [ ] Recall 360 / recall blast-radius query
- [ ] Doobie Agent lineage and recall tools
