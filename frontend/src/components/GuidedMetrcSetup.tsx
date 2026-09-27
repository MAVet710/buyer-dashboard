import { PlatformMetrcKey } from "./PlatformMetrcKey";
import "./cultivation-networks.css";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import { intelligenceScope } from "./cultivationIntelligenceTypes";
import { guidedMetrcBase as BASE, type MetrcSetupStatus, type MetrcFacilityPreview } from "./guidedMetrcTypes";

export function GuidedMetrcSetup() {
  return <Setup key={JSON.stringify(intelligenceScope())} />;
}
function Setup() {
  const client = useQueryClient();
  const scope = JSON.stringify(intelligenceScope());
  const alive = useRef(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<MetrcFacilityPreview | null>(null);
  const [license, setLicense] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [createNew, setCreateNew] = useState(false);
  const [importConfirmed, setImportConfirmed] = useState(false);
  const [productionConfirmed, setProductionConfirmed] = useState(false);
  const status = useQuery({ queryKey: ["guided-metrc", scope],
    queryFn: ({ signal }) => apiGet<MetrcSetupStatus>(BASE, signal), retry: false,
    refetchInterval: query => ["pending", "running"].includes(query.state.data?.run?.status || "") ? 3000 : false,
    refetchIntervalInBackground: false });
  const here = () => alive.current && scope === JSON.stringify(intelligenceScope());
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false;
      void client.cancelQueries({ queryKey: ["guided-metrc", scope] });
      client.removeQueries({ queryKey: ["guided-metrc", scope] }); };
  }, [client, scope]);
  const refresh = () => {
    if (!here()) return;
    void client.invalidateQueries({ queryKey: ["guided-metrc", scope] });
    void client.invalidateQueries({ queryKey: ["integration-wizard"] });
    void client.invalidateQueries({ queryKey: ["implementation-readiness"] });
  };
  async function action(label: string, path: string, payload: unknown, success: string) {
    setBusy(label); setError(""); setMessage("");
    try {
      const result = await apiPost<{ facility_id?: string }>(BASE + path, payload);
      if (here() && path === "/link" && result.facility_id && result.facility_id !== intelligenceScope()[1]) {
        sessionStorage.setItem("buyer-dash-pending-page", "Integration Wizard");
        localStorage.setItem("buyer-dash-facility", result.facility_id);
        client.clear(); window.location.reload(); return;
      }
      if (here()) { setMessage(success); setPreview(null); setConfirmed(false); refresh(); }
    } catch {
      if (here()) setError("The action was not confirmed. Refresh the saved connection and import evidence before retrying.");
    } finally { if (here()) { setBusy(""); refresh(); } }
  }
  async function saveKey(node: HTMLFormElement) {
    // A key is transient input, never React Query mutation data or saved browser state.
    let key = String(new FormData(node).get("api_key") || "");
    node.reset();
    try { await action("Saving your key", "/credentials", { state: "MA", api_key: key }, "Your key is saved securely. Next, find the facilities it can access."); }
    finally { key = ""; }
  }
  async function discover() {
    setBusy("Finding your facilities"); setError(""); setPreview(null); setConfirmed(false);
    try {
      const result = await apiPost<MetrcFacilityPreview>(BASE + "/preview", {});
      if (here()) { setPreview(result); setLicense(result.facilities.length === 1 ? result.facilities[0].license_number : ""); }
    } catch { if (here()) setError("Metrc did not return a verified facility list. Check the saved key, provider permissions and platform connection."); }
    finally { if (here()) setBusy(""); }
  }
  async function selectMode(mode: "metrc_sandbox" | "metrc_production") {
    setBusy("Selecting facility mode"); setError("");
    try { await apiPost("/api/v1/alpha-operating-mode", { mode, production_confirmed: mode === "metrc_production" && productionConfirmed }); refresh(); }
    catch { if (here()) setError("The facility mode was not changed. Review permissions and try again."); }
    finally { if (here()) setBusy(""); }
  }
  const data = status.data;
  return <section className="inventory-panel guided-metrc" aria-label="Guided Metrc connection"><h3>Bring your existing Metrc records into DoobieLogic</h3>
    <p>Connect your account, confirm the license, then import the records you already maintain. Existing local work is preserved.</p>
    {status.isPending && <p role="status">Loading this facility's connection...</p>}
    {status.isError && <p role="alert">Connection evidence is unavailable. Existing settings have not been changed.</p>}
    {data && !status.isError && <>
      <p>Facility: <strong>{data.facility.name}</strong>. License: <strong>{data.facility.license_number || "Not linked yet"}</strong>. Environment: <strong>{data.environment}</strong>.</p>
      {data.can_manage_platform && <PlatformMetrcKey key={data.environment} environment={data.environment} onSaved={refresh} />}
      {!data.production_available && <p>This guided lane currently uses the verified Massachusetts Metrc sandbox. Production onboarding and writes are not enabled by saving a key.</p>}
      {!data.can_manage ? <p>Read only. A facility administrator must connect and import records.</p> : <>
        {!["metrc_sandbox", "metrc_production"].includes(data.mode) && <><p>Metrc access is disabled in the current facility mode. Choose the correct environment explicitly before connecting. Do not use sandbox records in a production facility.</p><button className="secondary" disabled={Boolean(busy)} onClick={() => void selectMode("metrc_sandbox")}>Use Metrc Sandbox for this facility</button><label><input type="checkbox" checked={productionConfirmed} onChange={event => setProductionConfirmed(event.target.checked)} />This is a real licensed production facility. Import existing records without submitting changes to Metrc.</label><button className="primary" disabled={Boolean(busy) || !productionConfirmed} onClick={() => void selectMode("metrc_production")}>Use Metrc Production for this facility</button></>}
        {["metrc_sandbox", "metrc_production"].includes(data.mode) && <fieldset disabled={Boolean(busy) || ["pending", "running"].includes(data.run?.status || "")}>
          <form onSubmit={event => { event.preventDefault(); void saveKey(event.currentTarget); }}>
            <label>Your Metrc user API key<input type="password" name="api_key" required minLength={8} maxLength={1024} autoComplete="off" /></label>
            <p>{data.user_key_saved ? "A key is already saved. Leave it unchanged unless you intend to replace it." : "Use your own Metrc user key. Do not enter your DoobieLogic password."}</p>
            <button className="secondary" type="submit">Save user key securely</button>
          </form>
          {!data.platform_key_ready && <p role="status">The platform's Metrc connection is not configured for this facility. Your administrator must configure it. You do not need DoobieLogic's integrator key.</p>}
          <button className="primary" disabled={!data.user_key_saved || !data.platform_key_ready} onClick={() => void discover()}>Find my Metrc facilities</button>
          {preview && <section aria-label="Metrc facility preview"><h4>Choose the license for this facility</h4>
            <p>This preview has not created records or changed Metrc.</p>
            {!preview.facilities.length ? <p>No accessible licenses were returned. Check this user's Metrc permissions.</p> : <>
              <label>Metrc facility<select value={license} onChange={event => { setLicense(event.target.value); setConfirmed(false); }}><option value="">Select your licensed facility</option>{preview.facilities.map(item => <option key={item.license_number} value={item.license_number}>{item.name} | {item.license_number}</option>)}</select></label>
              <label><input type="checkbox" checked={createNew} onChange={event => { setCreateNew(event.target.checked); setConfirmed(false); }} />Create the missing DoobieLogic facility from this license, or reopen its existing exact match, instead of linking {data.facility.name}.</label>
              <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I authorize this license selection and its DoobieLogic facility link.</label>
              <button className="primary" disabled={!license || !confirmed} onClick={() => void action("Linking facility", "/link", { license_number: license, preview_id: preview.preview_id, confirmed: true, create_new: createNew }, "Facility linked. You can now import its existing records.")}>{createNew ? "Create or open licensed facility" : "Confirm facility link"}</button>
            </>}
          </section>}
          {data.trusted_mapping && data.configured && <section aria-label="Import Metrc records"><h4>Populate your workspaces</h4>
            <p>Import available items, packages, plant groups, plants, rooms and harvests. Missing records are created where their identities are certain. Conflicts need review; historical actions are not invented.</p>
            <label><input type="checkbox" checked={importConfirmed} onChange={event => setImportConfirmed(event.target.checked)} />Create missing DoobieLogic records from this facility's Metrc evidence. Do not send changes to Metrc.</label>
            <button className="primary" disabled={!importConfirmed} onClick={() => void action("Importing facility records", "/import", { confirmed: true }, "Import started on the DoobieLogic host. You can leave this page and return to its saved progress.")}>{data.run ? "Sync or resume existing records" : "Import existing facility records"}</button>
          </section>}
        </fieldset>}
      </>}
      {data.run?.workspace_summary && <p>{data.run.workspace_summary.conflict_count} materialization conflict(s) need review. Processing counts are not new-record counts.</p>}
      {data.run && <p role="status">Import: {data.run.status.replaceAll("_", " ")}. {data.run.totals ? `${data.run.totals.records} provider records processed; ${data.run.totals.errors} issue(s) need review.` : "Progress is saved as provider pages finish."}</p>}
      <details><summary>Imported resource evidence</summary><p>Counts are provider processing evidence, not proof that every operational workflow is ready. Restricted or conflicting records stay visible for review.</p>
        <div className="table-scroll"><table><thead><tr><th>Records</th><th>State</th><th>Seen</th><th>Saved</th><th>Last success</th></tr></thead><tbody>{data.resources.map(row => <tr key={row.resource}><td>{row.resource.replaceAll("_", " ")}</td><td>{row.restricted ? "Permission restricted" : row.status}</td><td>{row.records_seen}</td><td>{row.records_written}</td><td>{row.last_success_at || "Not recorded"}</td></tr>)}</tbody></table></div>
      </details>
      <p>Saving credentials does not prove a complete import. Importing records does not authorize production writes. Supported operational actions keep their existing permission and reconciliation checks.</p>
    </>}
    {busy && <p role="status">{busy}...</p>}{message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <button className="secondary" disabled={status.isFetching} onClick={refresh}>Refresh saved setup and import progress</button>
  </section>;
}
