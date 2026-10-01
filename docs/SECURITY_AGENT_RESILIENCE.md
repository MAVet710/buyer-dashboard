# Security Agent resilience and perimeter evidence

DoobieLogic Security Guard is a defensive observer and deterministic protection layer. It does not attack external systems, exploit hosts, change firewalls, disable user accounts, or treat an alert as proof of compromise.

## Monitoring incident semantics

Worker failures and dropped counters are lifetime totals for the running process. A monitoring_degraded incident now records only the new failures or drops observed since the previous successfully persisted monitor cycle. Evidence also includes the lifetime totals, the last bounded error category, error time, and saturation state.

The monitor classifies database DNS failures, database connection timeouts, database operational failures, event-observation failures, and other monitor-processing failures without storing connection strings or exception bodies.

After three successful, unsaturated cycles with no newly observed failures or drops, unresolved monitoring-degradation incidents are marked recovered. Recovery is evidence, not deletion. The original incident stays reviewable and its version increases. A new failure can reopen a recovered incident within the same deduplication window.

Security Guard investigations older than the active five-minute signal window move to recovered when no qualifying signal remains.

## Perimeter sources

### Windows Defender

On Windows, the host collector reads metadata only from the existing Microsoft-Windows-Windows Defender/Operational event log. It does not collect event messages, file contents, process memory, quarantine contents, or credentials.

High-signal Defender event IDs create a security incident and enter the deterministic Guard correlation model. Lower-risk configuration events can contribute evidence but do not independently trigger automatic Metrc write protection. An empty event window is healthy and is not treated as collector failure.

### Supabase Auth audit

The collector uses the existing production database connection and performs bounded, read-only queries against auth.audit_log_entries when that table is visible to the runtime role. Raw payload JSON is never persisted by Security Center. Only a bounded action label, deterministic audit identity, timestamp, and pseudonymized source are normalized.

If the table is empty, coverage reports connected_empty. If the runtime role cannot read it, coverage reports the limitation rather than claiming direct-auth visibility.

### Cloudflare

The PC host currently provides Cloudflare Tunnel process liveness only. This is explicitly labeled tunnel_liveness_only. It is not a Cloudflare WAF, Access, or Security Events feed and must not be described as one.

A future Cloudflare security-event adapter requires an authorized API or log source. No credential bypass or scraping is permitted.

## Source isolation

Perimeter collectors run independently from core application monitoring. Defender, Supabase Auth, or Cloudflare source failure cannot take username login, scope, or audit monitoring offline. Each source has durable status, cursor, failure count, last error category, last event time, and sanitized diagnostics in security_source_state.

Browser roles cannot read that table directly. Security Center remains platform-DEV only.

## Alert delivery

A stale encrypted Spacemail password no longer blocks a valid deployment-level Resend transport. When Resend is configured, only non-secret sender metadata is reused from the Spacemail integration row; the legacy mailbox secret is not decrypted.

Ambiguous provider-send outcomes are never automatically replayed. If alert delivery is unavailable, Security Center records a warning incident so the failure is visible even when email itself cannot be sent. The incident recovers when the notifier returns to ready.

A configured API key is still required for native Resend delivery. This change does not fabricate or expose one.

## Containment boundary

A single weak signal does not trigger containment. Defender alerts, direct-auth failures, honey routes, password spraying, scope denials, and other independent evidence can be correlated. Metrc write protection remains deterministic and fail closed when the configured risk threshold is reached.

The local AI analyst is advisory only. It receives bounded summarized state, never request bodies, headers, credentials, raw Defender messages, or raw Supabase Auth payloads.

## Local AI analyst deployment

The Security Guard AI route is local-only and never falls back to a cloud model. On CannaCenter, the existing Ollama OpenAI-compatible loopback endpoint is the intended runtime. `gpt-oss:20b` was verified locally as reachable and capable of a bounded defensive review. The model endpoint must remain loopback-only and is not a public API.

AI review runs independently from the core observer heartbeat. A slow or cold model cannot delay event persistence, heartbeat writes, notifier processing, or deterministic containment. The deterministic Guard remains authoritative; AI output is advisory text attached to an investigation.

The host security configuration may set the local endpoint/model and a bounded timeout. No API key is required for the loopback Ollama instance, no recurring service is added, and cloud fallback remains disabled.
