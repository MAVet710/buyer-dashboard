import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import { intelligenceScope } from "./cultivationIntelligenceTypes";
import { networkBase as BASE, type NetworkStatus, type NetworkPreview, type NetworkDeviceChoice, type NetworkConnection } from "./cultivationNetworkTypes";
import { NetworkDeviceReview } from "./NetworkDeviceReview";
import "./cultivation-networks.css";

export function CultivationNetworkSetup() { return <Setup key={JSON.stringify(intelligenceScope())} />; }
function Setup() {
  const client = useQueryClient();
  const scope = JSON.stringify(intelligenceScope());
  const mounted = useRef(false);
  const [adapter, setAdapter] = useState("aranet_cloud");
  const [deployment, setDeployment] = useState("ttn");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selection, setSelection] = useState<{ connection: string; preview: string } | null>(null);
  const here = () => mounted.current && scope === JSON.stringify(intelligenceScope());
  const status = useQuery({ queryKey: ["cultivation-networks", scope], queryFn: ({ signal }) => apiGet<NetworkStatus>(BASE, signal), retry: false, refetchInterval: 5000, refetchIntervalInBackground: false });
  const preview = useQuery({ queryKey: ["cultivation-network-preview", scope, selection?.connection, selection?.preview],
    queryFn: ({ signal }) => apiGet<NetworkPreview>(`${BASE}/${selection!.connection}/previews/${selection!.preview}`, signal),
    enabled: Boolean(selection), retry: false, refetchInterval: query => ["connecting", "listening"].includes(query.state.data?.state || "connecting") ? 3000 : false, refetchIntervalInBackground: false });
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; for (const key of ["cultivation-networks", "cultivation-network-preview"]) { void client.cancelQueries({ queryKey: [key, scope] }); client.removeQueries({ queryKey: [key, scope] }); } };
  }, [client, scope]);
  function refresh() { if (here()) { void client.invalidateQueries({ queryKey: ["cultivation-networks", scope] }); void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] }); } }
  async function discover(identity: string) {
    setBusy(true); setError(""); setMessage(""); setSelection(null);
    try { const result = await apiPost<{ id: string }>(`${BASE}/${identity}/discover`, {}); if (here()) setSelection({ connection: identity, preview: result.id }); }
    catch { if (here()) setError("Discovery was not confirmed. Check the saved key, host support and this account's read permissions."); }
    finally { if (here()) { setBusy(false); refresh(); } }
  }
  async function create(form: HTMLFormElement) {
    const fields = new FormData(form);
    let key = String(fields.get("api_key") || "");
    const options = adapter === "aranet_cloud" ? {} : { deployment, region: String(fields.get("region")), application_id: String(fields.get("application_id")), ...(deployment === "tti" ? { tenant: String(fields.get("tenant")) } : {}) };
    const payload = { adapter, label: String(fields.get("label")), options, api_key: key };
    form.reset(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiPost<{ id: string }>(BASE + "/connections", payload);
      payload.api_key = ""; key = "";
      if (here()) { refresh(); await discover(result.id); }
    } catch { if (here()) setError("The connection was not saved. Review the provider and account settings. Your key is not retained in this form."); }
    finally { payload.api_key = ""; key = ""; if (here()) setBusy(false); }
  }
  async function approve(devices: NetworkDeviceChoice[]) {
    if (!selection) return;
    setBusy(true); setError("");
    try {
      await apiPost(`${BASE}/${selection.connection}/approve`, { preview_id: selection.preview, devices, confirmed: true });
      if (here()) { setSelection(null); setMessage("Sensors linked. Collection will be confirmed after a new reading is saved."); refresh(); }
    } catch { if (here()) setError("The selection was not applied. Check the source units and rooms, or refresh discovery if the connection changed."); }
    finally { if (here()) setBusy(false); }
  }
  async function replaceKey(connection: NetworkConnection, form: HTMLFormElement) {
    const payload = { version: connection.version, api_key: String(new FormData(form).get("replacement_key") || "") };
    form.reset(); setBusy(true); setError("");
    try { await apiPost(`${BASE}/${connection.id}/credential`, payload); payload.api_key = "";
      if (here()) { setSelection(null); setMessage("Replacement key saved. Collection is paused until you find and confirm the sensors again."); refresh(); }
    } catch { if (here()) setError("The key replacement was not confirmed. Refresh this connection before retrying."); }
    finally { payload.api_key = ""; if (here()) setBusy(false); }
  }
  async function setActive(connection: NetworkConnection) {
    setBusy(true); setError("");
    try { await apiPost(`${BASE}/${connection.id}/active`, { version: connection.version, enabled: !connection.enabled }); if (here()) { setSelection(null); refresh(); } }
    catch { if (here()) setError("Collection was not changed. Refresh the connection before retrying."); }
    finally { if (here()) setBusy(false); }
  }
  const data = status.data;
  return <section className="cultivation-network-setup" aria-label="Sensor network setup"><h3>Connect your existing sensor network</h3>
    <p>Use your Aranet Cloud account or supported The Things Stack application. Select the sensors, confirm their rooms and keep the original equipment in control.</p>
    {status.isPending && <p>Checking this facility's collection host...</p>}
    {status.isError && <p>Network setup is currently unavailable. Existing radio and file connections are unchanged.</p>}
    {data && !status.isError && <>
      {!data.host_ready && <p>A facility administrator must enable network collection on the DoobieLogic host before connecting an account.</p>}
      {data.host_ready && !data.can_manage && <p>Read only. An administrator must connect or change sensor networks.</p>}
      {data.can_manage && <form onSubmit={event => { event.preventDefault(); void create(event.currentTarget); }} aria-label="Connect sensor account"><fieldset disabled={busy}>
        <label>System<select value={adapter} onChange={event => { setAdapter(event.target.value); setSelection(null); }}><option value="aranet_cloud">Aranet Cloud</option><option value="things_stack" disabled={data.mqtt_available === false}>The Things Stack / The Things Network</option></select></label>
        <label>Connection name<input name="label" required maxLength={100} placeholder="Flower rooms" /></label>
        {adapter === "things_stack" && <><label>Network<select value={deployment} onChange={event => setDeployment(event.target.value)}><option value="ttn">The Things Network</option><option value="tti">The Things Stack Cloud</option></select></label>
          {deployment === "tti" && <label>Cloud tenant<input name="tenant" required pattern="[a-z0-9-]{3,36}" placeholder="Your existing tenant name" /></label>}
          <label>Region<select name="region" defaultValue="nam1"><option value="nam1">North America</option><option value="eu1">Europe</option><option value="au1">Australia</option></select></label>
          <label>Existing application ID<input name="application_id" required pattern="[a-z0-9-]{3,36}" placeholder="Your sensor application" /></label>
          <p>Use an existing application key with read access to its device list and uplinks. Devices must supply supported standardized measurements; no decoder is installed or changed by DoobieLogic.</p></>}
        {adapter === "aranet_cloud" && <p>Your Aranet key grants access to one existing workspace. Measurements and units are verified against that account's metadata.</p>}
        <label>Customer-owned API key<input type="password" name="api_key" autoComplete="off" required minLength={16} maxLength={1024} /></label>
        <label><input type="checkbox" required />I authorize DoobieLogic to read this account's sensor data. Do not control equipment.</label>
        <button className="primary" type="submit">Connect account and find sensors</button>
      </fieldset></form>}
      {selection && data.can_manage && <section aria-label="Discovered network sensors">{preview.isPending && <p>Finding your sensors...</p>}{preview.isError && <p role="alert">This preview expired or the connection changed. Start discovery again.</p>}
        {preview.data?.state === "connecting" && <p>Verifying the account and retrieving its devices...</p>}
        {preview.data?.state === "failed" && <p role="alert">The account or data stream could not be verified. Check its permissions and setup before retrying.</p>}
        {preview.data && ["complete", "listening"].includes(preview.data.state) && <NetworkDeviceReview key={preview.data.id} preview={preview.data} busy={busy} onApprove={choices => void approve(choices)} />}
      </section>}
      <h4>Saved network connections</h4>{!data.connections.length && <p>No sensor network accounts are connected yet.</p>}
      {data.connections.map(connection => <article className="network-device" key={connection.id}><h5>{connection.label}</h5><p>{connection.status.replaceAll("_", " ")} | {connection.device_count} selected sensor(s)</p>
        <p>Last provider contact: {connection.last_contact_at || "Not recorded"}. Last saved reading: {connection.last_observed_at || "Not recorded"}.</p>
        {Boolean((connection.dropped_readings || 0) + (connection.dropped_messages || 0)) && <p>Some messages could not be retained. Coverage is incomplete; do not assume an uninterrupted history.</p>}
        {data.can_manage && <><details><summary>Reconnect with a replacement key</summary><p>Replacing a key pauses collection. Existing measurements and room mappings are preserved.</p><form onSubmit={event => { event.preventDefault(); void replaceKey(connection, event.currentTarget); }}><label>Replacement customer API key<input name="replacement_key" type="password" autoComplete="off" minLength={16} maxLength={1024} required disabled={busy} /></label><button type="submit" className="secondary" disabled={busy}>Replace key and pause collection</button></form></details><button type="button" className="secondary" disabled={busy} onClick={() => void discover(connection.id)}>Find or review sensors</button><button type="button" className="secondary" disabled={busy || (!connection.enabled && !connection.device_count)} onClick={() => void setActive(connection)}>{connection.enabled ? "Pause collection" : "Resume approved collection"}</button></>}
      </article>)}
      <p>Read-only collection uses the facility's DoobieLogic host and finite local storage. These paths do not guarantee replay of readings missed while disconnected. A working account does not prove that every sensor is reporting.</p>
    </>}{busy && <p role="status">Working on the connection...</p>}{message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
