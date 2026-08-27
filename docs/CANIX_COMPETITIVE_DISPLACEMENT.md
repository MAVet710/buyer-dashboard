# Canix Competitive Displacement Roadmap

## Objective

DoobieLogic should not copy Canix screen-for-screen. The goal is to absorb the strongest operational primitives Canix has proven in cannabis ERP, then make them easier, more automatic, more cross-functional, and more intelligence-driven.

Positioning target:

> Canix records and organizes the operation. DoobieLogic should understand, prioritize, and help execute the operation.

The win condition is not feature-count parity. It is that an operator can accomplish the same core compliance/ERP jobs while DoobieLogic requires fewer decisions, fewer screens, and less duplicate entry, and gives the user better forward-looking guidance.

## Verified Canix strengths worth incorporating

### 1. Mobile/offline floor execution and hardware

Canix supports an offline-enabled mobile app, RFID workflows, barcode scanners, and connected scales. Their published 2026 hardware guide includes Ohaus scales through RS232/Bluetooth adapters, Zebra barcode scanners, and several TSL/Zebra RFID readers.

DoobieLogic response:

- Add a Mobile Operations Runtime rather than separate one-off mobile features.
- Support offline-safe queued actions with visible Pending / Synced / Needs Review states.
- Add a hardware abstraction layer for scanner, RFID, and scale inputs.
- Treat hardware input as another trusted capture method feeding existing audited workflows rather than creating alternate business logic.
- Prioritize Inventory Audits, Cultivation, Receiving, Extraction measurements, Pick/Pack, and production actuals.

DoobieLogic differentiator:

- One capture layer across Retail, Production, Cultivation, Extraction, Receiving, and Compliance.
- Offline actions retain organization/facility/license scope and require server-side revalidation on sync.
- DoobieLogic explains conflicts instead of silently overwriting changed records.

### 2. Task management tied to real operational cost

Canix tasks support categories, templates, recurring schedules, assignments, checklists, attachments, inventory associations, triggers, labor hours, and non-cannabis inventory cost allocation.

DoobieLogic response: build a **Doobie Work Engine**, not another generic task list.

Work Engine objects should support:

- organization/facility/license scope
- work type/domain
- source signal
- due window
- priority
- assignee/crew
- estimated and actual duration
- checklist
- cannabis/package/plant/run/order references
- non-cannabis materials
- labor rate visibility permissions
- predicted operational impact
- actual cost allocation
- approval requirements
- evidence/history
- recurring templates
- deterministic triggers

DoobieLogic differentiator:

Most work should be generated automatically from operational state before requiring a manager to create a task.

Examples:

- flowering plant past estimated harvest -> Review harvest readiness
- production order at risk due to material shortage -> Resolve material blocker
- extraction stage beyond expected cycle time -> Review stalled run
- inventory package nearing expiration -> Disposition expiring inventory
- open PO past expected delivery -> Follow up with vendor
- compliance action failed -> Reconcile compliance submission
- audit variance above threshold -> Recount / investigate
- customer order cannot allocate -> Resolve fulfillment shortage

Every generated work item should answer:

1. What needs to happen?
2. Why now?
3. What will happen if we do nothing?
4. What records/material are involved?
5. Who can perform/approve it?
6. What did it cost once complete?

### 3. Cultivation forecasting and crop execution

Canix has mature cultivation workflows, plant/harvest management, nursery forecasting, RFID, labor costing, and now owns Trym, adding crop-steering and mobile cultivation expertise.

DoobieLogic response:

Phase 1:
- Cultivation Today
- system-generated work queue
- overdue/missing harvest-date detection
- room assignment exceptions
- 8-week flowering harvest forecast
- phase/room/strain rollups

Phase 2:
- plant batches and harvest entities as first-class 360 objects
- nursery/clone demand forecast driven by downstream production/sales demand
- recurring cultivation work templates
- labor/material COGS allocation to plants/batches/harvests
- harvest yield assumptions vs actuals
- room utilization and upcoming transitions

Phase 3:
- environmental/crop-steering integrations
- sensor ingestion with exception thresholds
- target vs actual VPD/EC/PPFD/irrigation metrics where appropriate
- Doobie Agent cultivation brief grounded in facility SOPs and live conditions

DoobieLogic differentiator:

Cultivation forecasting should connect forward into manufacturing demand and backward into Buyer purchasing requirements. The user should not need separate planning models for grow, production, and purchasing.

### 4. Production templates, BOMs, expected outputs, and forward planning

Canix supports BOMs, batch templates, multi-step production runs, expected outputs, production calendars, required inventory, labor/material/machine planning, standard cost, and planned-vs-actual analysis.

DoobieLogic already has major portions of this foundation: production orders, requirements, reservations, outputs, machines, crews, actuals, COGS, attainment, Extraction workflows, and Run 360.

DoobieLogic response:

- Introduce reusable Production Recipes/Templates that combine:
  - process steps
  - expected inputs
  - allowed source material rules
  - non-cannabis BOM
  - expected outputs and yields
  - baseline labor
  - machine/resource requirements
  - QA requirements
  - compliance checkpoints
- Starting a production job should prefill the template from the selected product/order/source material.
- Required inventory should be calculated for the target start date, not just current on-hand.
- Compare standard vs planned vs actual cost, labor, output, loss, and timing.
- Use the existing Production Today concept as the execution surface rather than exposing configuration-heavy templates to normal operators.

DoobieLogic differentiator:

Templates should be recommendation-aware. When demand changes, DoobieLogic should tell the planner which template/run should be launched and why, based on orders, inventory risk, labor, machinery, material availability, margin, and due dates.

### 5. Approval and submission queue

Canix supports granular approval permissions and a pending User Submissions queue.

DoobieLogic response:

Create a universal **Review & Approvals** layer for sensitive mutations:

- inventory adjustments
- compliance submissions/retries
- large audit reconciliation
- production release
- QA release
- PO approval
- purchasing override
- package destruction/waste
- recipe/BOM changes
- financial write-offs

Each approval should show a preview of the exact change, evidence, source records, calculated impact, requester, facility/license context, and resulting audit event.

DoobieLogic differentiator:

The approval queue should include a deterministic risk explanation, not merely “pending approval.” Doobie Agent may summarize evidence, but authorization and execution remain deterministic and human-controlled.

### 6. Accounting and commercial integrations

Canix has mature QuickBooks Online and Sage Intacct workflows plus LeafLink/other commercial integrations. Their QBO integration supports invoices, payments, purchase orders, credit memos, item/customer/vendor mapping, and inventory synchronization.

DoobieLogic response:

- Continue provider-neutral accounting connector architecture.
- Prioritize QBO first for smaller operators, then Sage/enterprise accounting.
- Build an integration ledger that shows source record, destination record, sync status, last attempt, error, retry, and reconciliation evidence.
- Never hide accounting sync failures inside a settings page.

DoobieLogic differentiator:

Tie accounting back to operational 360s so a PO, production run, package, sales order, vendor, and customer can expose the related financial synchronization and profitability context without changing systems.

### 7. Reporting and operational BI

Canix has mature configurable reporting across facilities and a large historical operational dataset.

DoobieLogic response:

Avoid competing only with more dashboards. Focus on decision layers:

- Needs Attention
- What changed?
- Why did it change?
- What should happen next?
- projected impact
- actual outcome

Keep exportable detailed reports, but make the default experience exception- and decision-oriented.

## Areas where DoobieLogic should remain deliberately different

### Native operational AI instead of external-query AI only

Canix's August 2026 MCP documentation currently exposes sales and inventory and states that cultivation/harvest and production/manufacturing schedules are not yet queryable.

DoobieLogic already has provider-neutral agents for Operations, Buyer, Purchasing, Inventory, Inventory Audit, Compliance, Nomenclature, Repack, Co-Man Production, Extraction Scientist, Commercial, Commercial Finance, Cultivation, and Data Hub.

Do not reduce this to a generic chat feature.

The moat is:

- deterministic Python/SQL before LLM
- authoritative retrieval for compliance/SOP questions
- server-side tenant scope
- model-provider neutrality
- local-first inference support
- cross-domain operational reasoning
- contextual Agent + 360 windows

### Extraction as a first-class operating workflow

Canix manufacturing can model extraction runs, but DoobieLogic should maintain a specialized extraction experience with stage-aware measurements, loss/yield calculations, formulation math, QA, COGS, and inline floor updates.

### Purchasing intelligence

Canix procurement and planning are broad ERP capabilities. DoobieLogic should continue pushing beyond transaction entry into reorder recommendations, days-on-hand, velocity, expiration/overstock exposure, vendor delivery performance, budget impact, and decision-ready PO staging.

## Ranked execution plan

### P0 — immediate competitive displacement

1. Cultivation Today + deterministic work queue + harvest forecast.
2. Doobie Work Engine data model and API.
3. Work Engine templates/checklists/assignees/recurrence.
4. Deterministic work generators across Cultivation, Extraction, Production, Inventory, Buying, Compliance.
5. Production recipe/template layer on top of existing BOM/resources/runs.
6. Approval queue foundation and mutation preview model.

### P1 — floor execution moat

7. PWA/offline application shell.
8. Durable offline action queue with tenant/license binding and sync conflict review.
9. Unified scanner input abstraction.
10. Bluetooth scale capture adapter.
11. RFID adapter interface and supported-device pilot.
12. Mobile quick-action surfaces for plants, audits, receiving, extraction, pick/pack.

### P1 — cultivation depth

13. Plant batch and harvest 360.
14. Nursery/clone forecast.
15. Cultivation task labor and materials COGS.
16. Harvest yield standard vs actual.
17. Room utilization/capacity planning.
18. Cross-domain cultivation -> production -> purchasing demand propagation.

### P2 — enterprise/commercial parity

19. QBO transaction synchronization/reconciliation.
20. Sage Intacct connector.
21. Customer invoicing/payments/credit memo maturity.
22. Marketplace/commerce depth where strategically justified.
23. Saved/custom reporting views and enterprise BI exports.
24. Environmental/crop-steering integration framework.

## Competitive scoring rule

Every Canix-inspired feature must be scored before completion:

- Canix capability reproduced: yes/no
- DoobieLogic workflow simpler: yes/no
- fewer primary user decisions: yes/no
- automatically calculated/prefilled fields: count
- automatically generated next actions: count
- cross-workspace context preserved: yes/no
- tenant/facility/license isolation covered: yes/no
- mobile path covered: yes/no
- evidence/audit history covered: yes/no
- Doobie Agent adds grounded value without owning authorization: yes/no

A feature is not considered a Canix displacement win merely because DoobieLogic has an equivalent screen.

## First implementation slice

Branch `feat/canix-displacement-ops-engine` begins with **Cultivation Today**.

It derives, without requiring a separate task configuration step:

- active plant count
- harvests due within 7 days
- harvests due within 30 days
- active cultivation room count
- overdue flowering harvest estimates
- missing harvest estimates for vegetative/flowering plants
- unassigned-room exceptions
- prioritized operator work items
- 8-week flowering harvest forecast grouped by week and strain

Selecting a generated work item opens the existing Plant 360 workflow, preserving the current durable lifecycle controls rather than creating parallel mutation logic.

## Sources reviewed August 27, 2026

- https://www.canix.com/
- https://www.canix.com/product/production-planning
- https://www.canix.com/products/cultivation-workflows
- https://www.canix.com/states/massachusetts
- https://www.canix.com/blog-posts/canix-is-acquiring-trym-building-the-future-of-cannabis-operations-together
- https://help.canix.com/hc/en-us/articles/47278175700884-Canix-Mobile-App-Overview
- https://help.canix.com/hc/en-us/articles/47281192518292-Hardware-Guide-Canix-Mobile-App
- https://help.canix.com/hc/en-us/articles/5687690700436-Task-Management-Beta
- https://help.canix.com/hc/en-us/articles/32298339689236-Guide-to-Accurate-Costs-with-Canix-s-Cultivation-Module
- https://help.canix.com/hc/en-us/articles/360057142952-Create-Bill-of-Materials-BOM
- https://help.canix.com/hc/en-us/articles/34011518574996-Batch-Templates
- https://help.canix.com/hc/en-us/articles/33839462209428-Manufacturing-Calendar-Guide
- https://help.canix.com/hc/en-us/articles/30888726434708-QuickBooks-Online-Canix-Integration-Guide
- https://help.canix.com/hc/en-us/articles/360056951271-User-Submissions
- https://help.canix.com/hc/en-us/articles/52206703021972-Questions-the-Canix-MCP-Server-Can-Answer
