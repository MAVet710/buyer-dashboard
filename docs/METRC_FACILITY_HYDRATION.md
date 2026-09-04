# Metrc facility hydration contract

## Product rule

After an administrator verifies the exact Metrc facility/license/jurisdiction/environment mapping, DoobieLogic should progressively become populated from provider-owned regulatory state instead of asking operators to rebuild data that already exists in Metrc.

Metrc is the regulatory source of truth. DoobieLogic remains the canonical operational ledger. Reconciliation is the controlled boundary between them.

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

### Provider resources hydrated

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

## Non-overwrite rule

Initial hydration is allowed to create missing canonical state and establish exact provider identity. It is not allowed to repair a disagreement by mutating an existing canonical record.

Examples:

- Metrc package exists and DoobieLogic package does not: seed the package when exact Package and Item identity are available.
- Same Metrc package label already exists locally: establish exact identity links when unambiguous, but do not change quantity, room, Product metadata, or status; reconciliation owns any difference.
- Local lot code collides with the Metrc package label but does not carry the same compliance package identity: block materialization and return a conflict.
- Exact Metrc Item identity exists but local Product name/unit differs: preserve the local Product and report a warning.
- Metrc package has no exact Item id/name pair or no exact provider Package ID + label pair: do not guess identity.
- Existing Item/Package link belongs to a different license scope: block hydration and require reconciliation rather than rebinding it.

## Still required by the approved end state

This PR establishes the hydration/materialization foundation. The following remain separate implementation slices and should not be represented as complete until shipped and tested:

- page-level durable checkpoint/resume inside a partially completed provider resource
- canonical master-data materialization for locations, sublocations, strains, item categories/brands and units of measure
- cultivation workspace hydration for plant batches, tagged plants and harvests
- richer universal Regulatory Detail / raw-provider drawer
- retail sales-receipt and sales-delivery operator surfaces
- rejected-transfer operator surface
- incremental changed-record sync and operator-facing freshness indicators

The existing full-page hydration is restartable and deduplicated, but a mid-resource retry currently re-reads that resource from page 1. Do not describe it as page-checkpoint resumable until durable per-page cursors are implemented and tested.
