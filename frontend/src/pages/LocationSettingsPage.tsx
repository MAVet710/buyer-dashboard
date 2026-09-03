import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type Settings = { auto_map_products_during_receive: boolean; default_receiving_room: string };
type Context = { organization: { name: string } | null; facility_id: string; facilities: { id: string; name: string }[] };
type SetupSection = { key: string; label: string; priority: string; status: string; description: string };
type SetupAction = { operation_type: string; label: string; resource: string; method: string; path: string; required_permission: string; dispatch_enabled: boolean; verification_status: string; note: string };
type FacilitySetup = {
  workspace: string;
  facility_id: string;
  role: string;
  can_manage: boolean;
  metrc: { configured: boolean; status: string; trusted_mapping: boolean; jurisdiction_code: string; license_number: string; environment: string; employee_license_number: string; message: string };
  sections: SetupSection[];
  actions: SetupAction[];
  lab_data_scope: { mode: string; included: string[]; excluded: string[] };
  retail_scope: { mode: string; message: string };
  documentation_scope: string;
};
type LiveEnvelope = { source: string; jurisdiction_code: string; license_number: string; environment: string; bounded: boolean; page_size: number };
type RoomsPayload = LiveEnvelope & {
  locations: Record<string, unknown>[];
  inactive_locations: Record<string, unknown>[];
  location_types: Record<string, unknown>[];
  sublocations: Record<string, unknown>[];
  inactive_sublocations: Record<string, unknown>[];
};
type StrainsPayload = LiveEnvelope & { strains: Record<string, unknown>[]; inactive_strains: Record<string, unknown>[] };
type ItemsPayload = LiveEnvelope & {
  items: Record<string, unknown>[];
  inactive_items: Record<string, unknown>[];
  categories: Record<string, unknown>[];
  brands: Record<string, unknown>[];
  units_of_measure: Record<string, unknown>[];
};
type ProcessingPayload = LiveEnvelope & {
  job_types: Record<string, unknown>[];
  inactive_job_types: Record<string, unknown>[];
  attributes: Record<string, unknown>[];
  categories: Record<string, unknown>[];
};
type AdditivePayload = LiveEnvelope & { additive_templates: Record<string, unknown>[]; inactive_additive_templates: Record<string, unknown>[] };
type TransportationPayload = LiveEnvelope & { drivers: Record<string, unknown>[]; vehicles: Record<string, unknown>[] };
type PermissionPayload = { status: string; can_introspect: boolean; permissions: string[]; employee_license_number?: string; message: string };
type PreviewPayload = { operation: SetupAction; provider_request: { method: string; path: string; query: Record<string, string>; body: Record<string, unknown>[] | null }; dispatch_enabled: boolean; requires_human_confirmation: boolean; message: string };
type Tab = "rooms" | "strains" | "items" | "production" | "cultivation" | "transportation" | "receiving";

const value = (row: Record<string, unknown>, ...keys: string[]): string => {
  for (const key of keys) {
    const candidate = row[key];
    if (candidate !== undefined && candidate !== null && String(candidate).trim()) return String(candidate);
  }
  return "";
};

const joined = (row: Record<string, unknown>, keys: string[]): string => keys.map(key => value(row, key)).filter(Boolean).join(" · ");

const resourcesForTab = (tab: Tab): string[] => {
  if (tab === "items") return ["items", "brands"];
  if (tab === "production") return ["processing_job_types"];
  if (tab === "cultivation") return ["additive_templates"];
  if (tab === "transportation") return ["drivers", "vehicles"];
  return [];
};

export function LocationSettingsPage() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["location-settings"], queryFn: ({ signal }) => apiGet<Settings>("/api/v1/location-settings", signal) });
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const setup = useQuery({ queryKey: ["facility-setup"], queryFn: ({ signal }) => apiGet<FacilitySetup>("/api/v1/location-settings/facility-setup", signal) });
  const rooms = useQuery({ queryKey: ["facility-setup", "metrc-rooms"], queryFn: ({ signal }) => apiGet<RoomsPayload>("/api/v1/location-settings/metrc-rooms", signal), enabled: false, retry: false });
  const strains = useQuery({ queryKey: ["facility-setup", "metrc-strains"], queryFn: ({ signal }) => apiGet<StrainsPayload>("/api/v1/location-settings/metrc-strains", signal), enabled: false, retry: false });
  const items = useQuery({ queryKey: ["facility-setup", "metrc-items"], queryFn: ({ signal }) => apiGet<ItemsPayload>("/api/v1/location-settings/metrc-items", signal), enabled: false, retry: false });
  const processing = useQuery({ queryKey: ["facility-setup", "metrc-processing-setup"], queryFn: ({ signal }) => apiGet<ProcessingPayload>("/api/v1/location-settings/metrc-processing-setup", signal), enabled: false, retry: false });
  const additives = useQuery({ queryKey: ["facility-setup", "metrc-additive-templates"], queryFn: ({ signal }) => apiGet<AdditivePayload>("/api/v1/location-settings/metrc-additive-templates", signal), enabled: false, retry: false });
  const transportation = useQuery({ queryKey: ["facility-setup", "metrc-transportation"], queryFn: ({ signal }) => apiGet<TransportationPayload>("/api/v1/location-settings/metrc-transportation", signal), enabled: false, retry: false });
  const permissions = useQuery({ queryKey: ["facility-setup", "metrc-permissions"], queryFn: ({ signal }) => apiGet<PermissionPayload>("/api/v1/location-settings/metrc-permissions", signal), enabled: false, retry: false });
  const [tab, setTab] = useState<Tab>("rooms");
  const [autoMap, setAutoMap] = useState(false);
  const [room, setRoom] = useState("Receiving");
  const [employeeLicense, setEmployeeLicense] = useState("");
  const [roomName, setRoomName] = useState("");
  const [roomType, setRoomType] = useState("");
  const [sublocationName, setSublocationName] = useState("");
  const [strainName, setStrainName] = useState("");
  const [preview, setPreview] = useState<PreviewPayload | null>(null);

  useEffect(() => { if (settings.data) { setAutoMap(Boolean(settings.data.auto_map_products_during_receive)); setRoom(settings.data.default_receiving_room || "Receiving"); } }, [settings.data]);
  useEffect(() => { if (setup.data) setEmployeeLicense(setup.data.metrc.employee_license_number || ""); }, [setup.data]);

  const save = useMutation({
    mutationFn: () => apiPost<Settings>("/api/v1/location-settings", { auto_map_products_during_receive: autoMap, default_receiving_room: room }),
    onSuccess: data => { client.setQueryData(["location-settings"], data); setAutoMap(Boolean(data.auto_map_products_during_receive)); setRoom(data.default_receiving_room || "Receiving"); },
  });
  const saveEmployee = useMutation({
    mutationFn: () => apiPost<{ employee_license_number: string }>("/api/v1/location-settings/metrc-employee", { employee_license_number: employeeLicense }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["facility-setup"] }); permissions.refetch(); },
  });
  const prepareAction = useMutation({
    mutationFn: (request: { operation_type: string; payload: Record<string, unknown> }) => apiPost<PreviewPayload>("/api/v1/location-settings/metrc-action-preview", request),
    onSuccess: data => setPreview(data),
  });

  const facility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  const roomTypes = rooms.data?.location_types ?? [];
  const canPrepare = Boolean(setup.data?.can_manage && setup.data?.metrc.configured && setup.data?.metrc.status === "connected" && setup.data?.metrc.trusted_mapping);

  return <div className="page">
    <div className="eyebrow">DATA & SETTINGS / LOCATION · SETTINGS & ADMINISTRATION / FACILITY SETUP</div>
    <div className="page-heading"><div><h1>Facility Setup</h1><p>{context.data?.organization?.name ?? "Organization"} · {facility?.name ?? "Facility"}</p><p>Manage the operational structure that sits underneath inventory, cultivation, production, wholesale, and Metrc. Live provider data loads only when you request it.</p></div></div>

    {setup.isLoading ? <div className="state">Loading Facility Setup…</div> : null}
    {setup.isError ? <div className="state error">{setup.error.message}</div> : null}
    {setup.data ? <>
      <section className="inventory-panel">
        <div className="page-heading"><div><h3>Metrc facility connection</h3><p>{setup.data.metrc.jurisdiction_code || "No jurisdiction"} · {setup.data.metrc.license_number || "No license"} · {setup.data.metrc.environment}</p></div></div>
        <div className={setup.data.metrc.status === "connected" && setup.data.metrc.trusted_mapping ? "success-banner" : "state"}>{setup.data.metrc.message}</div>
        <div className="form-grid">
          <label className="span-2">Metrc employee license number<input value={employeeLicense} placeholder="Used only for facility-specific permission introspection" onChange={event => setEmployeeLicense(event.target.value)}/></label>
        </div>
        <div className="button-row">
          <button className="secondary" type="button" disabled={!setup.data.can_manage || saveEmployee.isPending || !setup.data.metrc.configured} onClick={() => saveEmployee.mutate()}>{saveEmployee.isPending ? "Saving…" : "Save employee identity"}</button>
          <button className="secondary" type="button" disabled={permissions.isFetching || !setup.data.metrc.configured} onClick={() => permissions.refetch()}>{permissions.isFetching ? "Checking…" : "Check Metrc permissions"}</button>
        </div>
        {saveEmployee.isError ? <div className="state error">{saveEmployee.error.message}</div> : null}
        {permissions.isError ? <div className="state error">{permissions.error.message}</div> : null}
        {permissions.data ? <div className="inventory-panel"><strong>{permissions.data.status === "synced" ? "Permission sync complete" : "Permission enforcement"}</strong><p>{permissions.data.message}</p>{permissions.data.permissions.length ? <p className="source-caption">{permissions.data.permissions.join(" · ")}</p> : null}</div> : null}
      </section>

      <section className="inventory-panel">
        <h3>Facility workspaces</h3>
        <div className="button-row">
          {setup.data.sections.map(section => <button key={section.key} className={tab === section.key ? "primary" : "secondary"} type="button" onClick={() => setTab(section.key as Tab)}>{section.label}</button>)}
          <button className={tab === "receiving" ? "primary" : "secondary"} type="button" onClick={() => setTab("receiving")}>Receiving Defaults</button>
        </div>
      </section>

      {tab === "rooms" ? <section className="inventory-panel">
        <div className="page-heading"><div><h3>Rooms & Locations</h3><p>Locations and sublocations are loaded directly from the active Metrc facility. Create/edit/discontinue requests are visible here, but provider mutation stays locked until sandbox write/readback verification.</p></div><button className="primary" type="button" disabled={rooms.isFetching} onClick={() => rooms.refetch()}>{rooms.isFetching ? "Syncing…" : rooms.data ? "Refresh from Metrc" : "Load from Metrc"}</button></div>
        {rooms.isError ? <div className="state error">{rooms.error.message}</div> : null}
        {rooms.data ? <>
          <div className="metric-grid">
            <div className="metric-card"><span>Active rooms</span><strong>{rooms.data.locations.length}</strong></div>
            <div className="metric-card"><span>Sublocations</span><strong>{rooms.data.sublocations.length}</strong></div>
            <div className="metric-card"><span>Inactive rooms</span><strong>{rooms.data.inactive_locations.length}</strong></div>
          </div>
          <RecordGroup title="Active rooms" rows={rooms.data.locations} nameKeys={["Name", "name"]} detailKeys={["LocationTypeName", "locationTypeName"]}/>
          <RecordGroup title="Sublocations" rows={rooms.data.sublocations} nameKeys={["Name", "name"]} detailKeys={["ParentLocationName", "LocationName"]}/>
        </> : <div className="state">Live Metrc rooms are not placed on the normal page-load critical path. Choose “Load from Metrc” when you want current provider structure.</div>}

        <div className="form-grid">
          <label>New room / location<input value={roomName} placeholder="Flower Room 2" onChange={event => setRoomName(event.target.value)}/></label>
          <label>Metrc location type<select value={roomType} onChange={event => setRoomType(event.target.value)}><option value="">Select type</option>{roomTypes.map((row, index) => { const name = value(row, "Name", "name", "LocationTypeName"); return <option key={name || index} value={name}>{name || `Type ${index + 1}`}</option>; })}</select></label>
          <label className="span-2">New sublocation<input value={sublocationName} placeholder="Rack A / Shelf 2" onChange={event => setSublocationName(event.target.value)}/></label>
        </div>
        <div className="button-row">
          <button className="primary" type="button" disabled={!canPrepare || !roomName || !roomType || prepareAction.isPending} onClick={() => prepareAction.mutate({ operation_type: "location_create", payload: { name: roomName, location_type_name: roomType } })}>Prepare room creation</button>
          <button className="secondary" type="button" disabled={!canPrepare || !sublocationName || prepareAction.isPending} onClick={() => prepareAction.mutate({ operation_type: "sublocation_create", payload: { name: sublocationName } })}>Prepare sublocation creation</button>
        </div>
        {!canPrepare ? <p className="source-caption">Provider-changing controls require an authorized DoobieLogic role, a connected Metrc credential, and a trusted facility/license mapping.</p> : null}
        {prepareAction.isError ? <div className="state error">{prepareAction.error.message}</div> : null}
      </section> : null}

      {tab === "strains" ? <section className="inventory-panel">
        <div className="page-heading"><div><h3>Strains</h3><p>Read the current Metrc strain master and prepare reviewed create requests from the same Facility Setup workspace.</p></div><button className="primary" type="button" disabled={strains.isFetching} onClick={() => strains.refetch()}>{strains.isFetching ? "Syncing…" : strains.data ? "Refresh from Metrc" : "Load from Metrc"}</button></div>
        {strains.isError ? <div className="state error">{strains.error.message}</div> : null}
        {strains.data ? <>
          <div className="metric-grid"><div className="metric-card"><span>Active strains</span><strong>{strains.data.strains.length}</strong></div><div className="metric-card"><span>Inactive strains</span><strong>{strains.data.inactive_strains.length}</strong></div></div>
          <RecordGroup title="Active strains" rows={strains.data.strains} nameKeys={["Name", "name"]} detailKeys={["Genetics", "TestingStatus"]}/>
        </> : <div className="state">Choose “Load from Metrc” to inspect the current strain master.</div>}
        <div className="form-grid"><label className="span-2">New strain name<input value={strainName} placeholder="GMO" onChange={event => setStrainName(event.target.value)}/></label></div>
        <button className="primary" type="button" disabled={!canPrepare || !strainName || prepareAction.isPending} onClick={() => prepareAction.mutate({ operation_type: "strain_create", payload: { name: strainName } })}>Prepare strain creation</button>
      </section> : null}

      {tab === "items" ? <section className="inventory-panel">
        <LiveHeading section={setup.data.sections.find(section => section.key === "items")} loading={items.isFetching} loaded={Boolean(items.data)} onLoad={() => items.refetch()}/>
        {items.isError ? <div className="state error">{items.error.message}</div> : null}
        {items.data ? <>
          <div className="metric-grid">
            <div className="metric-card"><span>Active items</span><strong>{items.data.items.length}</strong></div>
            <div className="metric-card"><span>Inactive items</span><strong>{items.data.inactive_items.length}</strong></div>
            <div className="metric-card"><span>Brands</span><strong>{items.data.brands.length}</strong></div>
            <div className="metric-card"><span>Categories</span><strong>{items.data.categories.length}</strong></div>
          </div>
          <RecordGroup title="Active Metrc items" rows={items.data.items} nameKeys={["Name", "name"]} detailKeys={["ProductCategoryName", "ItemCategoryName", "BrandName", "UnitOfMeasureName"]}/>
          <RecordGroup title="Item brands" rows={items.data.brands} nameKeys={["Name", "BrandName"]} detailKeys={["Status"]}/>
          <RecordGroup title="Item categories" rows={items.data.categories} nameKeys={["Name", "ProductCategoryName"]} detailKeys={["ProductCategoryType", "Type"]}/>
          <RecordGroup title="Units of measure" rows={items.data.units_of_measure} nameKeys={["Name", "UnitOfMeasureName"]} detailKeys={["Abbreviation", "QuantityType"]}/>
          <RecordGroup title="Inactive Metrc items" rows={items.data.inactive_items} nameKeys={["Name", "name"]} detailKeys={["ProductCategoryName", "BrandName"]}/>
        </> : <LiveReadState label="items, brands, categories, and units of measure"/>}
        <ActionCatalog actions={setup.data.actions.filter(action => resourcesForTab("items").includes(action.resource))}/>
      </section> : null}

      {tab === "production" ? <section className="inventory-panel">
        <LiveHeading section={setup.data.sections.find(section => section.key === "production")} loading={processing.isFetching} loaded={Boolean(processing.data)} onLoad={() => processing.refetch()}/>
        {processing.isError ? <div className="state error">{processing.error.message}</div> : null}
        {processing.data ? <>
          <div className="metric-grid">
            <div className="metric-card"><span>Active processes</span><strong>{processing.data.job_types.length}</strong></div>
            <div className="metric-card"><span>Inactive processes</span><strong>{processing.data.inactive_job_types.length}</strong></div>
            <div className="metric-card"><span>Categories</span><strong>{processing.data.categories.length}</strong></div>
            <div className="metric-card"><span>Attributes</span><strong>{processing.data.attributes.length}</strong></div>
          </div>
          <RecordGroup title="Active Processing Job Types" rows={processing.data.job_types} nameKeys={["Name", "JobTypeName"]} detailKeys={["CategoryName", "Description"]}/>
          <RecordGroup title="Processing categories" rows={processing.data.categories} nameKeys={["Name", "CategoryName"]} detailKeys={["Description"]}/>
          <RecordGroup title="Processing attributes" rows={processing.data.attributes} nameKeys={["Name", "AttributeName"]} detailKeys={["DataType", "Description"]}/>
          <RecordGroup title="Inactive Processing Job Types" rows={processing.data.inactive_job_types} nameKeys={["Name", "JobTypeName"]} detailKeys={["CategoryName"]}/>
        </> : <LiveReadState label="Processing Job Types, categories, and attributes"/>}
        <ActionCatalog actions={setup.data.actions.filter(action => resourcesForTab("production").includes(action.resource))}/>
      </section> : null}

      {tab === "cultivation" ? <section className="inventory-panel">
        <LiveHeading section={setup.data.sections.find(section => section.key === "cultivation")} loading={additives.isFetching} loaded={Boolean(additives.data)} onLoad={() => additives.refetch()}/>
        {additives.isError ? <div className="state error">{additives.error.message}</div> : null}
        {additives.data ? <>
          <div className="metric-grid"><div className="metric-card"><span>Active additive templates</span><strong>{additives.data.additive_templates.length}</strong></div><div className="metric-card"><span>Inactive templates</span><strong>{additives.data.inactive_additive_templates.length}</strong></div></div>
          <RecordGroup title="Active additive templates" rows={additives.data.additive_templates} nameKeys={["Name", "TemplateName"]} detailKeys={["AdditiveName", "ProductTradeName", "UnitOfMeasureName"]}/>
          <RecordGroup title="Inactive additive templates" rows={additives.data.inactive_additive_templates} nameKeys={["Name", "TemplateName"]} detailKeys={["AdditiveName", "ProductTradeName"]}/>
        </> : <LiveReadState label="active and inactive additive templates"/>}
        <ActionCatalog actions={setup.data.actions.filter(action => resourcesForTab("cultivation").includes(action.resource))}/>
      </section> : null}

      {tab === "transportation" ? <section className="inventory-panel">
        <LiveHeading section={setup.data.sections.find(section => section.key === "transportation")} loading={transportation.isFetching} loaded={Boolean(transportation.data)} onLoad={() => transportation.refetch()}/>
        {transportation.isError ? <div className="state error">{transportation.error.message}</div> : null}
        {transportation.data ? <>
          <div className="metric-grid"><div className="metric-card"><span>Drivers</span><strong>{transportation.data.drivers.length}</strong></div><div className="metric-card"><span>Vehicles</span><strong>{transportation.data.vehicles.length}</strong></div></div>
          <RecordGroup title="Transport drivers" rows={transportation.data.drivers} nameKeys={["Name", "FullName", "FirstName", "LastName"]} detailKeys={["EmployeeLicenseNumber", "LicenseNumber", "PhoneNumber"]}/>
          <RecordGroup title="Transport vehicles" rows={transportation.data.vehicles} nameKeys={["Name", "LicensePlateNumber", "VehicleName"]} detailKeys={["Make", "Model", "Year"]}/>
        </> : <LiveReadState label="Metrc transport drivers and vehicles"/>}
        <ActionCatalog actions={setup.data.actions.filter(action => resourcesForTab("transportation").includes(action.resource))}/>
      </section> : null}

      {tab === "receiving" ? <section className="inventory-panel location-settings-card">
        <h3>Location settings</h3>
        <p>Inventory receiving</p>
        {settings.isLoading ? <div className="state">Loading receiving settings…</div> : null}
        {settings.isError ? <div className="state error">{settings.error.message}</div> : null}
        {settings.data ? <>
          <label className="toggle location-toggle"><input type="checkbox" checked={autoMap} onChange={event => setAutoMap(event.target.checked)}/><span><strong>Auto-map products during receive</strong><small>Reuse only previously reviewed and approved incoming-item → Catalog product mappings for this facility.</small><small>Auto-map never guesses a new catalog relationship.</small></span></label>
          <label className="compact-field">Default receiving room<input value={room} placeholder="Receiving" onChange={event => setRoom(event.target.value)}/></label>
          <button className="primary submit" type="button" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save location settings"}</button>
          {save.isError ? <div className="state error">{save.error.message}</div> : null}
          {save.isSuccess ? <div className="success-banner">Receiving defaults saved.</div> : null}
        </> : null}
      </section> : null}

      <section className="inventory-panel">
        <h3>Scope guardrails</h3>
        <p><strong>Lab data:</strong> {setup.data.lab_data_scope.mode}. DoobieLogic consumes Metrc testing state, results, COA references, remediation/retest context, and release readiness; it does not operate a testing lab.</p>
        <p><strong>Retail/POS:</strong> {setup.data.retail_scope.message}</p>
        <p className="source-caption">{setup.data.documentation_scope}</p>
      </section>
    </> : null}

    {preview ? <section className="inventory-panel">
      <h3>Metrc request preview</h3>
      <p><strong>{preview.operation.label}</strong> · requires {preview.operation.required_permission}</p>
      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.provider_request, null, 2)}</pre>
      <div className="state">{preview.message}</div>
    </section> : null}
  </div>;
}

function LiveHeading({ section, loading, loaded, onLoad }: { section?: SetupSection; loading: boolean; loaded: boolean; onLoad: () => unknown }) {
  if (!section) return null;
  return <div className="page-heading">
    <div><div className="eyebrow">{section.priority} · {section.status}</div><h3>{section.label}</h3><p>{section.description}</p></div>
    <button className="primary" type="button" disabled={loading} onClick={onLoad}>{loading ? "Syncing…" : loaded ? "Refresh from Metrc" : "Load from Metrc"}</button>
  </div>;
}

function LiveReadState({ label }: { label: string }) {
  return <div className="state">Current {label} are fetched only when requested. This keeps Metrc latency and availability out of the normal Facility Setup page-load path.</div>;
}

function RecordGroup({ title, rows, nameKeys, detailKeys }: { title: string; rows: Record<string, unknown>[]; nameKeys: string[]; detailKeys: string[] }) {
  return <details className="inventory-panel" open={rows.length > 0 && rows.length <= 12}>
    <summary><strong>{title}</strong> · {rows.length}</summary>
    {rows.length ? <div className="inventory-grid">{rows.map((row, index) => {
      const id = value(row, "Id", "id", "LicenseNumber", "licenseNumber");
      const first = value(row, ...nameKeys);
      const driverName = [value(row, "FirstName"), value(row, "LastName")].filter(Boolean).join(" ");
      const name = first || driverName || `${title} ${index + 1}`;
      const detail = joined(row, detailKeys);
      return <article className="inventory-panel" key={id || `${title}-${index}`}><strong>{name}</strong>{detail ? <p>{detail}</p> : null}{id ? <p className="source-caption">Metrc ID {id}</p> : null}</article>;
    })}</div> : <div className="state">No records returned by Metrc.</div>}
  </details>;
}

function ActionCatalog({ actions }: { actions: SetupAction[] }) {
  if (!actions.length) return null;
  return <div className="inventory-panel">
    <h4>Provider-changing actions</h4>
    <p>These controls are intentionally staged until their exact request bodies pass controlled Metrc sandbox write and fresh readback verification.</p>
    <div className="inventory-grid">{actions.map(action => <article className="inventory-panel" key={action.operation_type}><strong>{action.label}</strong><p>{action.method} /{action.path}</p><p className="source-caption">Requires {action.required_permission} · {action.verification_status.replaceAll("_", " ")}</p></article>)}</div>
    <div className="state">Live reads are available here now. Network writes remain fail-closed; DoobieLogic does not infer or fabricate a successful compliance change.</div>
  </div>;
}