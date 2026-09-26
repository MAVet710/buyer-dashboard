import { readSourcePreview, historicalWindow } from "./telemetryReview";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NormalizedPreviewTable, type PreviewSample } from "./telemetryMappingTable";
import { ImportedDeviationWork } from "./ImportedDeviationWork";
const sample: PreviewSample = { row_index: 0, source_device_id: "device@room", source_channel: "temp", source_metric: "vendor_temp", original_value: "077.00", original_unit: "F", normalized_value: 25, normalized_unit: "C", metric: "temperature", observed_at: "2026-09-25T00:00:00Z", room_id: "room", room_name: "Flower room", zone_id: null, zone_name: null, cycle_id: "crop", cycle_name: "Fall crop", status: "normalized_not_committed" };
describe("guided source review", () => {
  it("preserves CSV strings and quoted source channels without column inference", () => {
    const rows = readSourcePreview('event_id,source_device_id,source_channel,source_metric,value,unit,observed_at\r\ne1,d1,"temp,inside",vendor_temp,077.00,F,2026-09-25T00:00:00Z\r\n', "csv");
    expect(rows[0].value).toBe("077.00"); expect(rows[0].source_channel).toBe("temp,inside");
    expect(() => readSourcePreview("time,temp\nnow,77", "csv")).toThrow("documented source");
  });
  it("bounds files and rejects mismatched CSV columns", () => {
    expect(() => readSourcePreview(JSON.stringify(Array(501).fill({})), "json")).toThrow("500");
    expect(() => readSourcePreview("x".repeat(1048577), "csv")).toThrow("1 MiB");
    expect(() => readSourcePreview("event_id,source_device_id,source_channel,source_metric,value,unit,observed_at\ne1,d1", "csv")).toThrow("columns");
  });
  it("shows original and server normalized samples with named destinations", () => {
    const html = renderToStaticMarkup(<NormalizedPreviewTable samples={[sample]} truncated />);
    for (const text of ["077.00", "25 C", "Flower room", "Fall crop", "No zone assigned", "Normalized, not committed", "first 20"]) expect(html).toContain(text);
    expect(html).not.toContain("Whole room");
  });
  it("keeps invalid and future quality states unavailable", () => {
    const html = renderToStaticMarkup(<NormalizedPreviewTable samples={[{ ...sample, normalized_value: null, status: "invalid_measurement" }, { ...sample, row_index: 1, normalized_value: 25, status: "unknown" }]} truncated={false} />);
    expect(html).toContain("Check value, quality, unit and timestamp"); expect(html).toContain("Unavailable"); expect(html).not.toContain("25 C");
  });
});
const window = { start: "2026-09-25T00:00:00.000Z", end: "2026-09-25T01:00:00.000Z" };
function renderWork(capability: boolean | undefined, work: string | null = null, truncated = false) {
  const client = new QueryClient();
  client.setQueryData(["cultivation-intelligence", `/rooms/room/deviations?${new URLSearchParams(window)}`], { window, can_create_work: capability, truncated, items: [{ exception_id: "exception", metric: "temperature", direction: "above", duration_seconds: 600, threshold_seconds: 120, started_at: window.start, ended_at: window.end, work_item_id: work, return_route: "/cultivation?room=room&edge_exception=exception" }] });
  const html = renderToStaticMarkup(<QueryClientProvider client={client}><ImportedDeviationWork roomId="room" summary={window} canManage focus="exception" /></QueryClientProvider>); client.clear(); return html;
}
it("offers review only for effective server Work creation capability", () => {
  expect(renderWork(true)).toContain("Review Work action");
  expect(renderWork(false)).not.toContain("Review Work action");
  expect(renderWork(undefined)).not.toContain("Review Work action");
  expect(renderWork(true)).not.toContain("Create Doobie Work");
});
it("opens existing completed links even without write eligibility and fails closed on truncation", () => {
  expect(renderWork(false, "completed-id")).toContain("/work?item=completed-id");
  expect(renderWork(true, null, true)).not.toContain("Review Work action");
});
it("uses persisted window timestamps and leaves invalid windows empty", () => {
  expect(historicalWindow({ start: Date.parse(window.start) / 1000, end: Date.parse(window.end) / 1000 })).toEqual(window);
  expect(historicalWindow(null)).toEqual({ start: "", end: "" });
});
