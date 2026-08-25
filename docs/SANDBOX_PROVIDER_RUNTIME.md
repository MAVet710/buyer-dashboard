# DoobieLogic Sandbox Provider Runtime

DoobieLogic uses the sandbox provider runtime to prove integration behavior before any provider is allowed to use production credentials or write to a production system.

## Current safety boundary

The developer connection surface supports isolated facility-scoped records for METRC, Dutchie, BioTrack and QuickBooks. Secrets are encrypted by the existing integration credential service and are never returned to the browser. Sandbox and production provider IDs are separate. The sandbox API advertises `production_writes_enabled: false`, and the existing traceability processor continues to reject external provider writes from the DEV Sandbox.

The current provider transport is a deterministic sandbox fixture. It does **not** claim that DoobieLogic has authenticated to a vendor API. This mode exists so the application can exercise the same durable integration mechanics now while real vendor sandbox credentials, OAuth grants and endpoint access are obtained later.

## Step 1 — connection isolation

Each sandbox provider has a dedicated credential record scoped to the active organization and facility. The connection key includes the organization ID, facility ID and sandbox environment. Production credentials are not accepted by this surface.

## Step 2 — provider-neutral adapter contract

`modules/integrations/sandbox_runtime.py` defines one read contract for sandbox providers. Every adapter declares supported resources, produces raw provider records and normalizes them into provider-neutral staging records. METRC, Dutchie, BioTrack and QuickBooks use the same runtime lifecycle.

## Step 3 — sandbox adapters

The initial adapters expose these rehearsal feeds:

- METRC: packages, transfers, items
- Dutchie: sales, inventory, catalog
- BioTrack: inventory, transfers, plants
- QuickBooks: invoices, payments, items

The deterministic fixture transport produces stable IDs from the active tenant scope so the same facility receives repeatable sandbox data without external network dependencies.

## Step 4 — raw record preservation and cursors

Every accepted provider record is stored in `integration_sync_records` with the provider, resource, run ID, external ID, raw payload, normalized payload, fingerprint and receipt time. `integration_sync_states` stores one durable cursor and health state per facility/provider/resource.

## Step 5 — normalization

Adapters normalize provider payloads before downstream use. Dutchie sales already expose a canonical sale shape with source record ID, timestamp, SKU, product name, quantity and net sales. Other provider resources retain normalized metadata and sanitized provider payloads until their final materializers are enabled.

## Step 6 — dedupe and safe retry

A SHA-256 fingerprint is unique within organization, facility, provider and resource. Replaying the same sandbox feed therefore counts duplicates instead of creating duplicate durable records. Failed resource states can be retried independently. Every run is recorded in `integration_sync_attempts` with cursor-before/cursor-after and accepted, duplicate and error counts.

## Step 7 — reconciliation and operator visibility

Developer Connections exposes runtime status for each provider, supported resources, current cursor, records seen/written, latest failures, a **Run sandbox sync** control and **Retry failed syncs** control. The APIs are:

- `GET /api/v1/integrations/sandbox/{provider}/runtime`
- `POST /api/v1/integrations/sandbox/{provider}/sync`
- `POST /api/v1/integrations/sandbox/{provider}/retry`

The separate traceability transaction/reconciliation ledger remains the authority for state-system write workflows. Sandbox sync does not bypass it.

## Step 8 — production cutover gate

A sandbox provider can move from deterministic fixture transport to authenticated vendor sandbox transport only after its adapter has contract tests for authentication, pagination/cursors, normalization, retries, rate limits and reconciliation. Moving from vendor sandbox to production requires a separate provider-by-provider production configuration and an explicit production enablement decision. Sandbox credentials must never be reused as production credential rows.

Before production enablement for any provider, verify all of the following:

1. authenticated vendor sandbox handshake succeeds;
2. read endpoints and pagination/cursors are proven against vendor sandbox data;
3. raw and normalized records are tenant-isolated and credential-redacted;
4. repeated syncs are idempotent;
5. transient failures retry safely and ambiguous results enter reconciliation;
6. external writes, if applicable, use the existing approval/idempotency framework;
7. provider-specific contract tests and full CI are green;
8. production credentials and production-write enablement are introduced as a separate reviewed change.

Until those conditions are met, the runtime remains sandbox-only and external production writes remain disabled.
