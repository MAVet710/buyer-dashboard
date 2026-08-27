# Canix Displacement Implementation — 360-First Slice

## Architecture decision

DoobieLogic does not add a separate Work Engine destination.

- workspace/Home/Today surfaces generate and prioritize **Next Actions**
- the relevant **360 window is the execution surface**
- Doobie Agent may explain, calculate, summarize, and recommend but does not own mutation authorization

## Implemented in this slice

### Cultivation

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

### Production

Production Next Actions derive from `/api/v1/production/orders`, which is already backed by Production Run 360 state and existing production ERP calculations.

Generated actions:
- QA hold -> Review QA hold
- BOM/material reservation gap -> Resolve material blocker
- run on hold -> Review held run
- in-progress actual below planned -> Continue run execution

Selecting an action passes the durable production order ID into the existing Production Run 360 WorkspaceWindow. Run 360 accepts the targeted order while preserving its normal selector for switching runs.

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

Future template work should extend these canonical objects rather than create a second recipe/template data model.

## Next slices

1. Extend Product BOM standards with expected yield/output, standard labor, machine/resource requirements, QA requirements, and compliance checkpoints.
2. Add approval state + exact mutation preview to the affected 360 objects.
3. Add draft autosave/recovery to long operator workflows.
4. Build the global external-sync ledger and surface failures inside 360s.
5. Add PWA/offline queue, then scanner/scale/RFID capture adapters.
