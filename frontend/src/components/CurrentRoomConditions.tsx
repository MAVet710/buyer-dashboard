import { metricLabel, textValue, type EdgeLatest, type LatestReading } from "./cultivationIntelligenceTypes";

function group(metric: string) {
  if (/^(substrate_|root_|soil_)/.test(metric) || ["ec", "ph", "water_content", "dryback_pct"].includes(metric)) return "Root zone";
  if (/^(irrigation_|feed_|flow|water_|runoff_|drain_)/.test(metric) || metric === "tank_level") return "Irrigation";
  if (["temperature", "relative_humidity", "vpd", "co2", "ppfd", "dli", "hvac_state", "dehumidifier_state", "light_output_pct", "co2_state", "leaf_temperature"].includes(metric)) return "Environment";
  return "Other measurements";
}
function Reading({ reading }: { reading: LatestReading }) {
  const snap = reading.snapshot;
  const usable = reading.state === "ready" && reading.freshness === "fresh" && ["in_target", "above", "below", "unconfigured"].includes(reading.status) && typeof reading.value === "number" && Number.isFinite(reading.value);
  const configured = snap.recipe_revision != null && (snap.target_min != null || snap.target_max != null);
  const label = !usable ? reading.status === "stale" ? "Stale source. Current value unknown." : "Current value unavailable." : !configured || reading.status === "unconfigured" ? "Target unknown" : reading.status === "in_target" ? "Within recorded target" : reading.status === "above" ? "Above recorded target" : "Below recorded target";
  return <article className="ci-reading"><h6>{metricLabel(reading.metric)}</h6><p className="ci-reading-value">{usable ? `${reading.value} ${reading.unit || ""}` : "Unknown"}</p><p>{label}</p><p>Source: {reading.source_device_id} / {reading.source_channel}</p>
    <details><summary>Reading details</summary><p>Observed: {textValue(reading.observed_at)}. Received locally: {reading.received_at}.</p><p>Age: {textValue(reading.data_age_seconds)} seconds. Receipt latency: {textValue(reading.latency_seconds)} seconds.</p><p>State: {reading.state}. Freshness: {reading.freshness}. Status: {reading.status}.</p>{usable && <p>Original: {textValue(reading.original_value)} {textValue(reading.original_unit, "")}</p>}<p>Connection: {reading.connection_id}. Device: {reading.device_id}. Sensor: {reading.sensor_id}. Mapping revision: {snap.mapping_revision}. Zone: {textValue(snap.zone_id, "No zone assigned")}. Stage: {textValue(snap.stage_id)}.</p><p>Mapping interval: {snap.effective_from} to {snap.effective_to}. Recipe revision: {textValue(snap.recipe_revision)}.</p>{configured && <p>Recorded target: {textValue(snap.target_min, "No minimum")} to {textValue(snap.target_max, "no maximum")} {reading.unit}.</p>}<p>Continuous deviation threshold: {snap.threshold_seconds == null ? "not configured" : `${snap.threshold_seconds} seconds`}. A current value alone does not establish a duration-qualified alarm.</p></details>
  </article>;
}
export function CurrentRoomConditions({ latest, roomId }: { latest?: EdgeLatest | null; roomId: string }) {
  const readings = (latest?.readings || []).filter(reading => reading.snapshot.room_id === roomId);
  return <section aria-label="Latest sensor readings"><h4>Latest sensor readings</h4><p>Imported sensor evidence, independent of manual observations and historical aggregates. Room condition and missing coverage remain unknown.</p>{!readings.length ? <p>No mapped sensor readings yet.</p> : <><p>As of {latest?.as_of}. Each source is assessed separately.</p>{["Environment", "Root zone", "Irrigation", "Other measurements"].map(name => { const items = readings.filter(reading => group(reading.metric) === name); return items.length ? <div key={name}><h5>{name}</h5><div className="ci-cards">{items.map((reading, index) => <Reading key={`${reading.connection_id}:${reading.sensor_id}:${reading.source_channel}:${index}`} reading={reading} />)}</div></div> : null; })}</>}{latest?.truncated && <p role="status">Sensor evidence is incomplete. Additional streams may be missing.</p>}</section>;
}
