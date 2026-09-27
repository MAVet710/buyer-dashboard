import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import { intelligenceScope, metricLabel, type Room, type Zone } from "./cultivationIntelligenceTypes";
import type { RadioCandidate, RadioConnection, RadioScan, RadioStatus } from "./cultivationRadioTypes";
import "./cultivation-radio.css";

const BASE = "/api/v1/cultivation-radio";
const stateLabel = (state: string) => ({
  awaiting_reading: "Linked. Waiting for a new reading", receiving: "Receiving readings",
  needs_review: "Linked. Readings need review", disabled: "Collection disabled", disconnected: "Disconnected", stale: "No recent readings",
  receiver_unavailable: "Receiver unavailable", storage_or_mapping_unavailable: "Collection paused. Check storage or mapping",
}[state] || "Status unavailable");
const reasonLabel = (reason: string | null) => ({
  encrypted_requires_supported_pairing: "Encrypted sensor. A supported pairing method is required.",
  unsupported_bthome_object: "This sensor sends a measurement format we have not verified yet.",
  unsupported_bthome_version: "This broadcast version is not supported yet.",
  trigger_only_not_continuous_sensor: "Event-only sensor. Not a continuous environmental source.",
}[reason || ""] || "This device cannot be linked with the available decoder.");

export function CultivationRadioSetup({ rooms }: { rooms: Room[] }) {
  return <RadioSetup key={JSON.stringify(intelligenceScope())} rooms={rooms} />;
}

function RadioSetup({ rooms }: { rooms: Room[] }) {
  const client = useQueryClient();
  const scope = JSON.stringify(intelligenceScope());
  const activeScope = useRef(scope);
  const mounted = useRef(false);
  const currentScan = useRef<string | null>(null);
  const [receiver, setReceiver] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [scanId, setScanId] = useState<string | null>(null);
  const [selected, setSelected] = useState<RadioCandidate | null>(null);
  const [roomId, setRoomId] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [name, setName] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const status = useQuery({ queryKey: ["cultivation-radio", scope, "status"],
    queryFn: ({ signal }) => apiGet<RadioStatus>(BASE + "/status", signal), retry: false });
  const enabled = status.data?.host_matches === true;
  const canManage = status.data?.can_manage === true;
  const links = useQuery({ queryKey: ["cultivation-radio", scope, "connections"],
    queryFn: ({ signal }) => apiGet<{ connections: RadioConnection[]; truncated: boolean }>(BASE + "/connections", signal),
    enabled, retry: false, refetchInterval: enabled ? 10_000 : false, refetchIntervalInBackground: false });
  const scan = useQuery({ queryKey: ["cultivation-radio", scope, "scan", scanId],
    queryFn: ({ signal }) => apiGet<RadioScan>(BASE + "/scans/" + scanId, signal),
    enabled: Boolean(scanId) && canManage, retry: false,
    refetchInterval: query => ["starting", "scanning"].includes(query.state.data?.state || "starting") && !query.state.error ? 2000 : false,
    refetchIntervalInBackground: false });
  const zones = useQuery({ queryKey: ["cultivation-radio", scope, "zones", roomId],
    queryFn: ({ signal }) => apiGet<{ zones: Zone[] }>(`/api/v1/cultivation-intelligence/rooms/${encodeURIComponent(roomId)}/zones`, signal),
    enabled: Boolean(roomId) && Boolean(selected), retry: false });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      void client.cancelQueries({ queryKey: ["cultivation-radio", scope] });
      client.removeQueries({ queryKey: ["cultivation-radio", scope] });
      if (currentScan.current && scope === JSON.stringify(intelligenceScope())) {
        void apiPost(BASE + "/scans/" + currentScan.current + "/stop", {}).catch(() => undefined);
      }
    };
  }, [client, scope]);
  const stillHere = () => mounted.current && activeScope.current === JSON.stringify(intelligenceScope());
  const scanning = Boolean(scanId) && ["starting", "scanning"].includes(scan.data?.state || "starting") && !scan.error;
  const chosenReceiver = receiver || status.data?.receivers[0]?.id || "";
  async function start() {
    if (!authorized || !canManage || !chosenReceiver) return;
    setBusy(true); setError(""); setSelected(null); setConfirmed(false); setMessage("");
    try {
      const next = await apiPost<RadioScan>(BASE + "/scans", { receiver_id: chosenReceiver, authorized: true });
      if (!stillHere()) return;
      currentScan.current = next.id;
      client.setQueryData(["cultivation-radio", scope, "scan", next.id], next);
      setScanId(next.id);
    } catch { if (stillHere()) setError("The scan could not start. Check that this facility's receiver is available, then try again."); }
    finally { if (stillHere()) setBusy(false); }
  }
  async function stop() {
    if (!scanId) return;
    setBusy(true);
    try {
      const next = await apiPost<RadioScan>(BASE + "/scans/" + scanId + "/stop", {});
      if (stillHere()) client.setQueryData(["cultivation-radio", scope, "scan", scanId], next);
    } catch { if (stillHere()) setError("Could not confirm the stop. The discovery window expires automatically."); }
    finally { if (stillHere()) setBusy(false); }
  }
  async function connect() {
    if (!selected || !scanId || !roomId || !confirmed || !canManage) return;
    setBusy(true); setError("");
    try {
      await apiPost<RadioConnection>(BASE + "/connections", { scan_id: scanId, candidate_id: selected.id,
        room_id: roomId, zone_id: zoneId || null, display_name: name, ownership_confirmed: true });
      if (!stillHere()) return;
      setSelected(null); setConfirmed(false); setMessage("Device linked. We'll show receiving only after a new reading is saved.");
      void client.invalidateQueries({ queryKey: ["cultivation-radio", scope, "connections"] });
      void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] });
    } catch { if (stillHere()) setError("Linking was not confirmed. Refresh linked devices before retrying. An expired preview needs a new scan."); }
    finally { if (stillHere()) setBusy(false); }
  }
  async function disconnect(link: RadioConnection) {
    setBusy(true); setError("");
    try {
      await apiPost(BASE + "/connections/" + link.id + "/disconnect", { version: link.version });
      if (stillHere()) void client.invalidateQueries({ queryKey: ["cultivation-radio", scope, "connections"] });
    } catch { if (stillHere()) setError("Disconnect was not confirmed. Refresh the device before trying again."); }
    finally { if (stillHere()) setBusy(false); }
  }
  return <section className="radio-setup" aria-label="Nearby cultivation sensors"><h3>Find nearby sensors</h3>
    <p>Choose your sensor, confirm its room, and let DoobieLogic read its supported broadcasts. Your equipment stays in control.</p>
    {status.isPending && <p role="status">Checking this facility's receiver...</p>}
    {status.isError && <p role="alert">Receiver status is unavailable. Existing file and push connections are unchanged.</p>}
    {status.data && !enabled && <p>This facility does not have a configured local radio receiver. Discovery runs at the facility PC, not your phone or a remote office.</p>}
    {enabled && <><p>Listening location: this facility's configured DoobieLogic PC. Encrypted or unsupported broadcasts cannot be connected here.</p>
      {!canManage && <p>Read only. A connection administrator can find and link equipment.</p>}
      {canManage && <><div className="radio-scan-controls">{status.data!.receivers.length > 1 && <label>Receiver<select value={chosenReceiver} onChange={event => setReceiver(event.target.value)} disabled={scanning || busy}>{status.data!.receivers.map(item => <option key={item.id} value={item.id}>{item.band_label}</option>)}</select></label>}
        {status.data!.receivers.length === 1 && <p>Receiver: {status.data!.receivers[0].band_label}</p>}
        <label><input type="checkbox" checked={authorized} onChange={event => setAuthorized(event.target.checked)} disabled={busy || scanning} />I am authorized to identify sensors at this facility.</label>
        <button type="button" className="primary" onClick={() => void start()} disabled={!authorized || !chosenReceiver || busy || scanning}>Find sensors</button>
        {scanning && <button type="button" className="secondary" onClick={() => void stop()} disabled={busy}>Stop search</button>}</div>
        {scanning && <p role="status">Listening for up to {status.data!.receivers.find(item => item.id === chosenReceiver)?.kind === "rtl433" ? 90 : 15} seconds...</p>}
        {(scan.isError || scan.data?.state === "failed") && <p role="alert">The receiver could not complete this search. Check Bluetooth or the configured radio receiver and try again.</p>}
        {scan.data?.state === "complete" && !scan.data.devices.length && <p>No supported sensor broadcasts were found. Make sure your sensor is awake and near the facility receiver. A shared frequency does not guarantee compatibility.</p>}
        {scan.data?.truncated && <p>There are more nearby devices than this bounded search can show.</p>}
        <div className="radio-candidates">{!scan.isError && scan.data?.devices.map(device => <article key={device.id} className="radio-device"><h4>{device.name}</h4><p>Device ending {device.device_hint}. {device.rssi_dbm !== null ? `Signal ${device.rssi_dbm} dBm.` : "Signal strength unavailable."}</p>
          {device.supported ? <><p>{device.measurements.map(m => `${metricLabel(m.metric)}: ${m.value} ${m.unit}`).join(", ")}</p><button type="button" className="secondary" disabled={busy} onClick={() => { setSelected(device); setName(device.name.slice(0,64)); setConfirmed(false); setRoomId(""); setZoneId(""); setMessage(""); }}>Select {device.name}</button></> : <p>{reasonLabel(device.reason)}</p>}</article>)}</div>
        {selected && <form className="radio-link-form" onSubmit={event => { event.preventDefault(); void connect(); }}><h4>Link {selected.name}</h4><fieldset disabled={busy}><label>Device name<input required maxLength={64} value={name} onChange={event => setName(event.target.value)} /></label>
          <label>Room<select required value={roomId} onChange={event => { setRoomId(event.target.value); setZoneId(""); }}><option value="">Choose a room</option>{rooms.filter(room => room.active).map(room => <option key={room.id} value={room.id}>{room.display_name || room.room_code}</option>)}</select></label>
          {roomId && <label>Zone (optional)<select value={zoneId} onChange={event => setZoneId(event.target.value)} disabled={zones.isPending || zones.isError}><option value="">No zone assigned</option>{zones.data?.zones.filter(zone => zone.active).map(zone => <option key={zone.id} value={zone.id}>{zone.display_name || zone.zone_code}</option>)}</select></label>}
          {zones.isError && <p role="alert">Room zones could not be loaded. Refresh before linking.</p>}
          <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />This is my facility's sensor and I authorize read-only collection.</label>
          <p>Names and signal strength are not proof of identity. Compare this sample with your sensor or controller before confirming.</p>
          <button className="primary" disabled={!roomId || !confirmed || busy || zones.isError}>Connect sensor</button><button type="button" className="secondary" onClick={() => setSelected(null)}>Cancel</button></fieldset></form>}
      </>}
      <h4>Linked sensors</h4>{links.isPending && <p>Loading linked sensors...</p>}{links.isError && <p role="alert">Linked-device status is unavailable. Do not assume collection is healthy.</p>}
      {!links.isError && links.data?.connections.length === 0 && <p>No radio sensors are linked yet.</p>}
      {!links.isError && links.data?.connections.map(link => <article key={link.id} className="radio-device"><h4>{link.name}</h4><p>{stateLabel(link.status)}</p><p>{link.last_received_at ? `Last saved reception: ${link.last_received_at}` : "No saved reception confirmed in this session."}</p><a className="secondary" href={link.return_route}>Open Room 360</a>{canManage && link.status !== "disconnected" && <details><summary>Disconnect sensor</summary><p>Stop new collection and preserve existing evidence.</p><button type="button" className="secondary" disabled={busy} onClick={() => void disconnect(link)}>Confirm disconnect {link.name}</button></details>}</article>)}
      {links.data?.truncated && <p>Linked sensor list is incomplete. Review host capacity.</p>}
      <p className="radio-note">Times reflect reception at the facility PC. Broadcast identities are not cryptographically verified. Missed radio transmissions cannot be recovered automatically.</p>
    </>}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
