# Host runtime and deployment gates

The optional sensor network runtime starts only from an administrator-owned `CULTIVATION_NETWORK_CONFIG` path. Its allowlist identifies existing organization/facility scopes; browser requests cannot add scopes, paths, URLs, MQTT topics, arbitrary decoders or executables. The normal PC production launcher must start it explicitly on 8010 when Uvicorn lifespan is disabled. Shadow8012 must remain read-only and must not seize a collector lease.

The configured host supports at most eight network connections and two concurrent external HTTP jobs. Discovery previews are bounded and expire. Aranet polling defaults to a 60-second interval, with device and response caps. Requests use fixed approved HTTPS hosts, certificate verification, no ambient proxies and no redirects. Provider Retry-After is not shortened. Decrypted credentials exist only where required for the request/subscriber and never in output logs or process arguments.

The Things Stack subscriber uses the separately installed, hash-pinned `requirements-network.txt` package environment. The active API Python environment is not modified. A Windows named mutex prevents duplicate host collection; MQTT child processes belong to a kill-on-close Job. Credentials are provided over bounded stdin only after the Job is assigned. The worker only subscribes, reports ready after broker subscription acknowledgement, and has a bounded startup timeout. Failed subscriptions are not shown as receiving data.

Collection rechecks organization, facility capability, active administrator and effective permission. Approval records exact sensor streams and effective room/zone mapping. Only those approved streams can enter EdgeStore. Values observed before approval are not backfilled from previews. Final persistence checks connection/configuration version, current authorizer, enabled state and encrypted credential generation under the canonical facility lock. Pause, revocation and key replacement stop later collection without deleting prior evidence.

Local raw readings remain in the existing finite EdgeStore; no per-reading Supabase telemetry table or paid queue is introduced. The existing maintenance/aggregation/archive path remains authoritative. Pending in-memory input is bounded; it is not a durable offline broker. A process crash before an EdgeStore commit, QoS0 disconnection, missed Aranet polling interval or storage backpressure may leave gaps. The UI shows data age and drop counters instead of promising uninterrupted history. This first network adapter release does not implement historical gap backfill.

Migration0089 extends three existing check constraints. No tables are renamed and no inventory/lifecycle data is replaced. Downgrade refuses while production-mode or network-configuration evidence uses the new values. Preserve additive schema after user exposure; do not delete configuration or telemetry to force a rollback.

## Acceptance boundaries

The deterministic browser harness uses fresh migrated SQLite, the actual application routers, actual encrypted configuration, canonical materializers and local EdgeStore. Only vendor responses/MQTT capture are synthetic. It demonstrates the operator flow, mapping, saved readings, repeated import, reload and read-only denial at 390px and 1280px. It does not prove access to a customer's Aranet workspace, MQTT application, physical sensor or Metrc production account.

Live acceptance additionally requires customer-owned provider credentials and their permitted device streams. The PC release must separately pass clean source/tree identity, full CI/PostgreSQL gates, shadow read acceptance, stable-controller promotion, signed-in public checks and unchanged scheduled-task verification. A successful fixture or a green PR is not a deployed/live-provider claim.

No new recurring service is required by DoobieLogic. Customers may need an existing paid vendor/API entitlement. No subscription, credit package or physical receiver was purchased for this work.

The discovery request releases its local configuration read before runtime authorization. Runtime capability checks reuse their existing transaction connection. A two-slot, zero-overflow pool regression proves discovery does not request a third connection or hold a request slot while starting the provider read.
