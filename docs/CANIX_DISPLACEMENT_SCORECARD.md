# Canix Displacement Scorecard

Status meanings:

- **Lead** — DoobieLogic has a meaningful product advantage today.
- **Competitive** — core capability exists; maturity/integration may differ.
- **Gap** — Canix currently has a material advantage.
- **Build** — active displacement target.

| Capability | Canix | DoobieLogic current state | Status | Displacement move |
| --- | --- | --- | --- | --- |
| Cultivation plant lifecycle | Mature plant/batch/harvest workflows, RFID/mobile | Plant tags, phases, rooms, mother lineage, estimates, events | Gap | Cultivation Today, Plant/Harvest 360, batch workflows |
| Cultivation forecasting | Nursery/yield/production forecasting | Basic estimated harvest dates | Build | 8-week forecast first; nursery + demand propagation next |
| Crop steering/environmental | Trym acquisition adds strong domain expertise | No environmental integration framework | Gap | Sensor/crop-steering adapter after core cultivation execution |
| Floor task management | Templates, recurrence, checklists, attachments, triggers | Work is workspace-specific; no universal task engine | Build | Doobie Work Engine with generated work first |
| Labor COGS in cultivation | Mature labor costing to plant/batch/harvest/package | Production labor/COGS exists; cultivation labor not mature | Gap | Work completion -> cost allocation with permissioned wage visibility |
| Non-cannabis inventory + task use | Mature | Production/BOM foundation exists | Competitive | Unified materials model tied to Work Engine and recipes |
| Manufacturing templates | Mature batch templates + BOM prefill | Durable production/extraction workflows exist | Build | Production Recipes/Templates on existing run engine |
| Production planning | Labor/machine/material planning, expected outputs, standard cost | Production resources, machines, crews, reservations, actuals, optimizer | Competitive | Required inventory by date + recommendation-aware launch plan |
| Extraction-specific execution | Modeled through manufacturing | Dedicated stage-aware Extraction floor + Run 360 | Lead | Continue stage/method intelligence and machine telemetry |
| Yield/loss intelligence | Mature yield reporting | Extraction inline loss/yield + production attainment/economics | Lead | Standards vs actual + anomaly detection |
| Buying/reorder intelligence | Procurement and planning | DOH, velocity, reorder priority/qty, overstock/expiration, vendor performance | Lead | Turn recommendations into approval-ready PO actions |
| Compliance sync | Mature Metrc/BioTrack estate | Tenant/license-safe integrations and reconciliation architecture | Gap | Broaden proven state/system coverage + visible sync ledger |
| Approval queue | Granular Canix submission approvals | Domain permissions exist; no universal approval workbench | Build | Review & Approvals with exact mutation preview and evidence |
| Offline mobile | Offline-enabled native mobile | Responsive web/mobile workflows | Gap | PWA + durable offline action queue |
| Barcode scanning | Mobile/web scanning | Camera and scanner audit workflows exist | Competitive | Unified capture layer across operational workflows |
| RFID | Mature supported-device ecosystem | No RFID abstraction | Gap | Device-neutral RFID adapter + pilot hardware |
| Connected scales | Supported scale adapters/devices | Manual measurement entry | Gap | Scale capture abstraction for Extraction/Receiving/Harvest/Production |
| QuickBooks | Mature bi-directional workflows | Integration foundations exist but less mature | Gap | QBO first with integration ledger/reconciliation |
| Sage Intacct | Mature integration | Not comparable today | Gap | Enterprise connector after QBO |
| Sales/invoicing/payments | Mature | Orders/fulfillment exists; finance maturity lower | Gap | Invoice/payment/credit workflow if market strategy requires |
| Reporting | Mature configurable BI | Strong reports + decision dashboards | Competitive | Lead with exception/decision intelligence rather than report count |
| Native operational AI | MCP currently scoped mainly to sales/inventory | Provider-neutral multi-domain native Agent runtime | Lead | Expand grounded cross-domain operational reasoning |
| Contextual multitasking | Conventional ERP navigation; users value multiple browser tabs | Product/Package/Run 360 windows + persistent Doobie Agent | Lead | Continue non-blocking contextual work model |
| Draft resilience/autosave | Reviewers report lost order work on lag/reload | Partial workspace state preservation | Build | Durable autosave for PO/order/run/receiving drafts |
| Sync transparency | Users report occasional Metrc refresh/sync lag | Compliance attempts/reconciliation exists in domains | Build | Global integration/sync ledger with retry + evidence |
| Implementation friction | G2 reports ~3 month average implementation | Import/mapping/sandbox tools exist | Competitive | Guided migration + Mapping Agent + readiness score |

## Immediate sequence

1. **Cultivation Today** — in PR #322.
2. **Doobie Work Engine** — universal generated/manual work model.
3. **Production Recipes/Templates** — prefill materials, outputs, labor, machines, QA and compliance.
4. **Review & Approvals** — exact mutation preview and evidence.
5. **Draft autosave + recovery** — purchasing/orders/production/receiving first.
6. **Global sync ledger** — Metrc/BioTrack/accounting/commerce visibility.
7. **PWA/offline queue** — tenant-bound action staging and sync reconciliation.
8. **Hardware capture** — barcode -> scale -> RFID.
9. **Cultivation cost depth** — labor/material cost and yield standards.
10. **QBO reconciliation** — followed by Sage if enterprise demand justifies it.

## Product rule

For each Canix capability we adopt, DoobieLogic must add at least one of the following:

- automatic work generation
- deterministic calculation/prefill
- fewer operator decisions
- cross-domain context
- better exception explanation
- stronger recovery/reconciliation
- contextual Doobie Agent reasoning

If we merely reproduce the same screen, it is parity, not displacement.
