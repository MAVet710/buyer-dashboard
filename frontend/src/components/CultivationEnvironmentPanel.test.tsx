import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { EnvironmentTable, type EnvironmentReading } from "./CultivationEnvironmentPanel";

const reading: EnvironmentReading = { metric: "temperature", source: "manual", device_id: "probe-1", value: 0, unit: "C",
  quality: "valid", observed_at: "2026-01-02T12:00:00Z", states: ["stale", "out_of_range"],
  target: { minimum: 20, maximum: 25, stale_minutes: 60 }, trend_24h: { kind: "continuous", count: 2, min: 0, max: 10, average: 5 } };

describe("cultivation environment evidence", () => {
  it("shows irrigation counts/totals without meaningless averages", () => {
    const html = renderToStaticMarkup(<EnvironmentTable readings={[
      { ...reading, metric: "irrigation_event", unit: "count", states: ["current"], trend_24h: { kind: "event_count", count: 3, total: 3 } },
      { ...reading, metric: "irrigation_volume", unit: "L", trend_24h: { kind: "volume_total", count: 2, total: 4.5 } },
    ]} />);
    expect(html).toContain("3 recorded events");
    expect(html).toContain("Total 4.5 L");
    expect(html).toContain("Recorded");
    for (const label of ["avg", "Min ", "max "]) expect(html).not.toContain(label);
  });
  it("renders zero values, provenance, exceptions and valid trend summaries", () => {
    const html = renderToStaticMarkup(<EnvironmentTable readings={[reading]} />);
    for (const value of ["0 C", "manual", "probe-1", "stale, out of range", "2", "valid readings", "60", "minutes"]) expect(html).toContain(value);
  });
  it("does not turn missing evidence into a zero or healthy reading", () => {
    const html = renderToStaticMarkup(<EnvironmentTable readings={[{ ...reading, value: null, states: ["missing"], observed_at: null, trend_24h: null, target: null }]} />);
    expect(html).toContain("No observation");
    expect(html).toContain("missing");
    expect(html).toContain("No valid readings");
    expect(html).toContain("Not configured");
  });

  it("focuses exact exceptions and exposes canonical Work handoffs", () => {
    const exception = { ...reading, exception_id: "cultivation-telemetry:v1:abc" };
    const createHtml = renderToStaticMarkup(<EnvironmentTable readings={[exception]} canWrite initialExceptionId={exception.exception_id} />);
    expect(createHtml).toContain("Focused exception");
    expect(createHtml).toContain("Create Doobie Work");

    const linkedHtml = renderToStaticMarkup(<EnvironmentTable readings={[{ ...exception, work_item_id: "work-1" }]} canWrite />);
    expect(linkedHtml).toContain("Open Work");
    expect(linkedHtml).toContain("/work?item=work-1");

    const viewerHtml = renderToStaticMarkup(<EnvironmentTable readings={[exception]} canWrite={false} />);
    expect(viewerHtml).toContain("Review required");
    expect(viewerHtml).not.toContain("Create Doobie Work");
  });
});
