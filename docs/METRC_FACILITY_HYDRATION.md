# Metrc facility hydration contract

## Product rule

After an administrator verifies the exact Metrc facility/license/jurisdiction/environment mapping, DoobieLogic should progressively become populated from provider-owned regulatory state instead of asking operators to rebuild data that already exists in Metrc.

Metrc is the regulatory source of truth. DoobieLogic remains the canonical operational ledger. Reconciliation is the controlled boundary between them.

## Natural workspace rule

A successful Metrc read must not terminate at the Integrations screen when the returned information has an applicable operator-facing home in DoobieLogic.

For every supported provider resource, DoobieLogic chooses one of two safe visibility modes:

1. **Materialized** — provider state maps cleanly to a canonical DoobieLogic entity without inventing business history. Examples include Product Master items and active inventory packages. Missing canonical records may be created with exact provider identity links; existing conflicting local records are never silently overwritten.
2. **Provider shadow** — the provider owns an existing workflow/history object and creating a local workflow row would falsely imply that DoobieLogic created or executed it. The last synced state is displayed naturally in the applicable workspace as read-only provider-owned state. Existing Metrc transfers are the first implementation of this mode.

The rule is workspace-oriented, not Inventory-specific. As each resource is promoted, locations belong in Facility Setup, items in Product Master, packages in Inventory, plants/plant batches/harvests in Cultivation, processing state in Production, transfers in Transfer Control/Receiving/Wholesale, lab data in Testing/Compliance/labels, and sales state in the applicable retail/reporting surfaces.

## This implementation slice

The explicit facility initial-sync step now:

1. Reads every available page for the verified Metrc bootstrap resources, using 100-record pages and a defensive 100-page ceiling per collection.
2. Preserves the provider records in the existing immutable integration-sync mirror with deterministic fingerprint deduplication.
3. Uses the completed active-package snapshot to seed new canonical Product + Inventory Lot + append-only inventory balance records when package and Metrc Item identity are unambiguous.
4. Writes exact Product↔Metrc Item and Inventory Lot↔Metrc Package identities into the existing provider-neutral `traceability_object_links` spine. Generic Product/POS external IDs are not claimed by Metrc hydration.
5. Can establish those exact identity links for an already-existing local package when its compliance package label matches the provider package and no conflicting link exists; it still does not change the existing balance, room, Product metadata, or status.
6. Fails closed if an existing traceability link belongs to another jurisdiction/license scope, even when the provider ID itself matches.
7. Returns collisions and ambiguous identities as materialization conflicts rather than guessing or silently overwriting local state.
8. Marks unknown/untested package lab state as local hold; only explicit passed/released/not-required states seed as available.
9. Records provider-seeded inventory through the normal organization/facility ledger and audit trail, so existing Inventory and reconciliation surfaces can see it immediately.

The DEV Metrc sandbox runtime also proves the natural-workspace behavior end-to-end for its three deterministic resources:

- `items` → Product Master materialization with exact Metrc Item identity links
- `packages` → Inventory materialization with append-only starting balances and exact package links
- `transfers` → read-only provider shadow rows in Transfer Control, without fabricating ActionProposal, manifest, order or receiving-preflight history

A replay of the same sandbox sync is idempotent: it must not duplicate Products, Inventory Lots or starting inventory transactions.

### Provider resources mirrored by facility bootstrap

Normalized resources:

- active locations
- active strains
- active items
- available package tags
- available plant tags
- active packages
- active plant batches
- vegetative plants
- flowering plants
- active harvests

Direct resources:

- active sublocations
- location types
- item categories
- item brands
- units of measure

Mirrored means the provider record is durably preserved. It does **not** by itself mean every resource above has already been promoted into a canonical workspace. The natural-workspace rule is the contract governing that remaining promotion work.

## Non-overwrite rule

Initial hydration is allowed to create missing canonical state and establish exact provider identity. It is not allowed to repair a disagreement by mutating an existing canonical record.

Examples:

- Metrc package exists and DoobieLogic package does not: seed the package when exact Package and Item identity are available.
- Same Metrc package label already exists locally: establish exact identity links when unambiguous, but do not change quantity, room, Product metadata, or status; reconciliation owns any difference.
- Local lot code collides with the Metrc package label but does not carry the same compliance package identity: block materialization and return a conflict.
- Exact Metrc Item identity exists but local Product name/unit differs: preserve the local Product and report a warning.
- Metrc package has no exact Item id/name pair or no exact provider Package ID + label pair: do not guess identity.
- Existing Item/Package link belongs to a different license scope: block hydration and require reconciliation rather than rebinding it.
- Existing Metrc transfer was created outside DoobieLogic: show it as provider-owned state in Transfer Control rather than creating a fake local manifest proposal.

## Still required by the approved end state

This PR establishes the hydration/materialization and natural-visibility foundation. The following remain separate implementation slices and should not be represented as complete until shipped and tested:

- page-level durable checkpoint/resume inside a partially completed provider resource
- complete live-bootstrap Product Master materialization for standalone Metrc Items, including items with no active package
- canonical/safe Facility Setup visibility for locations, sublocations, strains, item categories/brands and units of measure
- cultivation workspace hydration for plant batches, tagged plants and harvests
- package/plant tag availability in the applicable operational selectors
- richer universal Regulatory Detail / raw-provider drawer
- retail sales-receipt and sales-delivery operator surfaces
- rejected-transfer exception visibility
- processing-job/provider production state in the normal Production workspace
- incremental changed-record sync and operator-facing freshness indicators

The existing full-page hydration is restartable and deduplicated, but a mid-resource retry currently re-reads that resource from page 1. Do not describe it as page-checkpoint resumable until durable per-page cursors are implemented and tested.
