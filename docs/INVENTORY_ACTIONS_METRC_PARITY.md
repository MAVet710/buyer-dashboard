# Inventory Actions / Metrc parity

DoobieLogic inventory screens should behave like operational workspaces, not passive lists. When an operator selects inventory, the product should expose the actions that are valid for that object, role, facility, state, and lifecycle status.

## Product rules

- **Move** means changing the room/location/sublocation inside the same licensed facility.
- **Transfer** means inventory leaves one licensed facility for another and follows the transfer/manifest workflow.
- DoobieLogic actions are classified as **Operational**, **Compliance**, or **Hybrid**.
- Compliance-changing actions follow **preflight → confirmation → execution → verification → audit**.
- A documented Metrc endpoint is not enough to enable an automatic write. The exact deterministic payload contract and jurisdiction/environment scope must be reviewed first.
- Unknown or uncertain provider outcomes fail closed and reconcile; they are never blindly repeated.
- Inventory quantity, package identity, location, reservations, and Metrc state remain separate concepts. A Move never changes quantity.

## Priority matrix

| Priority | Operator action | Object | Class | Metrc v2 evidence | DoobieLogic posture |
| --- | --- | --- | --- | --- | --- |
| P0 | Move | Package | Hybrid | `PUT /packages/v2/location` | Add contextual action now; provider dispatch remains locked until exact payload contract is verified. Local/demo move may update only DoobieLogic with an explicit no-Metrc state. |
| P0 | Adjust | Package | Hybrid | `PUT/POST /packages/v2/adjust` | Already has tracked provider/local reconciliation. Surface consistently from inventory Actions. |
| P0 | Finish | Package | Hybrid | `PUT /packages/v2/finish` | Existing reviewed write contract. Surface contextually when valid. |
| P0 | Unfinish | Package | Hybrid | `PUT /packages/v2/unfinish` | Add explicit contract; keep dispatch locked until exact payload is reviewed. |
| P0 | Split / create child package | Package | Hybrid | `POST /packages/v2/` and testing/planting variants | Package Studio exists. Keep one guided workflow rather than duplicate inventory ledgers. |
| P0 | Transfer | Package(s) | Hybrid | Transfers v2 endpoint family | Route to transfer/manifest workflow; never label this Move. |
| P0 | Audit / verify | Package/Product | Operational | n/a | Existing durable audit engine; expose from every inventory context. |
| P0 | Print label | Package/Product | Operational/Hybrid | n/a for local print | Existing printing/Package Studio path; expose contextually. |
| P1 | Hold / Release | Package/Lot | Operational + regulatory-aware | state depends on provider/lab/package lifecycle | Operational hold must immediately block sellability/allocation. Never invent a Metrc hold mutation without verified state semantics. |
| P1 | Change item | Package | Hybrid | `PUT /packages/v2/item` | Known capability; automatic dispatch locked until deterministic payload contract is reviewed. |
| P1 | Change/add note | Package | Hybrid | `PUT /packages/v2/note` | Known capability; automatic dispatch locked until payload contract is reviewed. |
| P1 | COA / lab status | Package | Operational/Compliance | lab tests v2 endpoint family | View/verify/attach where allowed. Regulatory result mutations remain separately controlled. |
| P1 | Move | Plant | Hybrid | `PUT /plants/v2/location` | Existing known write gap. Contextual cultivation action; dispatch currently locked. |
| P1 | Move | Plant batch | Hybrid | `PUT /plantbatches/v2/location` | Add known write gap; dispatch locked until payload verification. |
| P1 | Move | Harvest | Hybrid | `PUT /harvests/v2/location` | Add known write gap; dispatch locked until payload verification. |
| P1 | Allocate / unallocate | Package/Lot | Operational | n/a | DoobieLogic reservations only; must affect available inventory immediately. |
| P1 | Allocate to run / return unused | Package/Lot | Operational | n/a until a later regulatory action is required | Use production reservation/consumption truth and preserve lineage. |
| P1 | Report problem | Any inventory | Operational | n/a | Create a durable discrepancy/task without forcing the operator to choose a module. |
| P2 | Waste / destroy | Package/Plant/Harvest | Hybrid | Plant/harvest waste is documented; package waste is not assumed | Implement only where exact provider semantics are verified. Never infer a package-waste endpoint. |
| P2 | Flags/remediation/pretreat/decontaminate | Package | Compliance | documented package v2 actions in supported markets | Add only after jurisdiction-specific operational need and payload verification. |

## Inventory action menu

The normal package selection should converge on a consistent menu such as:

`Move · Adjust · Hold/Release · Split/Package Studio · Allocate · Transfer · Label · Audit · Package 360`

The menu is contextual. Invalid actions are omitted or disabled with a clear reason; they are not permanently hidden elsewhere in the application.

Bulk selection may safely expose actions such as Move Selected, Hold Selected, Print Labels, Start Audit, or Start Transfer only when every selected record passes the same preflight.

## Execution boundary

A state-system action has five distinct states:

1. **Preflight** — tenant, facility, role, license, environment, object status, reservations, and provider capability are checked.
2. **Confirmation** — operator sees exactly what will change and where.
3. **Execution** — provider mutation is submitted only through a reviewed write contract.
4. **Verification** — provider readback/local state confirms the requested result; accepted is not treated as verified.
5. **Audit** — actor, before/after state, provider transaction, timestamps, and reconciliation state are durable.

This keeps Metrc as compliance truth while DoobieLogic becomes the simpler operating surface.