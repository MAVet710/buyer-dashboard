import { useState, type FormEvent } from "react";
import { useIntelligence } from "./cultivationIntelligenceQueries";
import { ZoneSelect } from "./CultivationIntelligenceShared";
import type { Room, RegistryMetric, Workspace } from "./cultivationIntelligenceTypes";
import type { NetworkDevice, NetworkPreview, NetworkDeviceChoice } from "./cultivationNetworkTypes";

function Device({ device, index, rooms, metrics }: { device: NetworkDevice; index: number; rooms: Room[]; metrics: RegistryMetric[] }) {
  const [selected, setSelected] = useState(false);
  const [room, setRoom] = useState("");
  return <article className="network-device"><h5>{device.name}</h5><p>Source: {device.id}</p>
    <label><input type="checkbox" name={`selected-${index}`} checked={selected} disabled={!device.streams.some(stream => stream.unit && stream.sample_value !== null)} onChange={event => setSelected(event.target.checked)} />Connect this sensor</label>
    {!device.streams.length && <p>Waiting for a supported measurement. A listed device is not yet a working data feed.</p>}
    <fieldset disabled={!selected}>
      <label>DoobieLogic room<select name={`room-${index}`} required={selected} value={room} onChange={event => setRoom(event.target.value)}><option value="">Choose the room</option>{rooms.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.display_name || item.room_code}</option>)}</select></label>
      <ZoneSelect roomId={room} name={`zone-${index}`} />
      {device.streams.map((stream, streamIndex) => <section key={stream.source_channel} className="network-measurement"><p>{stream.label}: <strong>{stream.sample_value ?? "Unknown"} {stream.source_unit_label || "unit unknown"}</strong></p><p>Observed: {stream.sample_at || "Not available"}</p>
        <label>Use as<select name={`metric-${index}-${streamIndex}`} defaultValue={stream.suggested_metric || ""} disabled={!stream.unit || stream.sample_value === null}><option value="">Do not collect this measurement</option>{metrics.map(metric => <option key={metric.metric} value={metric.metric}>{metric.display_name || metric.metric.replaceAll("_", " ")} ({metric.unit})</option>)}</select></label>
        {!stream.unit && <p>The source unit is not supported yet. It will not be guessed or imported.</p>}
      </section>)}
    </fieldset>
  </article>;
}

export function NetworkDeviceReview({ preview, busy, onApprove }: { preview: NetworkPreview; busy: boolean; onApprove: (choices: NetworkDeviceChoice[]) => void }) {
  const workspace = useIntelligence<Workspace>("/workspace");
  const registry = useIntelligence<{ metrics: RegistryMetric[] }>("/metrics");
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const fields = new FormData(event.currentTarget);
    const choices: NetworkDeviceChoice[] = [];
    preview.devices.forEach((device, index) => {
      if (!fields.has(`selected-${index}`)) return;
      const streams = device.streams.flatMap((stream, streamIndex) => {
        const metric = String(fields.get(`metric-${index}-${streamIndex}`) || "");
        return metric ? [{ source_channel: stream.source_channel, metric }] : [];
      });
      choices.push({ source_id: device.id, room_id: String(fields.get(`room-${index}`) || ""), zone_id: String(fields.get(`zone-${index}`) || "") || null, streams });
    });
    if (!choices.length || choices.some(choice => !choice.room_id || !choice.streams.length)) { setError("Choose at least one sensor, its room and a supported measurement."); return; }
    onApprove(choices);
  }
  if (workspace.isError || registry.isError) return <p role="alert">Room and measurement choices could not be loaded. No devices were linked.</p>;
  if (!workspace.data || !registry.data) return <p>Loading your room choices...</p>;
  return <form onSubmit={submit} aria-label="Confirm network sensor rooms"><h4>Select sensors and confirm their rooms</h4><p>Review the sample and units. Only the selected sensors and measurements will be collected. This replaces this connection's previous selection without deleting its history.</p>
    {preview.state === "listening" && <p>Listening for standardized uplinks, for up to ten minutes. Devices appear before their first measurement; only sensors with supported readings can be connected.</p>}
    {preview.truncated && <p>More than 100 devices were returned. This preview is limited to the first 100.</p>}
    <fieldset disabled={busy}>{preview.devices.map((device, index) => <Device key={device.id} device={device} index={index} rooms={workspace.data!.rooms} metrics={registry.data!.metrics} />)}
      <label><input type="checkbox" required />I authorize read-only collection from these sensors into the rooms shown.</label><button className="primary" type="submit">Connect selected sensors</button>
    </fieldset>{error && <p role="alert">{error}</p>}
  </form>;
}
