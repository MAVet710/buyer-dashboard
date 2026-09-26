import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CultivationIntelligenceWorkspace } from "./CultivationIntelligenceWorkspace";
import { RoomEvidence } from "./Room360";
import { EnvironmentTable, type EnvironmentReading } from "./CultivationEnvironmentPanel";
import { metricLabel, record, rows, type Workspace } from "./cultivationIntelligenceTypes";
const empty: Workspace = { rooms: [], cycles: [], recipes: [], connections: [], can_manage: false, can_manage_connections: false, truncated: false, decision_support_only: true };
function renderWorkspace(data?: Workspace) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (data) client.setQueryData(["cultivation-intelligence", "/workspace"], data);
  const html = renderToStaticMarkup(<QueryClientProvider client={client}><CultivationIntelligenceWorkspace /></QueryClientProvider>);
  client.clear(); return html;
}
describe("cultivation intelligence fixture rendering", () => {
  it("renders loading and honest empty states", () => { expect(renderWorkspace()).toContain("Loading evidence"); expect(renderWorkspace(empty)).toContain("No canonical rooms"); });
  it("honors effective deny and preserves connection setup", () => { const html = renderWorkspace(empty); expect(html).not.toContain(">Create Cycle<"); expect(html).not.toContain(">Recipes<"); expect(html).toContain("Cultivation connection setup"); });
  it("exposes management only on effective grant", () => { const html = renderWorkspace({ ...empty, can_manage: true }); expect(html).toContain(">Create Cycle<"); expect(html).toContain(">Recipes<"); });
  it("renders unknown future metrics without crashing or losing source identity", () => {
    const reading: EnvironmentReading = { metric: "future_sensor", source: "fixture", device_id: "d1", unit: "custom", value: 0, quality: "valid", observed_at: null, states: ["missing"], target: null, trend_24h: null };
    const html = renderToStaticMarkup(<EnvironmentTable readings={[reading, { ...reading, metric: "irrigation_duration", unit: "s", trend_24h: { kind: "duration_total", count: 2, total: 30 } }]} />);
    expect(html).toContain("future sensor"); expect(html).toContain("0 custom"); expect(html).toContain("valid duration observations"); expect(html).not.toContain("valid volume observations");
  });
  it("uses persisted coverage and never invents history or recipe targets", () => {
    const html = renderToStaticMarkup(<RoomEvidence summary={{ status: "PARTIAL", streams: [{ metric: "temperature", kind: "continuous", snapshot: { connection_id: "fixture-source", mapping_revision: 4 }, coverage_seconds: 60, unknown_seconds: 3540, above_seconds: 0, below_seconds: 0, deviations: [] }] }} />);
    expect(html).toContain("3540"); expect(html).toContain("fixture-source"); expect(html).toContain("Above target seconds: Unknown"); expect(html).toContain("does not establish complete in-target coverage");
  });
  it("labels discrete duration totals separately from continuous averages", () => { const html = renderToStaticMarkup(<RoomEvidence summary={{ streams: [{ metric: "irrigation_duration", kind: "duration", total: 30, unit: "s", unknown_seconds: 3600 }] }} />); expect(html).toContain("Recorded duration total: 30 s"); expect(html).not.toContain("Sample mean"); });
  it("guards unspecified shapes and metric labels", () => { expect(rows(null)).toEqual([]); expect(record("bad")).toEqual({}); expect(metricLabel("future_metric")).toBe("future metric"); });
});

it("does not present threshold-qualified episodes when a threshold is not configured", () => {
  const html = renderToStaticMarkup(<RoomEvidence summary={{ start: 1790294400, end: 1790380800, streams: [{ metric: "future_metric", kind: "continuous", snapshot: { recipe_revision: 1 }, above_seconds: 120, below_seconds: 30, coverage_seconds: 150, unknown_seconds: 86250, deviations: [{ direction: "unqualified-excursion", start: 1, end: 2, seconds: 1 }] }] }} />);
  expect(html).toContain("Cumulative out-of-target seconds: 150");
  expect(html).toContain("Continuous threshold: not configured");
  expect(html).not.toContain("unqualified-excursion");
  expect(html).toContain("2026-");
});
