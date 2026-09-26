import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, apiPost } from "../lib/api";
import { ReadState, WriteState } from "./CultivationIntelligenceShared";
import { useIntelligence, useIntelligenceWrite } from "./cultivationIntelligenceQueries";
import { intelligenceBase, intelligenceScope, textValue, type Connection, type IngressGrant, type IngressGrantCreated, type IngressGrants, type PushHealth } from "./cultivationIntelligenceTypes";

export function CultivationPushSetup({ connection, canManage }: { connection: Connection; canManage: boolean }) {
  return <PushSetup key={JSON.stringify([...intelligenceScope(), connection.id, canManage])} connection={connection} canManage={canManage} />;
}

function PushSetup({ connection, canManage }: { connection: Connection; canManage: boolean }) {
  const client = useQueryClient();
  const path = `/connections/${encodeURIComponent(connection.id)}/ingress-grants`;
  const scope = JSON.stringify(intelligenceScope());
  const grants = useIntelligence<IngressGrants>(path);
  const alive = useRef(false);
  const generation = useRef(0);
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const invalidateRequests = useCallback(() => { generation.current++; }, []);
  useEffect(() => { alive.current = true; return () => { alive.current = false; invalidateRequests(); }; }, [invalidateRequests]);
  function close() { generation.current++; setToken(""); setMessage(""); setOpen(false); }
  async function issue(form: HTMLFormElement) {
    const fields = new FormData(form);
    const requestGeneration = ++generation.current;
    setBusy(true); setMessage(""); setToken("");
    try {
      // Deliberately bypass useMutation: the one-time token must never enter its cache.
      const result = await apiPost<IngressGrantCreated>(`${intelligenceBase}${path}`, { version: connection.version, label: fields.get("label"), expires_at: fields.get("expires_at") });
      if (alive.current && requestGeneration === generation.current && scope === JSON.stringify(intelligenceScope())) setToken(result.token);
      if (scope === JSON.stringify(intelligenceScope())) void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] });
    } catch (error) {
      const reason = error instanceof ApiError ? error.status === 409 ? " Connection version changed." : error.status === 429 ? " Rate limit reached. Wait before retrying." : error.status === 503 ? " Status unavailable." : error.status === 422 ? " Check the label and future expiry timestamp with timezone." : "" : "";
      if (alive.current && requestGeneration === generation.current && scope === JSON.stringify(intelligenceScope())) setMessage("Credential creation was not confirmed." + reason + " Reload grants before trying again; a lost response may have created a grant. Revoke any unused grant. A version conflict requires current connection evidence.");
    } finally { if (alive.current) setBusy(false); }
  }
  const active = !connection.revoked_at && connection.status !== "revoked";
  return <section aria-label="Normalized push setup"><h3>Normalized push setup</h3>
    <p>A first-party producer sends normalized JSON to this connection. This does not authorize a native Growlink webhook or discover equipment.</p>
    <details><summary>Integration instructions</summary><p>Register each source device and map its channel, original unit and time-effective room and zone using the forms below. Pending mapping evidence needs review before it can become valid room evidence.</p>
      <p>Send a bearer credential with Content-Type: application/json to:</p><code>{`/api/v1/external/v1/cultivation-telemetry/${encodeURIComponent(connection.id)}/batches`}</code>
      <p>Schema version 1 accepts a batch_id and readings array. Each reading needs event_id, source_device_id, source_channel, source_metric, value, unit and observed_at with a timezone. Optional quality defaults to valid. Preserve stable identities and unchanged payloads when retrying.</p>
      <details><summary>Example normalized payload</summary><p>Synthetic schema example. Replace identities and observation time with actual source evidence.</p><code>{JSON.stringify({ schema_version: 1, batch_id: "batch-001", readings: [{ event_id: "sample-001", source_device_id: "sensor-1", source_channel: "temperature", source_metric: "temperature", value: 24.5, unit: "C", observed_at: "2026-09-26T12:00:00Z", quality: "valid" }] }, null, 2)}</code></details>
      <p>Maximum 1 MiB and 500 readings, further bounded by the host's configured batch limit. Identity fields use ASCII letters, digits or _.:@- and at most 120 characters. Do not send room, facility, organization, receipt timestamps, URLs, credentials or metadata in the payload.</p>
      <p>A committed response confirms local storage, including pending or quarantined evidence. It does not confirm valid or current room conditions. On rate pressure (429), respect Retry-After. Storage or authorization unavailable (503) is not a successful receipt. No fixed requests-per-minute allowance is promised.</p>
      <p>The initial local collector watches finalized normalized files on its host and writes to the canonical local evidence store. It needs a running host and an authorized source producing those files. It does not automatically connect MQTT, Growlink or BACnet. Internet loss and host failure are different: a remote view cannot claim continued collection without a fresh local heartbeat.</p>
    </details>
    <ReadState query={grants}>{data => <><h4>Connection ingress grants</h4>{!data.grants.length && <p>No ingress grants. A platform service account alone does not authorize this connection.</p>}{data.truncated && <p>Grant list is incomplete.</p>}{data.grants.map(grant => <GrantRow key={grant.id} path={path} grant={grant} canManage={canManage && active} />)}</>}</ReadState>
    {canManage && active && <>{!open ? <button className="secondary" onClick={() => setOpen(true)}>Create ingress grant</button> : <div className="ci-stage"><button type="button" className="secondary" onClick={close}>Close credential setup</button>{!token && <form onSubmit={event => { event.preventDefault(); void issue(event.currentTarget); }}><fieldset disabled={busy}><label>Producer label<input name="label" required maxLength={120} /></label><label>Expires at (ISO with timezone)<input name="expires_at" required placeholder="2026-10-26T12:00:00Z" /></label><button className="primary">Issue one-time credential</button></fieldset></form>}{token && <><p>Copy this credential now. It will not be shown again. Closing this setup clears it from this view.</p><label>One-time credential<textarea readOnly value={token} rows={3} /></label><button className="secondary" onClick={async () => { const current = generation.current; try { await navigator.clipboard.writeText(token); if (alive.current && current === generation.current) setMessage("Credential copied."); } catch { if (alive.current && current === generation.current) setMessage("Clipboard access was denied. Select and copy the credential manually before closing."); } }}>Copy credential</button></>}{message && <p role="status">{message}</p>}</div>}</>}
    {message && !token && <button className="secondary" onClick={() => void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] })}>Reload grant and connection evidence</button>}
    {!canManage && <p>Read only. A connection administrator can issue or revoke grants.</p>}
  </section>;
}

function GrantRow({ path, grant, canManage }: { path: string; grant: IngressGrant; canManage: boolean }) {
  const [confirm, setConfirm] = useState<number | null>(null);
  const revoke = useIntelligenceWrite<IngressGrant>(`${path}/${encodeURIComponent(grant.id)}/revoke`, () => setConfirm(null));
  return <article className="ci-stage"><p>{grant.label}: {grant.status}. Expires: {grant.expires_at}.</p><details><summary>Grant identity</summary><p>Grant: {grant.id}. Service account: {grant.service_account_id}. Version: {grant.version}.</p></details>{canManage && !grant.revoked_at && grant.status !== "revoked" && !revoke.isSuccess && <>{confirm === null ? <button className="secondary" onClick={() => setConfirm(grant.version)}>Revoke {grant.label}</button> : <><p>Revoke this grant? Future admissions will be denied. A bounded admission already authorized may finish. Existing evidence is preserved.</p>{confirm !== grant.version && <p>Grant version changed. Cancel and review the current grant before confirming.</p>}<button className="secondary" disabled={revoke.isPending || confirm !== grant.version} onClick={() => revoke.mutate({ version: confirm })}>Confirm grant revocation</button><button className="secondary" disabled={revoke.isPending} onClick={() => setConfirm(null)}>Cancel</button></>}<WriteState error={revoke.error} /></>}</article>;
}

export function ConnectionHealthPanel({ data }: { data: PushHealth }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 15000); return () => window.clearInterval(timer); }, []);
  const edge = data.edge;
  const ingress = data.ingress;
  const receipt = ingress?.last_push_received_at;
  const receiptAge = receipt ? (now - Date.parse(receipt)) / 1000 : NaN;
  const staleAfter = data.connection.stale_after_seconds;
  const observed = data.freshness?.last_valid_observed_at;
  const observationAge = observed ? (now - Date.parse(observed)) / 1000 : NaN;
  const stale = data.freshness?.observation_status === "stale" || (typeof staleAfter === "number" && Number.isFinite(observationAge) && observationAge > staleAfter);
  const receiving = !data.connection.revoked_at && data.connection.status !== "revoked" && !stale && ingress?.grant_state === "active" && ingress.transport_state === "received" && data.freshness?.observation_status === "recent" && typeof staleAfter === "number" && Number.isFinite(receiptAge) && receiptAge >= 0 && receiptAge <= staleAfter;
  return <section aria-label="Connection health"><h3>Connection health</h3>
    {(data.connection.revoked_at || data.connection.status === "revoked") && <p>Connection revoked</p>}
    {!edge || !ingress ? <p>Status unavailable</p> : <>
      <p>Grant state: {ingress.grant_state}. {ingress.grants_truncated && "Grant evidence is incomplete."}</p>
      {ingress.transport_state === "awaiting" && <p>Awaiting first reading</p>}
      {receiving && <p>Receiving readings</p>}
      {stale && <p>Readings are stale</p>}
      {edge.capacity?.state === "full" && <p>Storage limit reached</p>}
      <p>Last committed push: {textValue(receipt)}.</p>
      <p>Current valid observation: {textValue(data.freshness?.last_valid_observed_at)}. Per-sensor cadence, freshness and coverage remain unknown here.</p>
      <p>Expected connection delivery interval: {data.connection.expected_interval_seconds == null ? "Not configured" : data.connection.expected_interval_seconds + " seconds"}. This is not per-sensor cadence.</p>
      {(edge.counts?.pending ?? 0) > 0 && <p>Mapping backlog: {edge.counts?.pending} pending. Oldest pending: {textValue(edge.oldest_pending_at)}. A backlog can coexist with new receipts.</p>}
      <details><summary>Storage and evidence limits</summary><p>Capacity headroom is unknown without meaningful observed rates. No hours of remaining collection are estimated.</p><p>Limiting resource: {textValue(edge.capacity?.limiting_resource)}. Backend action: {textValue(edge.capacity?.action)}.</p><ul>{Object.entries(edge.limits || {}).map(([key, value]) => <li key={key}>{key.replaceAll("_", " ")}: {textValue(value)}</li>)}</ul>{!edge.capacity && <p>Storage capacity status unavailable.</p>}</details>
    </>}
    <p>Transport contact is not room health. Historical imports and old readings received now do not establish a fresh stream. A recent connection-level receipt does not establish every sensor's freshness.</p>
  </section>;
}
