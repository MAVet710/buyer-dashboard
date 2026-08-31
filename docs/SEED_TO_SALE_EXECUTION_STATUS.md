# Seed-to-Sale Execution Status

Current status: Phases 1–7 are merged into `main`. The currently approved seed-to-sale hardening sequence is complete.

This document tracks the durable seed-to-sale material backbone and the operator-hardening phases built on top of it. Implementation changes remain isolated in pull requests until their focused regressions and repository CI gates pass.

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

## Phase 3 — Unified lineage and Extraction material backbone

- [x] Recursive canonical lot graph
- [x] Harvest / source plants in graph
- [x] Production order / actual source lots / outputs in graph
- [x] Existing Package Studio durable input/output graph folded into query
- [x] Tenant/facility-scoped lineage lookup
- [x] Package 360 consumes and displays the recursive graph
- [x] Continuous regression journey from plant -> harvest -> bulk lot -> production consumption -> finished lot -> completed run -> plant ancestry
- [x] Static operator-surface contracts for Harvest 360, Run 360, and Package 360
- [x] Extraction reservations share canonical inventory availability
- [x] Extraction actual consumption, WIP handoff, final-output quarantine/QA and mass-balance closeout
- [x] Extraction source/output edges participate in recursive genealogy

## Phase 4 — Cultivation batch / nursery operations

- [x] Durable cultivation plant groups
- [x] Mother/source genealogy
- [x] Atomic clone, seed and nursery batch creation
- [x] Capacity-aware batch phase / room actions
- [x] Plant 360 lineage
- [x] Batch-first operator UX with single-plant exception entry retained

## Phase 5 — Cross-license / cross-facility transfers

- [x] Two-sided source dispatch / destination receipt lifecycle
- [x] Separate physical inventory ledgers by license
- [x] State-system confirmation gates around transfer mutations
- [x] Manifest and package identity preserved on durable transfer lines
- [x] QA / COA evidence inheritance
- [x] Cross-facility genealogy federates only through durable transfer evidence
- [x] Unauthorized facility inventory remains redacted while transfer/package/license references stay visible

## Phase 6 — Recall 360

- [x] Deterministic downstream recall blast-radius query over canonical genealogy
- [x] Source package included while upstream ancestors are excluded from downstream recall scope
- [x] Branching descendants and multi-hop transformations included
- [x] Cycle-safe traversal and duplicate suppression
- [x] Adaptive graph expansion prevents fixed-depth silent under-reporting
- [x] Hard traversal ceiling returns an explicit incomplete-scope guard instead of a false-clear result
- [x] Cancelled transfers are excluded from live recall exposure
- [x] Cross-license downstream packages included only when the user may inspect that facility
- [x] Protected / in-transit transfer exposure remains visible as follow-up work instead of disappearing
- [x] Current on-hand exposure summarized by unit without mixing incompatible units
- [x] Recall 360 surfaced inside Package 360
- [x] Recall analysis explicitly read-only; no silent inventory holds, Metrc mutation or regulator notification
- [x] Regression coverage for downstream-only scope, depth expansion, cycles, cancelled transfers, cross-license authorization and tenant isolation

## Phase 7 — Doobie Agent lineage and recall tools

- [x] First-class read-only `package_lineage` tool over canonical genealogy
- [x] First-class read-only `recall_blast_radius` tool over Recall 360
- [x] Trusted server-side organization, facility, user, role and database scope; models cannot supply tenant scope arguments
- [x] Package/tag/barcode/lot resolution restricted to authorized facilities
- [x] Cross-tenant and unauthorized-facility package existence does not leak through identifier resolution
- [x] Ambiguous package/lot identifiers fail closed instead of selecting a candidate
- [x] Cross-license lineage/recall federation reuses the same durable transfer and facility-redaction rules as Package 360 / Recall 360
- [x] Explicit identifier-bound lineage and recall questions execute deterministically with zero model-provider dependency
- [x] Live traceability queries bypass the short deterministic analytics cache
- [x] Factual Compliance Agent traceability may use deterministic package facts without weakening authoritative-source requirements for legal/regulatory conclusions
- [x] Mixed legal/compliance traceability questions combine canonical package facts with authoritative retrieved evidence instead of short-circuiting either evidence class
- [x] Explicit traceability-service failures fail closed and do not fall through to model memory
- [x] Agent traceability remains analysis-only: no inventory hold, Metrc mutation, regulator notification or other compliance mutation
- [x] Regression coverage for schema isolation, facility redaction, admin federation, cross-tenant non-disclosure, ambiguity, deterministic execution, compliance grounding, mixed evidence and fail-closed tool errors

## Approved execution sequence

- [x] The currently approved seed-to-sale hardening sequence is complete. No additional phase is queued in this document.
