# Canix Displacement Scorecard

Status meanings:
- **Lead** — DoobieLogic has a meaningful product advantage today.
- **Competitive** — core capability exists; maturity/integration may differ.
- **Gap** — Canix currently has a material advantage.
- **Build** — active displacement target.

| Capability | DoobieLogic current state | Status | Displacement move |
| --- | --- | --- | --- |
| Cultivation lifecycle | Plant tags, phases, rooms, mother lineage, estimates, events | Competitive | Cultivation Today + Plant/Harvest 360 + batch depth |
| Cultivation forecasting | Estimated harvest dates + new 8-week forecast | Build | Nursery demand + room capacity + yield standards |
| Floor task management | Workspace-specific actions | Build | Generated Next Actions attached to 360 objects; no separate task silo |
| Labor COGS in cultivation | Production labor/COGS exists; cultivation labor not mature | Gap | Attribute completion labor/materials to plant/batch/harvest |
| Manufacturing templates | Active Product BOM, requirements, reservations, outputs, resources | Competitive | Extend BOM standards instead of parallel recipe database |
| Production planning | Machines, crews, reservations, actuals, optimizer, Run 360 | Competitive | Readiness + generated Next Actions + target-date requirements |
| Extraction execution | Dedicated stage-aware floor + Run 360 | Lead | Continue standards/anomaly/machine telemetry |
| Yield/loss intelligence | Extraction inline loss/yield + production attainment | Lead | Standard vs actual anomaly detection |
| Buying intelligence | DOH, velocity, reorder qty/priority, expiration/overstock, vendor performance | Lead | Approval-ready PO actions and recovery |
| Compliance sync | Tenant/license-safe integration architecture | Gap | Broaden coverage + global sync/reconciliation ledger |
| Approval workflow | Domain permissions exist | Build | Approval state and mutation preview inside affected 360/context |
| Offline mobile | Responsive mobile workflows | Gap | PWA + durable offline action queue |
| Barcode scanning | Camera/scanner audit workflows | Competitive | Unified capture layer |
| RFID | No device abstraction | Gap | Device-neutral adapter + pilot |
| Connected scales | Manual measurements in key workflows | Gap | Scale capture for Extraction/Receiving/Harvest/Production |
| QuickBooks | Connector foundations; less mature | Gap | QBO sync + reconciliation ledger |
| Reporting | Strong reports + decision dashboards | Competitive | Lead with exceptions, explanation, projected impact |
| Native operational AI | Provider-neutral multi-domain Agent runtime | Lead | Expand grounded cross-domain recommendations |
| Contextual multitasking | Product/Package/Run 360 + persistent Agent | Lead | Add Plant/Harvest/PO 360 and keep actions contextual |
| Draft resilience/autosave | Partial workspace preservation | Build | Durable PO/order/receiving/production draft recovery |
| Sync transparency | Domain reconciliation exists | Build | Global integration ledger + retry/evidence in 360 |

## Immediate sequence

1. Cultivation Today -> Plant 360.
2. Production Next Actions -> Production Run 360.
3. Extend Product BOM into richer run standards.
4. Approval state + mutation preview inside existing 360s.
5. Draft autosave + recovery.
6. Global sync ledger.
7. PWA/offline queue.
8. Hardware capture: barcode -> scale -> RFID.
9. Cultivation cost/yield depth.
10. QBO reconciliation, then Sage if justified.

## Product rule

For each Canix capability we adopt, DoobieLogic must add at least one of:
- automatic Next Action generation
- deterministic calculation/prefill
- fewer operator decisions
- cross-domain context
- better exception explanation
- stronger recovery/reconciliation
- contextual Doobie Agent reasoning

Every action must execute through the existing durable 360/context when one exists. If we merely reproduce the same screen, it is parity, not displacement.
