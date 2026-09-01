# DoobieLogic Operator Acceptance Suite

This document defines the stateful operator test for DoobieLogic. The goal is not to prove that pages render. The goal is to determine whether a real operator can run a cannabis business through the application without losing traceability, inventory truth, compliance state, cost lineage, or workflow context.

## Rating scale

| Rating | Meaning |
| --- | --- |
| Works naturally | The operator can complete the intended job with clear state changes and no unnecessary friction. |
| Works but awkward | The workflow succeeds, but navigation, terminology, clicks, or feedback create avoidable operator friction. |
| Incomplete | Part of the intended workflow is absent or requires an unsupported/manual workaround. |
| Broken | The intended workflow errors, produces inconsistent state, or cannot be completed. |
| Dangerous / ambiguous | The workflow can create misleading inventory, compliance, traceability, permission, QA, cost, or lineage state. |

## Test principles

1. Use the application statefully. Create the plant/material/package/order through DoobieLogic and follow the same record downstream instead of seeding the final answer.
2. Exercise happy paths and failure paths.
3. Verify downstream effects after every meaningful mutation.
4. Keep organization, facility, license, role, and operation-mode isolation active throughout the test.
5. Treat usability friction as a defect even when the underlying endpoint succeeds.
6. Never weaken a test simply to make a workflow green. Fix the workflow when the real operator behavior is wrong.
7. Extraction and Retail are first-class operational domains with the same acceptance depth as Cultivation and Production/Manufacturing.

## Operational domains and required journeys

### Retail Ops

| Surface | Stateful acceptance scenarios |
| --- | --- |
| Buyer Operations | Need identification, recommendations, vendor selection, PO creation, budget effect, delivery performance, replenishment-policy changes. |
| Inventory | Normal receipt, duplicate receipt, partial/problem receipt, QA hold, package lookup, source filtering, expiration views, adjustment, discrepancy handling. |
| Retail Inventory Transfers | Dispatch/receive or fail closed when the selected license/facility cannot perform the transfer; package identity must remain consistent. |
| Inventory Audits | Start independent audit, focused SKU/package audit, blind count, scan count, variance, pause, resume, stop, complete, adjustment posting, CSV/XLSX report. |
| Product 360 | Overview, inventory, sales, packages, audit handoff, source package context, COA/QA context. |
| Package 360 | Current package identity, history, lineage, QA/COA, movements, package actions. |
| Catalog Administration | Product mapping, operation scope, sellability, missing mappings, safe correction. |
| Slow Movers | Velocity/DOH logic, action handoff, no false positives caused by stale sales data. |
| Reports | Sales/category trends, executive reports, export/download behavior, cross-check to underlying sales and inventory. |
| Compliance | Compliance Q&A, traceability, state actions, Label Studio, nomenclature mapper, MA flower equivalency where applicable. |

### Cultivation

| Surface | Stateful acceptance scenarios |
| --- | --- |
| Plants | Seed/clone creation, seedling, vegetative, flowering, room move, harvest, destroy, invalid transition. |
| Harvest | Full and partial harvest, wet/dry weights, waste, source plant ancestry, resulting inventory. |
| Inventory | Bulk flower/trim/biomass visibility, receiving under cultivation/production license, reservations and package identity. |
| Genealogy | Plant -> harvest -> lot/package ancestry remains queryable downstream. |
| Handoff | Cultivation material can feed packaging, production, extraction, or wholesale only when eligible. |

### Production / Manufacturing

| Surface | Stateful acceptance scenarios |
| --- | --- |
| Production Today | Queue ordering, behind/on-time state, labor/capacity context, next-work decision. |
| Calendar | Scheduled work appears at the correct facility and time. |
| Production Run 360 | Reserve, consume, WIP, output, yield, waste, QA, cost, genealogy, completion. |
| Production Inventory | Bulk/WIP/finished goods separation, holds, reservations, adjustments, audits. |
| Production Inventory Transfers | Correct license/facility isolation and package identity across internal movements. |
| Product Master | Production-only products, packaging profiles, labels, categories, BOM/standard references. |
| White Label / Repack | Split/repack lineage, new package tag, inherited COA only when valid, quantities reconcile. |
| Package Studio | Package creation from eligible material, quantity/mass balance, current tag, Product Master packaging. |

### Extraction

Extraction must be exercised as a complete operating area, not as a page-load check.

| Surface / process | Stateful acceptance scenarios |
| --- | --- |
| Today / Runs | Create run, reserve eligible source lot, start work, find run, reopen historical run. |
| BHO / Hydrocarbon | Cured and live-resin workflow, input reservation/consumption, measured stage outputs, loss, output lot, QA, cost, release. |
| Ethanol | Biomass/trim -> crude/refinement, optional winterization/filtration/decarb/distillation stages, WIP handoff. |
| Distillation | Crude -> distillate, intermediate package identity, output mass/yield and costs. |
| Solventless | Ice-water hash, dry sift, hash rosin; source eligibility, intermediate output, final output. |
| CO2 | Extraction/refinement workflow where enabled. |
| Formulation / vape inputs | Formulation base, terpene handling mode/source/percentage, deterministic formulation math, downstream fill/package handoff. |
| Run 360 | Inputs, events, QA, costs, traceability, mass balance, COGS, notes, hold/release. |
| Failure paths | Over-reservation, over-consumption, invalid stage, hold, failed QA, unauthorized QA decision, missing package identity. |

### Wholesale / Distribution

| Surface | Stateful acceptance scenarios |
| --- | --- |
| Wholesale Ops | Eligible inventory appears only after QA/package/product requirements pass. |
| Storefront / customer portal | Customer browses allowed products, creates order, operator approves/rejects. |
| Orders | Reservation/allocation, edits, rejection, approval, status lifecycle. |
| Warehouse Pick / Pack | Pick exact package, prevent over-pick, packing, fulfillment, resulting inventory state. |
| Accounting effects | Costs/prices/totals remain consistent with the order and inventory source. |

### Compliance / QA / Label Studio

| Surface | Stateful acceptance scenarios |
| --- | --- |
| COA Library | Upload, parse, METRC-tag index, wrong-tag rejection, unresolved tag confirmation, duplicate/conflicting COA handling. |
| QA evidence | Hold/pass/fail/retest, immutable original evidence, current summary projection. |
| Split/repack lineage | Child/current METRC tag differs from tested ancestor while COA remains traceable to the tested material. |
| Label Studio | Current tag QR + Code128, package weight conversion, multipack composition, top 3 terpenes + Total Terpenes, cannabinoid results, expiration = one year from passed test date. |
| Testing-label scope | Packaging-only statutory warnings/symbols do not block or print on testing labels. |
| LabelGuard | Missing identity/COA/test date blocks release; reviewed passing label can print. |

### Administration / platform

| Surface | Stateful acceptance scenarios |
| --- | --- |
| Home / Control Towers | Attention items and metrics link to the correct underlying work. |
| Location Settings | Facility/license/capability changes affect available workflows correctly. |
| Data & Settings | Imports, mappings, source selection, failures, re-import/idempotency. |
| Admin Tools | Users, roles, facility permissions, tenant isolation. |
| Integrations | Configured/unconfigured traceability and accounting providers fail closed with useful guidance. |
| Doobie Agent | Context-aware read-only guidance, correct facility scope, useful answers, permission isolation, provider/tool failure behavior. |

## Cross-domain journeys

The suite must prove these records survive handoffs rather than testing each module in isolation:

| Journey | Required chain |
| --- | --- |
| Packaged flower | Plant -> harvest -> dry inventory -> QA/COA -> package -> Label Studio -> wholesale/retail. |
| Bulk wholesale flower | Plant -> harvest -> dry bulk lot -> QA/COA -> wholesale without pretending it is retail packaged inventory. |
| BHO concentrate | Cultivation material -> extraction run -> concentrate WIP -> QA -> package -> label -> wholesale/retail. |
| Ethanol/distillate | Biomass/trim -> ethanol -> crude -> distillation -> distillate -> package or manufacturing input. |
| Solventless | Flower/fresh frozen -> hash -> rosin -> QA -> package -> label. |
| Infused pre-roll | Flower + eligible extract -> production run -> packaged multipack -> inherited/source lineage -> label. |
| Vape | Distillate/rosin -> formulation -> fill/package -> QA/COA rules -> label -> wholesale/retail. |
| Edible | Extract input -> manufacturing/BOM -> units -> QA -> package -> wholesale/retail. |
| Retail-only | External receipt -> catalog -> inventory -> audit -> sales import/POS context -> reports. |
| Vertically integrated | Cultivation/production/extraction licenses remain distinct while genealogy and business reporting connect correctly. |

## Required edge cases

- Duplicate receipt or package.
- Missing or wrong COA.
- Failed, held, quarantined, or expired material.
- Split package with a new current METRC tag and inherited tested-material COA.
- Cross-facility and cross-organization access attempts.
- User role without permission for the attempted mutation.
- Over-reservation, over-consumption, negative/invalid count, and over-pick.
- Audit pause/resume/stop and later continuation.
- Partial harvest, partial receipt, partial production/extraction consumption.
- Rejected transfer/order and cancelled work.
- Integration unavailable or incorrectly mapped.
- Doobie Agent tool/provider failure without unsafe mutation or fabricated state.

## Automation layers

The suite is intentionally layered:

- **Route/boot sweep:** every workspace and sub-route must open without browser/API 5xx errors.
- **Real-browser interaction:** click tabs, dialogs, filters, forms and primary operator actions against the real FastAPI stack.
- **Stateful API acceptance:** exercise full durable mutations and verify downstream records.
- **Cross-domain lifecycle tests:** create a record upstream and follow it to saleability/fulfillment.
- **Human-friction review:** record unnecessary clicks, unclear terminology, weak feedback, dead ends, and context loss even when automation passes.

This file is a living acceptance contract. New operator-facing surfaces must be added here and to automated coverage before they are considered complete.