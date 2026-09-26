import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import "./adoption.css";

const wizardSteps = ["facility", "systems", "connect", "validate", "map", "evidence", "summary"] as const;
type Step = typeof wizardSteps[number];
const titles: Record<Step, string> = { facility: "Confirm facility", systems: "Choose systems", connect: "Connect", validate: "Validate", map: "Map", evidence: "Prove ready", summary: "Readiness summary" };
const wizardStatuses: Record<string, string> = { connected: "Connected", needs_validation: "Needs validation", needs_mapping: "Needs mapping", optional_skipped: "Optional skipped", not_applicable: "Not applicable", blocked: "Blocked" };
export type WizardItem = { key: string; label: string; required: boolean; status: string; evidence: string; last_validated_at: string | null; environment: string; test_path: string | null; settings_path: string; mapping_route: string; managed_entities: string[]; manual_mapping_required: string[] };
export type WizardData = { facility: { id: string; name: string; license_number: string; license_type: string; capabilities: string[] }; mode: { effective_mode: string; message: string }; items: WizardItem[]; step: Step; can_manage: boolean };

function ProviderEvidence({ item, canManage, step, onNavigate, refresh }: { item: WizardItem; canManage: boolean; step: Step; onNavigate: (page: string) => void; refresh: () => void }) {
  const skip = useMutation({ mutationFn: () => apiPost(`/api/v1/integration-wizard/providers/${item.key}`, { skipped: item.status !== "optional_skipped" }), onSuccess: refresh });
  const test = useMutation({
    mutationFn: async () => {
      const result = await apiPost<{ result: { ok: boolean } }>(item.test_path!, {});
      if (!result.result?.ok) throw new Error("Provider validation failed. Review advanced settings and retry after correcting the connection.");
    },
    onSettled: refresh,
  });
  const active = !["optional_skipped", "not_applicable"].includes(item.status);
  return <article className="inventory-panel">
    <h3>{item.label} <small>{item.required ? "Required" : "Optional"}</small></h3>
    <strong>{wizardStatuses[item.status] ?? "Blocked"}</strong><p>{item.evidence}</p>
    <p>Environment: {item.environment}. Last validation: {item.last_validated_at ? new Date(item.last_validated_at).toLocaleString() : "Not recorded"}.</p>
    {!!item.managed_entities.length && <p>Managed entities: {item.managed_entities.join(", ")}. Manual mapping: {item.manual_mapping_required.join(", ")}. Customer synchronization is required before posting an invoice.</p>}
    <button className="secondary" onClick={() => onNavigate(item.settings_path)}>Open advanced settings for {item.label}</button>
    {active && ["map", "evidence", "summary"].includes(step) && <button className="secondary" onClick={() => onNavigate(item.mapping_route)}>Review {item.label} mapping and workflow</button>}
    {canManage && active && item.test_path && ["validate", "evidence", "summary"].includes(step) && <button className="primary" disabled={test.isPending || skip.isPending} onClick={() => test.mutate()}>{test.isPending ? "Validating..." : `Test / Validate ${item.label}`}</button>}
    {canManage && !item.required && item.status !== "not_applicable" && step === "systems" && <button className="secondary" disabled={skip.isPending || test.isPending} onClick={() => skip.mutate()}>{item.status === "optional_skipped" ? `Include ${item.label}` : `Skip optional ${item.label}`}</button>}
    {test.isError && <p role="alert">{test.error.message}</p>}{skip.isError && <p role="alert">{skip.error.message}</p>}
    {test.isSuccess && <p role="status">Connection test succeeded. Current mapping and workflow evidence still determine readiness.</p>}
  </article>;
}

function GuidedFlow({ data, onNavigate, refresh }: { data: WizardData; onNavigate: (page: string) => void; refresh: () => void }) {
  const [step, setStep] = useState<Step>(data.step);
  const move = useMutation({ mutationFn: (next: Step) => apiPost("/api/v1/integration-wizard/progress", { step: next }), onSuccess: (_, next) => { setStep(next); refresh(); } });
  const index = wizardSteps.indexOf(step);
  const navigateStep = (next: Step) => data.can_manage ? move.mutate(next) : setStep(next);
  const remaining = data.items.filter(item => item.required && !["connected", "optional_skipped", "not_applicable"].includes(item.status));
  return <>
    <p>{data.facility.name} | License: {data.facility.license_number || "Not recorded"} | {data.mode.effective_mode.replaceAll("_", " ")}</p>
    <nav className="wizard-steps" aria-label="Integration setup steps">{wizardSteps.map((value, position) => <button key={value} className={value === step ? "primary" : "secondary"} aria-current={value === step ? "step" : undefined} disabled={move.isPending} onClick={() => navigateStep(value)}>{position + 1}. {titles[value]}</button>)}</nav>
    <h2 tabIndex={-1}>{titles[step]}</h2>
    {step === "facility" ? <section className="inventory-panel"><h3>Operating context</h3><p>Facility: {data.facility.name}. License type: {data.facility.license_type || "Not recorded"}.</p><p>Enabled operations: {data.facility.capabilities.join(", ") || "None"}.</p><p>{data.mode.message}</p><p>Confirm this is the facility you intend to set up. Use the facility selector to change context.</p><button className="secondary" onClick={() => onNavigate("Location Settings")}>Review facility settings</button><button className="secondary" onClick={() => onNavigate("Integrations")}>Review operating mode</button></section> : <>
      {step === "systems" && <p>Systems reflect this facility's capabilities and selected operating mode. Optional systems can be deferred. Required systems remain incomplete until their evidence is satisfied.</p>}
      {step === "connect" && <p>Open each provider's existing settings to save its connection. Return with Resume Integration Wizard. Saved work stays in the existing configuration store and stored secrets are never loaded into this wizard.</p>}
      {step === "validate" && <p>Tests run only when you select Test / Validate. These use the existing provider contracts. A successful test proves connectivity, not production synchronization.</p>}
      {step === "map" && <p>Review trusted facility mappings and accounting Item mappings. The wizard does not synchronize or post business records.</p>}
      {step === "evidence" && <p>Review observed validation times, environment, mapping requirements and blockers. Missing evidence cannot be overridden by progressing through this guide.</p>}
      {step === "summary" && <><p>{remaining.length} required provider setup item(s) still need attention. Optional services do not block facility go-live. {data.items.filter(item => item.required && item.status !== "connected").length} required provider(s) remain incomplete.</p><p>Connected means a recorded connection test passed with the setup checks shown here. Go-live acceptance still requires the authoritative Implementation Readiness reviews and operational evidence. Sandbox validation is not production acceptance.</p></>}
      <div className="report-card-grid">{data.items.map(item => <ProviderEvidence key={item.key} item={item} step={step} canManage={data.can_manage} onNavigate={onNavigate} refresh={refresh} />)}</div>
    </>}
    {move.isError && <p role="alert">Progress was not saved: {move.error.message}</p>}
    <div className="wizard-navigation"><button className="secondary" disabled={index === 0 || move.isPending} onClick={() => navigateStep(wizardSteps[index - 1])}>Back</button>{index < wizardSteps.length - 1 && <button className="primary" disabled={move.isPending} onClick={() => navigateStep(wizardSteps[index + 1])}>{step === "facility" ? "Confirm context and continue" : "Next"}</button>}<button className="secondary" onClick={() => onNavigate("Implementation Readiness")}>Open Implementation Readiness</button></div>
  </>;
}

export function IntegrationWizardPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["integration-wizard"], queryFn: ({ signal }) => apiGet<WizardData>("/api/v1/integration-wizard", signal), retry: false });
  const refresh = () => { client.invalidateQueries({ queryKey: ["integration-wizard"] }); client.invalidateQueries({ queryKey: ["implementation-readiness"] }); };
  return <div className="page adoption-page"><h1>Integration Wizard</h1><p>Facility → Integrations → Validate → Map → Prove Ready → Go Live</p>
    <button className="secondary" disabled={query.isFetching} onClick={refresh}>Refresh evidence</button>
    {query.isPending && <p role="status">Loading facility integration evidence...</p>}{query.isError && <p role="alert">{query.error.message}</p>}
    {query.data && !query.isError && <GuidedFlow key={query.data.facility.id} data={query.data} onNavigate={onNavigate} refresh={refresh} />}
  </div>;
}
