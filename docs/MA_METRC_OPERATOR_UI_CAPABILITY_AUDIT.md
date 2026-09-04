# Massachusetts Metrc operator UI capability audit

Baseline: `977fce379a155c56f1a178460feb86c532b70a41`  
Reviewed: 2026-09-04  
Jurisdiction: Massachusetts  
Provider surface: Metrc v2

## Product rule

DoobieLogic is the operator surface. Metrc is the regulated adapter underneath it.

An operator should normally see business language such as **Create room**, **Move plants**, **Finish harvest**, **Adjust package**, **Build transfer**, or **Complete delivery**. The server is responsible for tenant/facility/license scope, the exact reviewed provider payload, permission checks, human confirmation, authenticated submission, HTTP evidence, provider readback, reconciliation state, and audit history.

A documented Metrc endpoint is not permission to dispatch it. There are three distinct proof levels:

1. **Documented** — present in the reviewed Massachusetts v2 documentation.
2. **Evaluation executable** — DoobieLogic has a bounded deterministic evaluator for the exact method/path/payload and fresh readback. This is code readiness, not an official pass until it is executed successfully against the assigned sandbox.
3. **Operator promoted** — the normal product workflow can execute it through a governed, auditable, fail-closed provider path.

Unknown or uncertain provider outcomes are never blindly repeated.

## Current baseline

| Workflow | Current state on baseline | Evaluation / governed evidence | Operator gap |
| --- | --- | --- | --- |
| Facility | Live | Sandbox discovery, exact license mapping, independent facility validation, switching, permission introspection, `Validate this sandbox facility` | Keep provider work explicit and facility-scoped |
| Locations / Rooms | Live reads + create preview | `location_create`, `location_update` evaluation executors | Promote exact create/update; keep sublocation/discontinue locked until separately proven |
| Strains | Live reads + create preview | `strain_create`, `strain_update` evaluation executors | Promote exact create/update; keep discontinue locked until separately proven |
| Items | Live reads + comprehensive create preview | `item_create`, `item_update` evaluation executors | Promote exact create/update; keep brands/discontinue locked until separately proven |
| Plant Batches | Backend evaluation only | plantings, packages, growth phase, delete | Surface lifecycle actions contextually from Cultivation; do not create a second plant ledger |
| Plants | Local cultivation UX + backend evaluation | location, plantings, plant-batch package, delete, manicure, harvest | Connect natural cultivation actions to exact Metrc transactions and readback |
| Harvest / Post-Harvest | Local post-harvest UX + backend evaluation | packages, waste, finish, unfinish | Promote finish/waste/package actions from the harvest workflow; keep moisture loss, usable output, and waste concepts distinct |
| Packages | Strong local package/inventory surfaces | create, item, adjust, finish, unfinish evaluation executors; governed Package Finish already exists | Converge package actions into contextual Inventory / Package 360 menus; add readback verification consistently |
| Transfers / Manifests | Governed outgoing template path exists | `transfer_template_create` is controlled MA-sandbox write; manifest readback/PDF lifecycle exists | Surface one Build transfer flow from eligible packages/orders; do not confuse Move with Transfer |
| Sales | Backend evaluation only | receipt create/update/delete; delivery create/update/complete | Expose only where Backoffice owns the business workflow. Register/POS remains a separate future client, but Backoffice owns authoritative sales/traceability services |
| Evidence / Reconciliation | Durable traceability ledger exists | requested → validated → queued → submitted → accepted → verified/reconciliation-required; manifest lifecycle has explicit readback | Make verification state visible after every promoted operator action and give operators a clear reconciliation path |

## Exact evaluation-executable operations on current main

### Master data (#452)

- `POST /locations/v2/` — create location
- `PUT /locations/v2/` — update location
- `POST /strains/v2/` — create strain
- `PUT /strains/v2/` — update strain
- `POST /items/v2/` — create item
- `PUT /items/v2/` — update item

The master-data evaluator requires Massachusetts sandbox scope, separate integrator/user credentials, HTTP 200, a provider identity, and fresh exact by-ID readback. Sublocations, brands, and discontinue operations are documented but are **not** promoted by this evidence.

### Cultivation / production lifecycle (#456)

Plant batches:

- `POST /plantbatches/v2/plantings`
- `POST /plantbatches/v2/packages`
- `POST /plantbatches/v2/growthphase`
- `DELETE /plantbatches/v2/`

Plants:

- `PUT /plants/v2/location`
- `POST /plants/v2/plantings`
- `POST /plants/v2/plantbatch/packages`
- `DELETE /plants/v2/`
- `POST /plants/v2/manicure`
- `PUT /plants/v2/harvest`

Harvests:

- `POST /harvests/v2/packages`
- `POST /harvests/v2/waste`
- `PUT /harvests/v2/finish`
- `PUT /harvests/v2/unfinish`

Packages:

- `POST /packages/v2/`
- `PUT /packages/v2/item`
- `PUT /packages/v2/adjust`
- `PUT /packages/v2/finish`
- `PUT /packages/v2/unfinish`

These 19 evaluator contracts are bounded to fixed operation names, methods, paths, payload builders, and readback resources. They are not generic arbitrary Metrc writes.

### Sales (#457)

- `POST /sales/v2/receipts`
- `PUT /sales/v2/receipts`
- `DELETE /sales/v2/receipts/{id}`
- `POST /sales/v2/deliveries`
- `PUT /sales/v2/deliveries`
- `PUT /sales/v2/deliveries/complete`

The sales evaluator also preserves Metrc's facility-local timestamp contract rather than silently converting operator values to UTC/Z timestamps.

## Massachusetts documented capability beyond the evaluation minimum

The current Massachusetts v2 documentation also exposes additional location/sublocation, package, plant, harvest, processing, transfer, transporter, tag, and sales lifecycle operations. These remain useful roadmap evidence, but they stay fail-closed until DoobieLogic has both an exact deterministic request contract and controlled sandbox write/readback proof for the specific action.

Examples that must **not** be promoted merely because the endpoint exists include package location/note corrections, plant-batch location changes, harvest location changes, processing-job mutations, transfer cancellation/rejection variants, and additional sales-delivery lifecycle actions.

## Operator workflow target

### Facility → Locations → Strains → Items

Facility Setup owns facility-level master data. Common actions should be direct:

- **Create room**
- **Rename / edit room**
- **Create strain**
- **Edit strain**
- **Create Metrc item**
- **Edit Metrc item**

The normal flow is:

`operator form → preflight → human confirmation → exact provider write → HTTP result → fresh by-ID readback → verified/reconciliation state → audit evidence`

Raw endpoint/payload detail belongs under an advanced evidence disclosure, not in the primary operator interaction.

### Plant Batches → Plants

Cultivation should expose only actions valid for the selected lifecycle state and role, for example:

- **Create plant batch / plantings**
- **Move plants**
- **Move to vegetative**
- **Create batch from plants**
- **Create package from plants**
- **Record manicure**
- **Harvest plants**
- **Destroy / discontinue** only when lifecycle rules allow it

Bulk actions must preflight every selected record before submission.

### Harvest / Post-Harvest

The harvest board should remain operationally simple while preserving exact traceability concepts underneath:

- **Record wet weight**
- **Record waste**
- **Create package / testing package** where supported
- **Finish harvest**
- **Reopen harvest** as a controlled correction path

Local WIP, finished flower, trim, biomass, waste, and moisture loss remain separate concepts. Finishing a harvest must reconcile outputs and waste before the provider mutation is allowed.

### Packages

The package action menu should converge on contextual actions such as:

`Move · Adjust · Hold/Release · Split/Package Studio · Allocate · Transfer · Label · Audit · Package 360`

Additional lifecycle actions such as **Finish package**, **Reopen package**, or **Change item** appear only when valid. A package Move never changes quantity, and a Transfer always leaves the facility through the manifest workflow.

### Transfers / Manifests

Use one guided flow:

`select eligible packages/order → recipient/license → driver/vehicle/route → review → build provider template/manifest state → readback → shipment lifecycle`

The operator should not need to understand Metrc template endpoint names.

### Sales

Backoffice should expose authoritative sales traceability actions through business workflows, while the future separate POS remains only a register interaction client. Promoted actions must preserve exact receipt/delivery identity and local timestamp semantics.

## Evidence contract for every promoted action

Every promoted mutation must retain or make queryable:

- organization, facility, license, jurisdiction, environment
- actor and approving/confirming actor
- canonical operator request
- exact provider method/path (evidence layer only)
- sanitized provider request body
- HTTP status and sanitized response
- provider/external identity when returned
- fresh readback resource and result
- before/after or expected/observed state
- transaction status
- timestamps
- mismatch/reconciliation reason
- idempotency key / retry posture

**Accepted is not Verified.** A provider HTTP success without the required readback remains accepted/pending verification, not a completed compliance fact.

## Implementation order

1. Promote the six #452 master-data actions into Facility Setup with a natural confirmation/verification experience.
2. Connect #456 Plant Batch and Plant actions to Cultivation context menus and bulk preflight.
3. Connect Harvest/Post-Harvest actions, preserving local mass-balance rules.
4. Converge package actions in Inventory / Package 360 and promote only the exact #456-proven contracts.
5. Finish transfer/manifest operator flow around the existing governed template + readback lifecycle.
6. Promote the six #457 sales actions only through Backoffice-owned sales/delivery services.
7. Make evidence/reconciliation status consistently visible from each affected object and from the global traceability queue.

This document is a promotion gate: future work should update the row/status when an action moves from documented → evaluation executable → operator promoted.