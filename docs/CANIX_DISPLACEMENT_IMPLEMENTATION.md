# Canix Displacement Implementation — 360-First Strategy

## Architecture decision

DoobieLogic does not add a separate Work Engine destination.

- workspace/Home/Today surfaces generate and prioritize **Next Actions**
- the relevant **360 window is the execution surface**
- Doobie Agent may explain, calculate, summarize, and recommend but does not own mutation authorization

## Purchasing guardrail

Production planning may identify a material shortage and explain exactly what is missing, but **DoobieLogic must not automatically create, submit, approve, or place a purchase order from the Production workspace**.

- Production can surface a shortage as **Buyer review required**
- Buying remains the decision surface for purchasing
- a human buyer retains control of PO creation, editing, staging, approval, and submission
- Doobie Agent may recommend or explain purchasing needs but cannot bypass the existing approval/mutation path

This is intentional product behavior, not a missing automation feature.

## Implemented

### Cultivation Today

Cultivation Today derives directly from facility plant records:
- active plant count
- harvests due in 7 and 30 days
- active rooms
- overdue flowering harvest estimates
- missing veg/flower harvest estimates
- unassigned rooms
- 8-week harvest forecast by week and strain

Generated actions:
- Review harvest readiness
- Prepare for harvest
- Set harvest estimate
- Assign cultivation room

Selecting an action opens the exact Plant 360 in a non-modal WorkspaceWindow. The existing lifecycle transition API remains the only mutation path.

### Production Next Actions

Production Next Actions derive from `/api/v1/production/orders`, which is backed by Production Run 360 state and existing production ERP calculations.

Generated actions include:
- QA hold -> Review QA hold
- BOM/material reservation gap -> Resolve material blocker
- run on hold -> Review held run
- in-progress actual below planned -> Continue run execution
- labor/output variance outside standard -> Review the exact run

Selecting an action passes the durable production order ID into the existing Production Run 360 WorkspaceWindow.

### Product BOM production standards

The canonical Product BOM remains the recipe source of truth and now carries version-bound execution standards for:
- expected output / process loss
- standard labor hours
- standard machine hours
- standard cycle time
- resource category
- QA requirement
- compliance checkpoint

Run 360 compares the scaled standard with actual execution records rather than asking the operator to enter actuals twice.

### Decision-first Production Plan

Production now has a read-only planning layer that answers **What should we run next?** from the durable operational state already in DoobieLogic.

The plan ranks active work as:
- CONTINUE
- RUN NOW
- RUN NEXT
- AT RISK
- BLOCKED

Signals include:
- due date and priority
- BOM requirement quantities
- current lot balances
- material already reserved to the run
- material reserved by other runs
- scheduled labor capacity
- required machine/resource category
- QA hold state
- configured BOM production standards
- compliance checkpoint visibility

A true material shortage is labeled **Buyer review**. The plan never performs a purchasing mutation.

## Existing Canix-equivalent foundation intentionally reused

The production ERP already has:
- Product BOMs
- scaled material requirements
- FIFO material reservation
- production orders
- planned and actual outputs
- labor and machine actuals
- waste/rework events
- QA hold/release
- COGS events
- attainment
- resources and crews
- audit/evidence history

Future planning work extends these canonical objects rather than creating a second recipe/template data model.

## Next displacement slices

1. Add a capacity-aware Production Calendar that warns about material, labor, machine, QA, and due-date conflicts before schedule changes are committed.
2. Add approval state + exact mutation preview to affected 360 objects.
3. Add draft autosave/recovery to long operator workflows.
4. Build the global external-sync ledger and surface Metrc/BioTrack/accounting failures inside the relevant 360.
5. Add offline/PWA action queue, then scanner, Bluetooth scale, and RFID capture adapters.
6. Deepen Cultivation 360 with mobile scan workflows, labor/consumable costing, and demand-linked harvest/crop forecasting.
7. Extend closed-loop costing from BOM standard -> actual run -> yield/loss -> COGS -> product/order profitability.
8. Add accounting reconciliation depth for QuickBooks first, then Sage.
