import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { EnvironmentTable, type EnvironmentReading } from "./CultivationEnvironmentPanel";

const reading: EnvironmentReading = { metric: "temperature", source: "manual", device_id: "probe-1", value: 0, unit: "C",
  quality: "valid", observed_at: "2026-01-02T12:00:00Z", states: ["stale", "out_of_range"],
  target: { minimum: 20, maximum: 25, stale_minutes: 60 }, trend_24h: { count: 2, min: 0, max: 10, average: 5, total: 10 } };

describe("cultivation environment evidence", () => {
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
});
