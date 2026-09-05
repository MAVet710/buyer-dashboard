# Vertical Seed-to-Sale Operator Audit

**Audit date:** 2026-08-30  
**Pinned main SHA:** `2e5d496ed307d819416cb4c67bc91e611e7a35f2`  
**Audit mode:** code-backed operator simulation against current `main`, existing browser/API tests, data models, services, permissions, and current UX contracts.

## Objective

Act like an operator inside a vertically integrated cannabis business and determine whether DoobieLogic can carry cannabis through the entire operational chain without broken inventory truth, lost genealogy, duplicate entry, hidden workflow steps, or unsafe license/tenant crossover.

The simulated organization includes cultivation, manufacturing/extraction, wholesale/distribution, and retail capabilities. The audit intentionally follows the same source material into multiple outputs instead of testing isolated pages.

This audit treats a workflow as failed when the UI can appear complete but the underlying inventory, source lineage, compliance state, or facility scope is not durably correct.

## Executive finding

DoobieLogic currently contains several strong operational systems, but it is **not yet a continuous seed-to-sale system**.

The strongest areas are shared inventory availability, Package Studio transformations, Production Run 360 output/QA controls, extraction analytics, wholesale eligibility, warehouse fulfillment, tenant/facility isolation, and guarded traceability architecture.

The weakest area is the connective tissue between those systems.

Two defects are blockers for a true vertical operation:

1. **Completed cultivation harvests do not create canonical downstream inventory lots/packages.** Harvest 360 retires plants, tracks wet/dry/waste/COGS, and completes the harvest record, but does not create the bulk flower, trim, biomass, or fresh-frozen inventory that manufacturing, extraction, Package Studio, wholesale, and reporting need.
2. **Normal Production Run 360 reservations do not become physical source-material consumption.** The current tested flow can reserve a cannabis input, create/release finished output, and still leave the source lot's physical ledger balance unchanged. Package Studio consumes material correctly, but Production Run 360 does not yet share that transformation/lineage contract.

Those two gaps mean a finished item can exist while its upstream cannabis genealogy and mass balance are incomplete.

## Operator scorecard

| Area | Score | Status | Operator finding |
| --- | ---: | --- | --- |
| Discoverability | 5/10 | Needs work | Cultivation is buried under Production Inventory -> Plants instead of presenting itself as a first-class operating workflow. |
| Genetics / nursery / batch intake | 3/10 | Gap | Individual plants work, but creation is one-at-a-time; mother is free text; source package lineage exists in backend but is not exposed in Add Plant. |
| Plant lifecycle | 8/10 | Strong local workflow | Clone/seedling/veg/flower/harvested/destroyed transitions, room movement, events, capacity, harvest estimates and Plant 360 are durable and facility scoped. |
| Harvest execution | 7/10 | Strong local workflow | Harvest assignment, wet/dry/waste, yield and cultivation COGS are useful. |
| Harvest -> inventory handoff | 1/10 | **Critical blocker** | Completing Harvest 360 does not create canonical source lots for flower/trim/fresh frozen/biomass. |
| Production planning / BOM / QA | 8/10 | Strong | FIFO reservation, BOM requirements, standards, machine/crew scheduling, preview-before-mutation, output quarantine/release and cost events are substantial. |
| Production material consumption | 2/10 | **Critical blocker** | Reserved source quantity is not converted into a physical inventory decrement in the normal Run 360 flow. |
| Package transformations | 9/10 | Strongest transformation layer | Package Studio atomically consumes inputs, creates outputs, balances loss and records parent/child lineage. |
| Cross-module genealogy | 3/10 | **Critical** | Package 360 lineage is based primarily on Package Studio relationships; normal production outputs and cultivation harvest ancestry are not a continuous graph. |
| Extraction execution | 6/10 | Partial | Strong run/stage/yield/QA/COGS foundation, but current extraction audit already identifies premature consumption, weak preflight, intermediate WIP, deviations and closeout gaps. |
| Wholesale sellability | 8/10 | Strong | Released inventory, passed COA and positive uncommitted quantity are required; production/wholesale commitments are respected. |
| Warehouse fulfillment | 8/10 | Strong | Existing tests validate FEFO lot recommendation, scan validation, reservation and shipment decrement behavior. |
| Compliance / METRC architecture | 6/10 | Safe but incomplete | Facility/license mapping is fail-closed and cultivation reconciliation is read-only. Plant/harvest regulatory writes are not yet a complete operator workflow. |
| Tenant / facility isolation | 9/10 | Strong | Core services consistently scope organization/facility and tests reject cross-tenant package access. |
| Doobie Agent | 7/10 | Strong reasoning, limited repair actions | Deterministic evals cover cultivation, production, extraction, wholesale and compliance; governed production scheduling exists, but Agent cannot repair missing harvest/consumption lineage. |
| Overall vertical readiness | **5/10** | **Not seed-to-sale ready yet** | Strong operational islands are present; canonical handoffs must be unified before calling the platform vertically complete. |

## Simulated product journeys

### 1. Mother -> clones -> vegetative -> flowering -> harvest

**Result: PARTIAL / usable locally**

Plant phase transitions, room movement, lifecycle history, harvest assignment and harvest economics work. The operator can run individual plants through cultivation.

Friction:
- Cultivation is reached through Production Ops -> Inventory -> Plants.
- Add Plant creates one plant at a time.
- Mother plant tag is free text rather than a selected durable relationship.
- Backend `source_lot_id` support is not exposed in the current Add Plant form.
- There is no obvious nursery action such as "Create 100 clones from Mother X" with tag range/batch creation.

### 2. Harvest -> packaged flower eighths

**Result: BLOCKED end-to-end**

The harvest can be completed, but completion does not create a canonical bulk-flower lot. Therefore the operator must manually introduce source inventory before Package Studio or production can continue.

Once a trustworthy bulk lot exists, Package Studio is well suited to pack-down because it consumes the source and creates output lots with exact source-equivalent balancing and lineage.

### 3. Harvest -> 1 g pre-rolls

**Result: PARTIAL with critical ledger defect**

A production order/BOM can reserve flower, record output, quarantine the output, attach QA evidence and release a finished lot. However, the normal production flow does not currently convert the reserved flower into consumed source inventory. The finished pre-roll lot can therefore exist while the flower source balance remains physically unchanged.

### 4. Harvest -> wholesale bulk flower

**Result: BLOCKED upstream; strong downstream**

Wholesale can correctly restrict inventory to released, passed-COA, uncommitted lots and expose bulk units. The blocker is producing that bulk harvest lot automatically and preserving harvest/plant ancestry.

### 5. Trim/biomass -> extraction input -> crude/distillate

**Result: PARTIAL**

Extraction has source/WIP/bulk-output concepts, stages, run context, analytics and mass-balance intelligence. The repo's extraction parity audit correctly identifies that the operator flow still needs a clearer Plan -> Reserve -> Preflight -> Start -> Consume Actual sequence, better intermediate inventory, explicit deviations/rework, and explicit closeout.

### 6. Fresh frozen -> live resin

**Result: PARTIAL**

The extraction foundation can represent the work, but the cultivation harvest currently cannot automatically split a harvest into dry flower versus fresh-frozen canonical lots. The extraction workflow also needs the preflight/intermediate/closeout improvements above.

### 7. Flower -> solventless / hash -> rosin

**Result: PARTIAL**

The same source-material handoff and extraction intermediate-inventory limitations apply. Method-specific analytics can be layered onto the existing extraction foundation, but source and intermediate lots need to remain canonical at each transformation.

### 8. Distillate -> vape carts

**Result: PARTIAL**

Production BOMs can model distillate plus hardware/packaging and create finished outputs, but Run 360 needs actual input consumption and unified source lineage before this is a trustworthy manufacturing transformation.

### 9. Distillate -> gummies / edible production

**Result: PARTIAL**

BOM, production standards, QA and finished-output controls are suitable, but cannabis ingredient consumption must post to the physical ledger and lineage graph. A compliant edible lot should trace through oil source packages all the way back to original plant/harvest sources where applicable.

### 10. Flower + distillate -> infused pre-roll

**Result: PARTIAL / high-value stress case**

The BOM model can represent multiple input products and reservations, which is good. This journey exposes the lineage problem most clearly: one finished lot needs multiple cannabis parents. Current Package Studio can model multi-input transformations better than normal Production Run 360.

### 11. Repack / multi-build / samples / rework

**Result: STRONG when performed through Package Studio**

Package Studio supports breakdown, pack-down, build run, multi-build, sample pull, rework and correction. It validates source availability, balances input = output source-equivalent + loss, posts negative/positive ledger transactions and records parent/child relationships.

This transformation contract should become the shared lineage engine beneath Production Run 360 and cultivation handoffs rather than remain isolated to Package Studio.

### 12. Finished lot -> wholesale storefront -> order -> pick/pack/ship

**Result: STRONG once finished inventory is trustworthy**

Wholesale eligibility requires released inventory, passed COA evidence and positive uncommitted quantity. Shared availability respects production reservations, wholesale reservations and wholesale commitments. Existing fulfillment tests also validate FEFO selection and scan-safe shipment decrements.

### 13. Finished production -> retail inventory -> sale

**Result: PARTIAL / cross-license handoff needs a dedicated operator test**

Retail and production inventories are correctly separate by operation/facility capability. Current code search did not expose one obvious first-class internal-facility transfer workflow that completes the full production-license -> retail-license movement as an operator journey. This should be verified and, if necessary, unified with the governed state traceability/manifest workflow.

### 14. Failed QA / hold / retest / remediation / rework

**Result: GOOD foundation, inconsistent depth by module**

Production Run 360 has QA hold/pass/fail/release/retest/deviation/remediation concepts and quarantines newly measured output. Extraction still needs first-class deviation/rework/resume and intermediate-hold behavior to match that maturity.

### 15. Recall / backward trace

**Result: BLOCKED for a true seed-to-sale recall**

Package 360 provides a useful package timeline and Package Studio parent/child lineage. It cannot currently guarantee:

`finished package -> production run -> all consumed source lots -> harvest -> plants -> mother/source package`

because cultivation-to-inventory lineage is missing and normal Production Run 360 does not create the same source edges as Package Studio.

## Critical defects to fix first

### P0-1 — Cultivation Harvest Output Posting

When a harvest is completed, require an explicit output-allocation step that turns measured harvest material into canonical inventory lots.

Minimum outputs should support:
- finished dry flower
- smalls
- trim / biomass
- fresh frozen
- waste / destruction
- other recoverable material

Requirements:
- total allocated source material must reconcile with the harvest measurement policy
- every output gets durable harvest ancestry
- output product/material type, quantity, unit, location, compliance package/tag reference and QA state are explicit
- local state and state-system intent remain separated and fail-closed
- no duplicate entry of strain, harvest code, source plants, facility or measured totals

### P0-2 — Production Material Actual Consumption

Add a governed `consume_materials` / material-actual step to Production Run 360.

Requirements:
- reservation is planning, not consumption
- operator records/scans actual lots and actual quantities consumed
- physical ledger is decremented atomically
- reservation is reduced/closed accordingly
- under/over-consumption creates variance rather than silently changing the BOM
- waste/rework is separately classified
- mutation uses preview-before-commit and stale-preview protection
- completion cannot silently create finished output while all cannabis input remains unconsumed

### P0-3 — Unified Transformation Lineage Graph

Create one lineage contract shared by:
- cultivation harvest outputs
- Production Run 360 consumption/output
- extraction source/WIP/output
- Package Studio
- rework/correction
- wholesale/retail package movement

Package 360 should then answer both directions recursively:

`Where did this come from?`

and

`What did this become?`

A recall should be able to traverse the graph without relying on free-text notes.

## High-priority operator improvements

### P1-1 — First-class Cultivation navigation

Expose Cultivation as a clear Production Ops workflow rather than requiring operators to infer Inventory -> Plants.

Suggested surface:
- Cultivation Today
- Nursery / Batches
- Plants
- Rooms
- Harvests
- Cultivation Inventory
- Regulatory Health

### P1-2 — Nursery and batch workflows

Add durable genetics/mother/batch relationships and bulk creation workflows:
- seed intake / seed batch
- clone batch from selected mother
- plant-tag range assignment / scan workflow
- batch phase changes where legally/operationally appropriate
- source-package selection where genetics entered from inventory

### P1-3 — Extraction execution sequence

Implement the extraction audit's target flow:

`Plan -> Reserve -> Preflight -> Stage -> Start -> Consume Actual -> Intermediate Outputs -> QA/Hold -> Finished Output -> Closeout`

Do not consume material at planning time.

### P1-4 — Cross-license transfer journey

Make production/cultivation -> retail/commercial facility transfers explicit, previewed and easy to discover. Local inventory intent, manifest/state-system action, provider response, receiving and reconciliation should be one visible journey without merging legal facility inventories.

### P1-5 — Doobie Agent vertical reasoning

Once the canonical lineage graph exists, add deterministic tools for:
- harvest output reconciliation
- source-to-finished genealogy lookup
- production input actual-vs-BOM variance
- unexplained mass-balance variance
- recall blast radius
- "what can this harvest become?" planning
- "do we have enough material to fulfill wholesale without starving production/retail?"

The Agent should explain and stage corrective actions, not invent inventory transactions.

## UX acceptance rule

A cannabis operator should be able to start from the object in their hand and continue the work from context.

Examples:
- On a flowering plant: **Add to harvest**
- On a completed harvest: **Allocate harvest outputs**
- On a bulk flower lot: **Package / Send to production / Send to extraction / Offer wholesale**
- On a production run: **Stage materials -> Consume actual -> Record output -> QA -> Close**
- On a finished lot: **Label / Package 360 / Wholesale / Transfer / Audit / Recall trace**

The operator should not need to know which internal DoobieLogic module owns the next transaction.

## Proposed remediation order

1. Fix Harvest -> canonical inventory output posting.
2. Fix Production reservation -> actual material consumption.
3. Unify transformation lineage across Cultivation, Production, Extraction and Package Studio.
4. Add regression tests proving source balances decrement and child lots retain source ancestry.
5. Add first-class cultivation/nursery navigation and batch workflows.
6. Implement extraction preflight/intermediate/closeout sequence.
7. Verify and simplify cross-license facility transfer/receiving journey.
8. Add Agent lineage/mass-balance/recall tools only after the ledger graph is authoritative.
9. Run the same operator simulation in a real authenticated browser and record actual click counts, timing, mobile friction and recovery behavior.

## Required regression scenarios

A release should not be considered vertically complete until automated tests prove all of the following:

1. Mother/clone or source package -> plant -> harvest relationship survives lifecycle transitions.
2. Harvest completion can allocate multiple child inventory lots and reconcile measured material.
3. A production run consuming 10 g from a 100 g lot leaves 90 g physical balance, not 100 g.
4. A finished output cannot be released without its required QA policy.
5. A finished package can recursively trace to all parent source lots.
6. A parent source lot can recursively enumerate all downstream finished packages.
7. Multi-input infused products retain every cannabis parent.
8. Package Studio and Production Run 360 use compatible lineage semantics.
9. Wholesale cannot sell failed/held/no-COA inventory or quantity already committed elsewhere.
10. Cross-tenant/facility access cannot expose or mutate another legal inventory scope.
11. A failed/reworked output preserves both original and rework ancestry.
12. A simulated recall returns the complete blast radius across production and sales/wholesale allocations.

## Release recommendation

Do not spend the next engineering cycle mainly adding more cannabis product formats. The application already has enough domain surfaces to model many formats.

The next cycle should make the **material graph authoritative**.

Once Harvest -> Inventory, Production Actual Consumption, and Unified Lineage are complete, the existing production, extraction, Package Studio, wholesale, compliance and Doobie Agent capabilities become dramatically more valuable because they will all be reasoning over the same trustworthy cannabis history.
