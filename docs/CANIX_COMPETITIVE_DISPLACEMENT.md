# Canix Competitive Displacement Roadmap

## Objective

DoobieLogic should not copy Canix screen-for-screen. Absorb the operational primitives Canix has proven in cannabis ERP, then make them easier, more automatic, more cross-functional, and more intelligence-driven.

> Canix records and organizes the operation. DoobieLogic should understand, prioritize, and help execute the operation.

## Governing interaction model

**Today / Home / workspace surfaces answer: What needs attention?**

**360 windows answer: Work on the thing.**

**Doobie Agent answers: Why, what changed, what is likely next, and what should I consider?**

There is no separate Work Engine destination. Generated and manual Next Actions attach to the durable operational object and open its 360 execution context.

Examples:

- flowering plant past estimated harvest -> Plant 360
- package variance above tolerance -> Package 360
- extraction yield anomaly -> Extraction Run 360
- production material shortage or QA hold -> Production Run 360
- product stockout risk -> Product 360
- compliance exception -> the relevant compliance evidence/action context
- PO approval -> PO 360 when implemented

Next Actions may carry priority, due window, assignee/role, checklist, recurrence, estimated/actual labor, evidence, approval requirement, and cost attribution, but they must not become a competing task silo.

## Verified Canix strengths worth incorporating

### 1. Mobile/offline floor execution and hardware

Canix supports offline mobile work, RFID, barcode scanners, and connected scales.

DoobieLogic response:

- PWA/offline application shell.
- Durable tenant/facility/license-bound action queue.
- Visible Pending / Synced / Needs Review / Failed states.
- Scanner, scale, and RFID capture abstractions feeding the same audited business logic used online.
- Prioritize Inventory Audits, Cultivation, Receiving, Extraction, Pick/Pack, and production actuals.

Differentiator: one trusted capture layer across Retail, Production, Cultivation, Extraction, Receiving, and Compliance with explicit conflict review instead of silent overwrite.

### 2. Task management tied to real operational cost

Canix has mature templates, recurrence, assignments, checklists, attachments, triggers, labor hours, inventory association, and cost allocation.

DoobieLogic response:

Do not create a generic task module. Add **Next Actions** to existing operational objects and 360s.

Next Actions should support:

- source signal and deterministic reason
- priority and due window
- assignee/crew or required role
- checklist/evidence
- estimated and actual duration
- labor/material attribution
- recurring rules when recurrence is genuinely useful
- approval requirement where mutation risk warrants it
- exact durable entity reference

Most Next Actions should be generated from operational state before a manager has to configure anything.

### 3. Cultivation forecasting and crop execution

Canix has mature cultivation workflows, nursery forecasting, RFID, labor costing, and added Trym's crop-steering expertise.

DoobieLogic response:

Phase 1:
- Cultivation Today
- system-generated Next Actions
- overdue/missing harvest-date detection
- room assignment exceptions
- 8-week flowering harvest forecast
- Plant 360 as the execution surface

Phase 2:
- plant batch and Harvest 360
- nursery/clone demand forecast driven by downstream demand
- recurring cultivation action templates attached to plant/batch/room objects
- labor/material COGS allocation
- harvest yield standard vs actual
- room utilization and upcoming transitions

Phase 3:
- environmental/crop-steering integrations
- sensor ingestion and threshold exceptions
- facility-SOP-grounded Cultivation Agent brief

Differentiator: connect cultivation forecasting forward into manufacturing and backward into Buying requirements.

### 4. Production templates, BOMs, expected outputs, and planning

Canix supports BOMs, batch templates, expected outputs, calendars, required inventory, labor/material/machine planning, standard cost, and planned-vs-actual analysis.

DoobieLogic already has durable production orders, active BOMs, scaled requirements, FIFO reservations, multi-output runs, labor and machine actuals, QA, COGS, attainment, resources, crews, Extraction workflows, and Production Run 360.

DoobieLogic response:

- Treat the existing Product BOM as the recipe/template foundation rather than inventing a parallel recipe database.
- Extend product/run standards with expected outputs/yields, baseline labor, machine/resource requirements, QA requirements, and compliance checkpoints.
- Prefill the run from Product Master + BOM + order + source material.
- Calculate readiness for the target start date, not only current on-hand.
- Generate Production Next Actions for material blockers, QA holds, stalled/held runs, output shortfalls, and schedule risk.
- Every action opens the exact Production Run 360.
- Compare standard vs planned vs actual output, cost, labor, waste/loss, and timing.

Differentiator: DoobieLogic recommends which run should launch and why using orders, inventory risk, labor, machinery, material availability, margin, and due dates.

### 5. Review & approvals

Canix supports granular approval permissions and pending submissions.

DoobieLogic response:

Approval is a state on the affected operational object, surfaced as a Next Action and worked inside its 360/context. Do not create an isolated approval data universe.

Priority approvals:
- inventory adjustment/reconciliation
- compliance submissions/retries
- QA/production release
- PO approval and purchasing overrides
- package destruction/waste
- BOM/recipe standard changes
- large financial write-offs

Every approval must show exact before/after mutation preview, evidence, calculated impact, requester, facility/license context, and resulting audit event. Doobie Agent can summarize evidence but cannot authorize the mutation.

### 6. Autosave, recovery, and sync transparency

Competitive reviews expose two practical weaknesses worth attacking: losing in-progress work on reload/lag, and delayed/unclear external synchronization.

DoobieLogic response:

- autosave drafts for PO/order/receiving/production workflows
- restore after reload/device interruption
- explicit stale/conflict detection
- global integration ledger for Metrc/BioTrack/accounting/commerce
- source record, destination record, status, attempt history, error, retry, reconciliation evidence
- surface sync failures in the operational 360, not only Settings

### 7. Accounting and commercial integrations

Prioritize QuickBooks Online for smaller operators, then Sage/enterprise accounting where demand justifies it. Financial sync belongs in the related PO/run/order/vendor/customer 360 context and in a global integration ledger.

### 8. Reporting and operational BI

Keep exportable detailed reports, but default to:
- Needs Attention
- What changed?
- Why did it change?
- What should happen next?
- projected impact
- actual outcome

## Deliberate DoobieLogic advantages

### Native operational AI

DoobieLogic's provider-neutral runtime spans Operations, Buyer, Purchasing, Inventory, Audit, Compliance, Repack, Co-Man Production, Extraction, Commercial, Cultivation, and Data Hub. Preserve deterministic Python/SQL first, authoritative retrieval, immutable server-side tenant scope, provider neutrality, local inference support, and human-owned authorization.

### Extraction as a first-class operating workflow

Maintain the stage-aware extraction floor, automatic loss/yield/formulation calculations, QA, COGS, traceability, and contextual Run 360 rather than reducing extraction to generic manufacturing records.

### Purchasing intelligence

Continue pushing beyond procurement entry into reorder decisions, DOH/velocity, expiration/overstock exposure, vendor performance, budget impact, and approval-ready PO actions.

## Ranked execution plan

### P0 — immediate displacement

1. Cultivation Today + generated Next Actions + harvest forecast -> Plant 360.
2. Production Next Actions from existing BOM/run/QA state -> Production Run 360.
3. Extend Product BOM into richer production standards: expected output/yield, labor, machine, QA, compliance checkpoints.
4. Approval state + exact mutation preview attached to existing 360 objects.
5. Autosave/recovery for PO, orders, receiving, production, and long operator forms.
6. Global sync ledger with retry/reconciliation evidence surfaced in relevant 360s.

### P1 — floor execution moat

7. PWA/offline shell.
8. Durable offline action queue with tenant/license binding and sync conflict review.
9. Unified scanner abstraction.
10. Bluetooth scale capture.
11. RFID adapter interface and supported-device pilot.
12. Mobile quick-action surfaces for plants, audits, receiving, extraction, and pick/pack.

### P1 — cultivation depth

13. Plant Batch 360 and Harvest 360.
14. Nursery/clone forecast.
15. Cultivation labor/material COGS.
16. Harvest yield standards vs actual.
17. Room utilization/capacity planning.
18. Cultivation -> production -> purchasing demand propagation.

### P2 — enterprise/commercial parity

19. QBO synchronization/reconciliation.
20. Sage Intacct connector.
21. Customer invoicing/payments/credits as strategically justified.
22. Saved/custom reporting and enterprise BI exports.
23. Environmental/crop-steering integration framework.

## Competitive scoring rule

Every Canix-inspired capability must answer:

- Canix capability reproduced: yes/no
- DoobieLogic workflow simpler: yes/no
- fewer primary user decisions: yes/no
- automatically calculated/prefilled fields: count
- automatically generated Next Actions: count
- action opens existing 360/context: yes/no
- cross-workspace context preserved: yes/no
- tenant/facility/license isolation covered: yes/no
- mobile path covered: yes/no
- evidence/audit history covered: yes/no
- Doobie Agent adds grounded value without owning authorization: yes/no

Equivalent screens are parity, not displacement.
