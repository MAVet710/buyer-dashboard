# Cultivation intake operator guide

Implementation handoff, September 26, 2026. This guide does not establish deployment, a connected device, or live acceptance. The machine contract is [CULTIVATION_PUSH_API.md](CULTIVATION_PUSH_API.md); local collection is described in [CULTIVATION_PUSH_EDGE_API.md](CULTIVATION_PUSH_EDGE_API.md).

## Choose an intake method

Open the existing Cultivation connections setup. Choose **File import** for reviewed JSON/CSV evidence or Growlink exports. Choose **Normalized JSON push** only when an authorized first-party producer can supply the published JSON contract. Push supports generic JSON; Growlink remains export only. A threshold webhook or old historical file does not establish continuous sensor coverage.

Create a clearly named connection in the intended organization and facility. Optional delivery expectations accept seconds from the actual producer schedule. Leave them blank when unknown. Connection delivery intervals are not per-sensor cadence, stale crop targets, or deviation thresholds.

Use **Register device** for the source device identity. Open its details to assign the source channel, source measurement and original unit to the canonical measurement. Select its canonical room and optional zone, with an explicit time-effective timestamp. **No zone assigned** means only room attribution is known; it does not mean the sensor represents the whole room. Existing mapping details link to Room 360.

## Authorize one producer

An administrator with the effective connection-management permission opens **Create ingress grant**, supplies a producer label and a future expiry timestamp with timezone, then explicitly selects **Issue one-time credential**. Each grant creates its own bound service-account identity. An existing broad platform account does not silently authorize this connection.

Copy the credential into the producer's protected configuration while it is displayed. If clipboard permission is denied, select and copy it manually. Closing setup, changing connection, changing facility/organization, or losing management capability removes it from the view. It is never returned by the ordinary grant list and is not retained in browser storage or the query/mutation caches. The UI does not store vendor credentials or ask for arbitrary receiver URLs or filesystem paths.

If issuance returns an error or the response is lost, reload the grant list before trying again. A grant may have been created without its one-time credential reaching the browser. Revoke any unused grant before replacing it. Grant revocation requires confirmation and the current grant version. A version conflict requires reloading evidence and reviewing the current record. Revocation blocks later admissions; a bounded admission authorized before revocation may finish. Existing observations and audit evidence remain preserved.

Read-only operators can inspect instructions, grant state, connection evidence and mapping history. They cannot issue or revoke grants, register devices, change mappings or import evidence.

## Deliver and inspect evidence

The read-only integration instructions show the exact connection endpoint, schema fields and published bounds. The initial ceiling is 1 MiB and 500 readings, further restricted by configured host limits. Respect `Retry-After` for rate pressure. A storage or authorization-unavailable response is not a durable receipt. A producer must keep stable observation identities and unchanged payloads when retrying a lost acknowledgement.

Transport, observations and capacity are independent:

- **Awaiting first reading** means no committed push receipt is evidenced, even if file imports exist.
- **Receiving readings** requires an active grant, a committed push receipt within the configured stale interval and a server-reported recent observation. This is connection-level evidence only.
- **Readings are stale** comes from the server observation assessment. Old observations delivered now remain old.
- A mapping backlog can coexist with new receipts. Review pending mappings before treating observations as valid room evidence.
- **Storage limit reached** reports the backend's full state. Review its limiting resource and action. Do not infer hours of remaining capacity without meaningful rates.
- **Connection revoked** and grant expiry/revocation describe authorization, not deletion of historical evidence.
- **Status unavailable** means diagnostics cannot establish the state.

Use Room 360 for individual source freshness and recorded crop context. A newest connection-wide observation cannot establish all sensors' freshness or clear a missing channel. A receipt is not room health or a duration-qualified agronomic alert.

## Local collection and outages

The initial local collector watches operator-approved, finalized normalized files and writes to the existing canonical EdgeStore. It is run locally; the browser does not install a Windows task. The producer must publish complete files atomically. Unmapped evidence may remain pending for authorized mapping review.

Collection requires the collector host and the source feed to keep running. Internet loss and host failure have different consequences. A remote browser cannot claim that an unreachable collector is still collecting without a fresh local heartbeat. Local storage-full conditions stop new persistence. Preserve source backlog and unresolved evidence for recovery.

This workflow does not discover equipment, subscribe to arbitrary MQTT feeds, validate native Growlink signatures, or connect BACnet/Modbus automatically. Those paths require their own reviewed source contracts and explicit implementation.

## Frontend validation and integration status

The focused browser fixture uses real React components with intercepted network responses and the global CSS import order from `main.tsx`, including `popup-surfaces.css`. It is synthetic evidence, not a live API, hardware or public workflow test.

Frontend dependency installation was attempted with `pnpm.cmd install --offline --frozen-lockfile`. The local store lacked `@babel/helper-validator-option@7.29.7`, so installation failed. Lint, TypeScript, Vitest and browser execution require an approved dependency installation before this frontend candidate can pass its gates. No production browser, deployment, commit or push was performed by the frontend worker.

Attempts to invoke the gates through `pnpm.cmd exec` unexpectedly triggered automatic dependency fetching. Network access rejected those requests; all four commands were stopped. None reached test execution. Use direct local executables after dependencies have been provisioned. The intended gates are:

```text
node_modules/.bin/eslint src/components/CultivationConnections.tsx src/components/CurrentRoomConditions.tsx src/components/CultivationPushSetup.tsx src/components/CultivationPushSetup.test.tsx src/components/cultivationIntelligenceTypes.ts e2e/cultivation-push.spec.ts e2e/fixtures/cultivation-push-entry.tsx
node_modules/.bin/tsc -b
node_modules/.bin/vitest run src/components/CultivationPushSetup.test.tsx src/components/CultivationIntelligence.test.tsx
node_modules/.bin/vite --config e2e/fixtures/cultivation-push.config.ts
node_modules/.bin/playwright test --config e2e/fixtures/cultivation-push.playwright.config.ts
```

On Windows, use the `.cmd` executable suffix. Check that port 4195 is unused before starting the isolated fixture server, and stop only that server. No server was started in the blocked run. The fixture cannot establish the required 390/1280 no-overflow or popup appearance acceptance until it executes.

The backend and edge transport argument mismatch observed during implementation was reconciled in the published API document. Final backend/edge integration and authenticated acceptance remain primary-owned. The shared `ZoneSelect` component still contains the legacy option text `Whole room / no zone`; it is outside this worker's file ownership. The assigned connection-history and CurrentRoomConditions fallbacks now say `No zone assigned`. The primary should resolve the shared selector wording before final acceptance.
