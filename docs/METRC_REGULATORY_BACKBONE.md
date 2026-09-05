# Metrc Regulatory Backbone

## Purpose

DoobieLogic treats Metrc as the authoritative regulatory system of record for state-tracked cannabis objects. DoobieLogic is the operational ERP layer that normalizes Metrc records into usable modules, adds business context that Metrc does not own, and writes regulated changes back to Metrc only through reviewed, permission-aware, auditable contracts.

This document defines the product and engineering contract for that behavior.

## Source-of-truth rules

### Metrc-authoritative facts

For a connected Metrc facility/license, DoobieLogic must defer to Metrc for regulated facts including, where applicable:

- facilities and license scope
- locations and sublocations
- tags
- plant batches and plants
- harvests
- items and item categories
- packages and package quantities
- testing status and regulated lab state
- transfers and manifests
- sales/delivery records
- processing jobs and other provider-owned regulatory workflow state

A local value must never silently override a conflicting Metrc-authoritative value.

### DoobieLogic-owned enrichment

DoobieLogic may add business context that Metrc does not own, such as:

- cost and purchasing intelligence
- internal SKU/nomenclature
- labor and production scheduling
- SOP links and operational notes
- customer allocations and demand planning
- internal QC workflow
- label templates and presentation
- forecasting and analytics
- user-facing workflow state that does not alter a regulated fact

Enrichment must remain linked to the exact provider object and facility/license scope.

## Canonical data flow

1. **Provider mirror**
   - Read Metrc using the exact organization/facility/jurisdiction/environment/license credential scope.
   - Preserve the provider record without loss for audit, troubleshooting, and reconciliation.

2. **Normalize**
   - Convert provider-specific shapes into provider-neutral DoobieLogic canonical records.
   - Do not infer or guess provider identity when exact identity is unavailable.

3. **Map**
   - Maintain a durable identity link between the DoobieLogic object and the exact Metrc resource/provider ID/tag under the exact facility/license scope.

4. **Populate modules**
   - Product Master from Metrc Items.
   - Inventory from Metrc Packages.
   - Cultivation from Metrc Plant Batches, Plants, Strains, Locations, and Tags.
   - Post Harvest from Metrc Harvests and downstream package state.
   - Receiving/Wholesale from Metrc Transfers.
   - Retail/Sales views from Metrc sales resources where the license supports them.
   - Testing/Compliance views from provider testing state.
   - Production/Processing from Metrc processing resources where supported.

5. **Operate in DoobieLogic**
   - Users work in normal modules, not an API/integration console.
   - Regulated actions create typed traceability commands linked to the canonical object.

6. **Capability gate**
   - Determine resource/action availability per facility/license using provider permissions and observed authenticated capability evidence.
   - Unsupported resources are `not_available_for_license`, not system failures.
   - A successful authenticated facility read prevents a resource-specific 401 from being treated as proof of globally invalid credentials.

7. **Writeback**
   - Only reviewed deterministic Metrc write contracts may dispatch.
   - Writes require exact facility/license/environment mapping, user permission, provider capability, explicit authorization, payload validation, and an audit trail.
   - There is no arbitrary-path or arbitrary-JSON write escape hatch.

8. **Readback and reconciliation**
   - Provider acceptance is not final truth.
   - Re-read the affected Metrc resource and reconcile the canonical DoobieLogic state to the confirmed provider state.
   - Unknown/ambiguous outcomes enter `reconciliation_required` and must not be blindly retried.

## Runtime status model

The integration/runtime UI should distinguish:

- `connected`: provider authentication and facility discovery succeeded.
- `syncing`: an authorized resource is currently hydrating.
- `healthy`: authorized resource read succeeded, including valid empty `0 records` responses.
- `not_available_for_license`: the selected license does not expose the resource/action.
- `permission_required`: the resource exists for this license type but the connected user lacks permission.
- `degraded`: transient provider/network/rate-limit issue.
- `failed`: malformed request, broken mapping, invalid contract, or other unexpected integration error.
- `reconciliation_required`: a write may have reached the provider but final state is not yet confirmed.

Expected license boundaries must not be presented to operators as red integration failures.

## Operator UX contract

The Metrc setup experience is a first-class **Regulatory Connection**, not a "future provider" feature.

Normal operators should see a concise summary:

- Metrc Sandbox / Production environment
- connection status
- discovered and mapped facilities
- selected/current facility and license type
- last successful sync
- modules populated
- capability summary
- reconciliation/discrepancy count

Raw resource diagnostics, HTTP status, cursor details, and retry controls belong under an Advanced / Diagnostics view.

Once connected, the integration should largely disappear from day-to-day work. The user opens Inventory, Cultivation, Post Harvest, Receiving, Production, Wholesale, Sales, or Compliance and sees the Metrc-backed state already normalized into that module.

## Discrepancy policy

When a regulated local expectation differs from Metrc:

- show both values
- identify Metrc as the authoritative regulatory value
- do not silently overwrite the provider
- create an auditable discrepancy/reconciliation record
- require a permitted corrective workflow when a provider write is needed

## Rollout sequence

1. Complete permission/capability discovery per facility/license.
2. Finish canonical hydration coverage for all readable Metrc resources.
3. Surface module hydration health and discrepancies.
4. Promote write contracts one workflow family at a time in the MA sandbox.
5. For every promoted write: local command -> validated provider write -> provider readback -> reconciliation -> audit evidence.
6. Use the Metrc Generic Evaluation as proof of real operator workflows rather than one-off evaluation-only code.

## Non-negotiable engineering guardrails

- Tenant/facility/license/environment scope on every provider read and write.
- Provider credentials encrypted server-side; never returned to the browser.
- No provider secret values in logs or evidence artifacts.
- Idempotent ingestion and durable provider identity mapping.
- No silent local override of Metrc-authoritative state.
- No blind retry after an uncertain write.
- No unsupported endpoint invention.
- No write contract promoted without sandbox evidence and readback verification.
- Evaluation tasks are not marked passed until executed and evidenced in the actual sandbox.
