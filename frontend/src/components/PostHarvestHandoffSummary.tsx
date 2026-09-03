import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Batch = { stage: string; needs_attention: boolean };
type Harvest = { id: string; status: string };
type AccountContext = { user: { role: string } };

const writeRoles = new Set(["dev", "admin", "supervisor", "operator", "qa"]);

export function PostHarvestHandoffSummary({ onOpen }: { onOpen: () => void }) {
  const client = useQueryClient();
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const harvests = useQuery({ queryKey: ["cultivation-harvests"], queryFn: ({ signal }) => apiGet<{ items: Harvest[] }>("/api/v1/inventory/production/plants/harvests", signal) });
  const postHarvest = useQuery({ queryKey: ["post-harvest"], queryFn: ({ signal }) => apiGet<{ items: Batch[] }>("/api/v1/inventory/production/plants/post-harvest", signal) });
  const canWrite = writeRoles.has(account.data?.user.role ?? "");
  const syncKey = (harvests.data?.items ?? []).filter(row => row.status === "active" || row.status === "drying").map(row => `${row.id}:${row.status}`).sort().join("|");
  const lastSyncKey = useRef<string | null>(null);
  const sync = useMutation({
    mutationFn: () => apiPost<{ items: Batch[] }>("/api/v1/inventory/production/plants/post-harvest/sync", {}),
    onSuccess: data => client.setQueryData(["post-harvest"], data),
  });

  useEffect(() => {
    if (!canWrite || harvests.isLoading || lastSyncKey.current === syncKey) return;
    lastSyncKey.current = syncKey;
    sync.mutate();
  }, [canWrite, harvests.isLoading, syncKey]);

  const items = postHarvest.data?.items ?? [];
  const count = (stage: string) => items.filter(row => row.stage === stage).length;
  const attention = items.filter(row => row.needs_attention).length;

  return <section className="inventory-panel post-harvest-handoff-summary">
    <div className="section-heading">
      <div>
        <div className="eyebrow">GROW OPERATIONS · HANDOFF</div>
        <h3>Post-Harvest</h3>
        <p className="source-caption">Drying, trim, cure, testing hold and release now live in their own operator workspace. Cultivation keeps only this live handoff view.</p>
      </div>
      <button className="primary" type="button" onClick={onOpen}>Open Post-Harvest</button>
    </div>
    <div className="metrics four">
      <Metric label="Needs attention" value={attention} />
      <Metric label="Drying" value={count("drying")} />
      <Metric label="Ready for trim" value={count("bucking")} />
      <Metric label="Trimming" value={count("trimming")} />
    </div>
    {postHarvest.isLoading ? <div className="state">Loading post-harvest handoff…</div> : null}
    {postHarvest.isError ? <div className="warning-banner">Post-Harvest status could not be loaded: {postHarvest.error.message}</div> : null}
    {sync.isError ? <div className="warning-banner">Open harvests could not be synchronized into Post-Harvest: {sync.error.message}</div> : null}
  </section>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
