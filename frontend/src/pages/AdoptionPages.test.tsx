import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { ImplementationReadinessPage } from "./ImplementationReadinessPage";
import { ScheduledReportsPage } from "./ScheduledReportsPage";
import { pageForPath, pathForPage } from "../lib/workspaceRoutes";

describe("facility adoption pages", () => {
  it("resolves durable routes", () => {
    expect(pageForPath("/settings/implementation")).toBe("Implementation Readiness");
    expect(pathForPage("Scheduled Reports")).toBe("/reports/scheduled");
  });
  it("renders readiness evidence for readers without edit controls", () => {
    const client = new QueryClient();
    client.setQueryData(["implementation-readiness"], { can_manage: false, items: [{ key: "inventory", label: "Starting inventory", status: "incomplete", evidence: "No canonical transactions observed", route: "Data & Settings", manual: false, notes: "Opening count pending", owner: "Operations", target_date: null }] });
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><ImplementationReadinessPage onNavigate={() => {}} /></QueryClientProvider>);
    expect(html).toContain("No canonical transactions observed");
    expect(html).toContain("Opening count pending");
    expect(html).not.toContain("Save review");
  });
  it("renders paused subscriptions and deferred delivery history", () => {
    const client = new QueryClient();
    client.setQueryData(["report-subscriptions", 0], { items: [{ id: "one", report_type: "production", recipients: ["ops@example.com"], cadence: "monthly", active: false, next_run: "2026-10-01T12:00:00Z", last_run: null }] });
    client.setQueryData(["report-delivery-history", 0], { items: [{ id: "run", report_type: "production", recipients: ["ops@example.com"], status: "deferred", detail: "Spacemail unavailable", created_at: "2026-09-01T12:00:00Z" }] });
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><ScheduledReportsPage /></QueryClientProvider>);
    expect(html).toContain("Resume");
    expect(html).toContain("Spacemail unavailable");
    expect(html).toContain("Test delivery");
    expect(html).toContain("Run now");
  });
});
