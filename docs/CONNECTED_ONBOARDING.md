# Connected facility onboarding

This feature joins existing provider credentials, facility mappings, canonical hydration and local telemetry. It does not replace them with another inventory or sensor ledger. Source and test readiness are not a production release claim.

## Metrc operator workflow

Open Integration Wizard and its Connect step. Choose the correct facility environment explicitly. Enter the operator's current Metrc User API Key, find accessible licenses, select the exact license and confirm the local facility link. A missing local facility can be created from the provider's returned identity; an existing exact match is reused. The wizard never accepts an invented provider record from the browser.

Ordinary operators supply only their user key. A platform DEV administrator configures DoobieLogic's integrator key separately for the supported state and environment. The interface clears entered keys before displaying any response; saved values and hints are not loaded into the guided form. A failed discovery or provider authorization is not treated as an expired DoobieLogic login.

Import existing facility records starts a bounded host-side read job and returns immediately. Its progress and provider page checkpoints survive navigation. A process interruption requires an explicit resume; the import does not claim automatic recovery merely because it has a saved key. Repeated imports preserve canonical identities and do not duplicate starting balances. Source conflicts remain review items. Provider-owned historical workflows remain read-only projections rather than fabricated local actions.

The current guided provider contract supports Massachusetts. Sandbox and production credentials, exact license mappings and provider evidence are isolated. A facility already containing evidence from another environment cannot be repurposed silently. Default local sandbox behavior is unchanged.

## Regulatory writes are a separate gate

This release adds explicit production READ onboarding. It does not enable production Metrc writes through the alpha dispatcher or promote unverified operation payloads. Existing approved sandbox operations and their human approval/readback checks remain unchanged. Import never creates, adjusts, destroys or transfers anything in Metrc. No sales, lab-write, POS or delivery subsystem was added.

The goal of minimizing Metrc switching requires operation-by-operation production acceptance and the appropriate customer permissions. Do not describe production write activation as complete based on a successful import. Metrc's own documentation distinguishes the integrator key, individual user key, permissions and idempotent GETs from potentially non-idempotent mutations: https://api-ma.metrc.com/Documentation/

## API and persistence

`/api/v1/integration-wizard/metrc-setup` exposes sanitized connection/readiness and durable import progress. Credentials, facility preview, confirmed link and import are explicit actions. Confirmation re-fetches the licensed facility list and compares its fingerprint, selected environment and credential generation. Linking runs canonical saves inside one relational transaction. A lost response can be retried without creating a second local facility.

The background job is bounded to one import per host. A dedicated short-budget PostgreSQL connection holds a transaction-scoped advisory lock during the import rather than occupying the API's normal small pool. Progress updates use an expected run identity so a superseded worker cannot overwrite a newer run. A stale pending lease is distinguishable from a live worker; no fake success is written on process restart.
