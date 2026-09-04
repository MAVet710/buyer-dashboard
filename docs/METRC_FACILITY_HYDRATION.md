# Metrc facility hydration contract

## Product rule

After an administrator verifies the exact Metrc facility/license/jurisdiction/environment mapping, DoobieLogic progressively becomes populated from provider-owned regulatory state instead of asking operators to rebuild data that already exists in Metrc.

**Metrc is regulatory truth. DoobieLogic is the canonical operational ledger. Reconciliation is the controlled boundary.**

A successful Metrc read must not terminate at the Integrations screen when the returned information has an applicable operator-facing home in DoobieLogic.

## Materialized vs provider-owned shadow state

DoobieLogic uses two visibility modes:

1. **Materialized** — provider state maps cleanly to a canonical DoobieLogic entity without inventing business history. Missing canonical records may be created with exact provider-neutral identity links. Existing conflicting local state is never silently overwritten.
2. **Provider shadow** — Metrc owns an already-existing workflow/history object and creating a local transaction would falsely imply DoobieLogic performed it. The synchronized provider state is displayed read-only in the natural workspace instead.

Examples:

- Metrc Items → Product Master
- Metrc Packages → Inventory
- referenced Locations → Cultivation Rooms when required by a complete cultivation baseline
- Plant Batches → Cultivation Groups
- tagged Plants → Cultivation Plants
- Harvests → Cultivation Harvests
- existing Transfers → Transfer Control / Receiving / Wholesale provider shadows
- Processing state → Production regulatory state
- Sales receipts/deliveries → Retail regulatory state
- available plant/package tags → durable operational selectors
- package-specific lab results → Package 360 testing evidence

## Exact scope and identity

Every authenticated provider operation is scoped by:

- organization
- DoobieLogic facility
- jurisdiction
- provider environment
- exact Metrc license

Regulatory identities live in provider-neutral `traceability_object_links`. Provider IDs and regulatory tags establish identity; mutable names never rebind an existing local object.

Cross-license identities, duplicate provider identities, ambiguous local collisions, and attempted rebinding fail closed.

## Durable provider evidence

DoobieLogic keeps two complementary provider stores:

- `integration_sync_records` — immutable audit/history evidence with deterministic fingerprint deduplication
- `integration_provider_snapshots` — the latest provider membership/current state used by normal workspaces

A complete full provider snapshot may mark previously returned rows not-present. Failed, truncated, or permission-skipped reads never erase previously proven provider membership.

Incremental `lastModifiedStart` reads are deltas: they may create/update current rows but **never** infer deletion from an omitted row. A later complete full snapshot is the authority for absence/removal.

## Full authenticated facility hydration

The verified facility bootstrap:

1. Reads provider collections with 100-record pages.
2. Persists immutable sync evidence and current-provider membership separately.
3. Uses durable page-level hydration checkpoints.
4. Resumes an interrupted resource after revalidating the provider anchor/page-1 evidence and pagination consistency.
5. Uses bounded provider concurrency and retry behavior.
6. Honors provider `Retry-After` up to a bounded 30-second ceiling.
7. Treats capability-specific 403/404 results as permission skips instead of breaking unrelated facility onboarding.
8. Does not promote truncated or transport-uncertain collections as complete current membership.

The authenticated API runtime raises the defensive full-sync ceiling to 10,000 pages per resource. At 100 records/page that permits up to 1,000,000 rows per collection while retaining checkpoint/resume behavior. The ceiling is still a safety guard, not evidence that a truncated collection is complete.

## Natural Product Master and Inventory hydration

### Items

Metrc Items can seed missing Product Master records and Product Master profiles when identity is unambiguous. Existing local business fields are enriched only when blank; populated business data is not overwritten to mirror Metrc.

### Packages

A complete active-package snapshot can seed missing Inventory Lots and append-only starting Inventory Transactions. Exact Product↔Metrc Item and Inventory Lot↔Metrc Package identities use `traceability_object_links` rather than generic POS/external-product IDs.

Important rules:

- re-running the same hydration does not duplicate Products, lots, or starting balances
- an existing local package with the exact compliance package tag may be linked without changing its balance, room, Product, or status
- package quantity/location/status/Product disagreements remain reconciliation findings
- unknown/untested packages default to hold
- only explicit released/passed/not-required testing states are seeded available

## Natural Cultivation hydration

Canonical cultivation hydration can create:

- referenced Metrc locations → `CultivationRoom`
- plant batches → `CultivationPlantGroup`
- vegetative/flowering tagged plants → `CultivationPlant`
- harvests → `CultivationHarvest`

The materializer establishes exact provider identities but does not fabricate historical local lifecycle events.

Existing linked local lifecycle state is never silently changed to match Metrc. Phase, room, strain, or harvest differences are surfaced for reconciliation.

### Composite completeness gate

Cultivation is a composite canonical workspace. Full materialization is withheld unless the same verified baseline has complete current snapshots for:

- locations
- plant batches
- vegetative plants
- flowering plants
- harvests

A partial provider response therefore cannot create a half-valid local cultivation lifecycle.

Incremental cultivation changes are materialized only after this complete cultivation baseline exists. Required location/batch dependencies are loaded from DoobieLogic's current local provider snapshot rather than making a second provider request.

## Normal workspace behavior

Normal page loads do not put Metrc on the critical path. They read the locally synchronized current-provider snapshot.

Current natural surfaces include:

- **Facility Setup** — synchronized location/sublocation, strain/item and reference-data status/counts
- **Cultivation** — synchronized plant batches, vegetative/flowering plants, harvests and reconciliation; explicit live verification remains available
- **Production** — synchronized package/processing regulatory state without inventing local production orders
- **Transfer Control / Receiving / Wholesale** — incoming/outgoing provider shadows and rejected-transfer exceptions
- **Retail Insights** — provider-owned sales receipt/delivery regulatory state without fabricating local `RetailSale` rows
- **Tag-dependent workflows** — synchronized available plant/package tags while locally reserved/used/voided tags cannot be resurrected
- **Package 360 / Product 360** — reusable Regulatory Detail from local provider evidence

## Regulatory Detail

The universal local Regulatory Detail contract exposes, when authorized:

- provider identity
- jurisdiction/license/environment scope
- current provider membership
- sync freshness/evidence
- reconciliation-required state
- normalized provider record
- lossless raw provider payload

Opening this detail does not contact Metrc.

### Package-specific lab evidence

Metrc `GET /labtests/v2/results` is treated as a package-scoped lookup, not a valid facility-wide baseline collection.

Package 360 therefore loads cached package-specific lab evidence from DoobieLogic and exposes an explicit **Verify live** action for the exact linked Metrc Package identity. A successful complete live verification replaces only that package's cached lab membership. An incomplete response is non-destructive and cannot erase previously cached results.

## Incremental and periodic synchronization

After a trusted complete baseline exists, routine sync uses Metrc `lastModifiedStart` with a five-minute overlap to absorb provider/client clock drift.

Incremental sync:

- is non-destructive
- updates current snapshot rows that were actually returned
- hydrates newly changed Items and Packages naturally
- hydrates eligible changed Cultivation state after the complete cultivation baseline exists
- does not repeatedly classify permission-skipped resources as missing baselines

A complete authenticated re-baseline is required on the current 24-hour policy so removals and full-only reference resources are periodically proven again.

## Operator sync semantics

For a trusted real Metrc sandbox mapping, the operator-facing Metrc Sync / Retry / Runtime controls represent authenticated Metrc provider state.

Deterministic developer fixtures remain a DoobieLogic simulated-sandbox behavior and must never masquerade as a successful real Metrc facility synchronization.

## Non-overwrite examples

- Metrc package exists and DoobieLogic package does not → seed when exact Package and Item identity are available.
- Same exact package tag exists locally → link identity when unambiguous, but preserve existing local operational values.
- Local lot code collides with the Metrc package label but is not the same compliance identity → block and reconcile.
- Exact Metrc Item identity exists but Product name/unit differs → preserve local Product and warn/reconcile.
- Existing traceability identity belongs to another license → block rather than rebind.
- Existing Metrc transfer was created outside DoobieLogic → display provider-owned state instead of creating fake local workflow history.
- Incomplete cultivation baseline → display synchronized regulatory state where safe, but do not create a partial canonical cultivation lifecycle.

## Acceptance boundary

Repository tests and CI are necessary but are not an official Metrc evaluation pass.

Before claiming live Metrc integration acceptance:

1. deploy the exact validated build
2. use the saved encrypted Metrc sandbox credentials
3. verify the exact Massachusetts sandbox facility/license mapping
4. run authenticated full hydration against the real provider
5. verify provider-returned data appears naturally in each applicable DoobieLogic workspace
6. rerun sync and prove idempotence/no duplicate canonical state
7. exercise incremental synchronization and explicit live package/testing verification
8. resolve any real provider permission/path behavior exposed by that run

Only actual sandbox execution can move the relevant Metrc evaluation items from code-ready to provider-passed.
