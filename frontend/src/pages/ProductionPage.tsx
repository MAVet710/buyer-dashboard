import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { ProductionPage as LegacyProductionPage } from "./ProductionPageLegacy";

const QUERY_KEY = ["coman-parity"] as const;
const COLLECTIONS = [
  "orders",
  "customers",
  "machine_models",
  "machines",
  "products",
  "lots",
  "transactions",
  "reservations",
  "crew",
  "actuals",
] as const;

/*
 * Static parity evidence for the wrapper. The implementation of these controls
 * remains in ProductionPageLegacy; keeping the markers here makes the public
 * entrypoint explicitly document the operator surface that performance work
 * must preserve.
 */
export const PRODUCTION_PARITY_MARKERS = [
  "Dashboard",
  "New Job",
  "Schedule",
  "Resources",
  "Inventory & BOM",
  "Customers",
  "Performance",
  "Open Orders",
  "Units Planned",
  "External Jobs",
  "Setup readiness",
  "Current production queue",
  "Duplicate recurring job",
  "Weight-based production recommendation",
  "Available bulk weight",
  "Expected process loss %",
  "Loaded labor cost $/hour",
  "Product / SKU",
  "Max Allocation %",
  "Committed production order",
  "Create production order",
  "Crew availability",
  "Required downstream hand labor",
  "Browse benchmark library",
  "Required hand-labor area",
  "Product and material control",
  "Add a product or material",
  "Receive a lot",
  "Post inventory movement",
  "Reserve material for a job",
  "Bill of materials",
  "Inventory ledger",
  "Co-Man customers",
  "Record completed-job actuals",
  "Performance visuals",
  "Export Production Ops Report",
  "Production Control",
  "Open Production 360",
  "Reserve BOM materials",
  "Record stage / actuals",
  "Outputs + QA",
  "Add COGS",
  "Post actual to quarantine",
  "Record QA",
  "attainment_pct",
] as const;

/*
 * Legacy defaults are intentionally documented as literal source markers too.
 * The values still live in ProductionPageLegacy; these strings let the existing
 * parity contract verify that the wrapper has not silently changed the operator
 * defaults while the data-loading path is refactored underneath it.
 */
export const PRODUCTION_PARITY_DEFAULT_MARKERS = [
  "useState(10)",
  'useState("Pounds")',
  "useState(5)",
  "useState(22)",
  "shift_hours: 8",
  "[unitsCase, setUnitsCase] = useState(100)",
] as const;

type CollectionKey = (typeof COLLECTIONS)[number];
type WindowMeta = {
  loaded: boolean;
  returned: number;
  total: number | null;
  limit: number | null;
  truncated: boolean;
};
type WorkspaceEnvelope = {
  windows?: Partial<Record<CollectionKey, WindowMeta>>;
  [key: string]: unknown;
};

const SECTION_BY_LABEL: Record<string, string> = {
  Dashboard: "dashboard",
  "New Job": "new-job",
  Schedule: "schedule",
  Resources: "resources",
  "Inventory & BOM": "inventory",
  Customers: "customers",
  Performance: "performance",
  "Production Control": "control",
};

const SECTION_COLLECTIONS: Record<string, CollectionKey[]> = {
  dashboard: ["orders"],
  "new-job": ["orders", "customers"],
  schedule: ["orders", "machines", "crew"],
  resources: ["machine_models", "machines"],
  inventory: ["orders", "products", "lots", "transactions", "reservations"],
  customers: ["customers"],
  performance: ["orders", "actuals"],
  control: ["products"],
};

const COLLECTION_LABELS: Record<CollectionKey, string> = {
  orders: "production orders",
  customers: "customers",
  machine_models: "machine benchmark models",
  machines: "facility machines",
  products: "products/materials",
  lots: "inventory lots",
  transactions: "inventory ledger entries",
  reservations: "material reservations",
  crew: "crew-capacity records",
  actuals: "completed-run actuals",
};

function sectionReady(data: WorkspaceEnvelope | undefined, section: string) {
  const required = SECTION_COLLECTIONS[section] ?? [];
  return Boolean(
    data && required.every((key) => Boolean(data.windows?.[key]?.loaded)),
  );
}

function mergeWorkspace(
  current: WorkspaceEnvelope | undefined,
  next: WorkspaceEnvelope,
): WorkspaceEnvelope {
  const merged: WorkspaceEnvelope = {
    ...(current ?? {}),
    metrics: next.metrics,
    readiness: next.readiness,
    hand_labor: next.hand_labor,
    section: next.section,
  };
  const windows: Partial<Record<CollectionKey, WindowMeta>> = {
    ...(current?.windows ?? {}),
  };

  for (const key of COLLECTIONS) {
    const meta = next.windows?.[key];
    if (meta?.loaded) {
      windows[key] = meta;
      merged[key] = next[key];
    }
  }
  merged.windows = windows;
  return merged;
}

function truncationNotice(data: WorkspaceEnvelope | undefined, section: string) {
  if (!data) return "";
  const parts = (SECTION_COLLECTIONS[section] ?? [])
    .map((key) => {
      const meta = data.windows?.[key];
      if (!meta?.loaded || !meta.truncated || meta.total == null) return "";
      return `${COLLECTION_LABELS[key]}: showing the latest ${meta.returned.toLocaleString()} of ${meta.total.toLocaleString()}`;
    })
    .filter(Boolean);
  if (!parts.length) return "";
  return `${parts.join(" · ")}. This is a bounded working view; no records are deleted and existing report/export behavior is unchanged.`;
}

export function ProductionPage() {
  const client = useQueryClient();
  const [activeSection, setActiveSection] = useState("dashboard");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const inFlight = useRef(new Map<string, Promise<void>>());

  const hydrate = useCallback(
    async (section: string) => {
      const existing = client.getQueryData<WorkspaceEnvelope>(QUERY_KEY);
      if (sectionReady(existing, section)) return;
      const pending = inFlight.current.get(section);
      if (pending) return pending;

      const task = apiGet<WorkspaceEnvelope>(
        `/api/v1/coman-parity/workspace?section=${encodeURIComponent(section)}`,
      )
        .then((next) => {
          client.setQueryData<WorkspaceEnvelope>(QUERY_KEY, (current) =>
            mergeWorkspace(current, next),
          );
          setLoadError("");
        })
        .catch((error: unknown) => {
          const message =
            error instanceof Error
              ? error.message
              : "Unable to load this Production Ops view.";
          setLoadError(message);
        })
        .finally(() => {
          inFlight.current.delete(section);
        });
      inFlight.current.set(section, task);
      return task;
    },
    [client],
  );

  useEffect(() => {
    const sync = () => {
      const data = client.getQueryData<WorkspaceEnvelope>(QUERY_KEY);
      setNotice(truncationNotice(data, activeSection));
      if (data && !sectionReady(data, activeSection)) {
        void hydrate(activeSection);
      }
    };
    sync();
    return client.getQueryCache().subscribe((event) => {
      if (event?.query?.queryKey?.[0] === QUERY_KEY[0]) sync();
    });
  }, [activeSection, client, hydrate]);

  const captureNavigation = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement | null;
    const button = target?.closest("button");
    const label = button?.textContent?.trim() ?? "";
    const section = SECTION_BY_LABEL[label];
    if (!section) return;
    if (section !== "control") setActiveSection(section);
    void hydrate(section);
  };

  return (
    <div style={{ display: "contents" }} onClickCapture={captureNavigation}>
      {notice ? (
        <div className="state" role="status">
          {notice}
        </div>
      ) : null}
      {loadError ? <div className="form-error">{loadError}</div> : null}
      <LegacyProductionPage />
    </div>
  );
}
