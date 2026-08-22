import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type Settings = { auto_map_products_during_receive: boolean; default_receiving_room: string };
type Context = { organization: { name: string } | null; facility_id: string; facilities: { id: string; name: string }[] };

export function LocationSettingsPage() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["location-settings"], queryFn: ({ signal }) => apiGet<Settings>("/api/v1/location-settings", signal) });
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const [autoMap, setAutoMap] = useState(false);
  const [room, setRoom] = useState("Receiving");
  useEffect(() => { if (settings.data) { setAutoMap(Boolean(settings.data.auto_map_products_during_receive)); setRoom(settings.data.default_receiving_room || "Receiving"); } }, [settings.data]);
  const save = useMutation({
    mutationFn: () => apiPost<Settings>("/api/v1/location-settings", { auto_map_products_during_receive: autoMap, default_receiving_room: room }),
    onSuccess: data => { client.setQueryData(["location-settings"], data); setAutoMap(Boolean(data.auto_map_products_during_receive)); setRoom(data.default_receiving_room || "Receiving"); },
  });
  const facility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  return <div className="page">
    <div className="eyebrow">Data & Settings / Location</div>
    <div className="page-heading"><div><h1>Location settings</h1><p>{context.data?.organization?.name ?? "Organization"} · {facility?.name ?? "Facility"}</p><p>These settings apply only to the selected facility and are stored durably with that facility&apos;s Buyer Dash data.</p></div></div>
    {settings.isLoading ? <div className="state">Loading location settings…</div> : null}
    {settings.isError ? <div className="state error">{settings.error.message}</div> : null}
    {settings.data ? <section className="inventory-panel location-settings-card">
      <h4>Inventory receiving</h4>
      <label className="toggle location-toggle"><input type="checkbox" checked={autoMap} onChange={event => setAutoMap(event.target.checked)}/><span><strong>Auto-map products during receive</strong><small>When enabled, Buyer Dash remembers prior approved incoming-item → Catalog product mappings for this facility and preselects them the next time the same incoming product is received. The receiver can always choose a different Catalog product.</small></span></label>
      <label className="compact-field">Default receiving room<input value={room} placeholder="Receiving" onChange={event => setRoom(event.target.value)}/></label>
      <p className="source-caption">Auto-map never guesses a new catalog relationship. It reuses only mappings that were previously reviewed and posted at this facility.</p>
      <button className="primary submit" type="button" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save location settings"}</button>
      {save.isError ? <div className="state error">{save.error.message}</div> : null}
      {save.isSuccess ? <div className="success-banner">Location settings saved.</div> : null}
    </section> : null}
  </div>;
}
