import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { AppShell } from "./AppShell";
import { OrdersPage } from "../pages/OrdersPage";
import { PlantInventory } from "./PlantInventory";

vi.mock("./GlobalSearch", () => ({ GlobalSearch: () => null }));
vi.mock("./WorkspaceAgent", () => ({ WorkspaceAgent: () => null }));
vi.mock("../lib/supabase", () => ({ supabase: null }));
vi.mock("./WorkspaceWindow", () => ({ WorkspaceWindow: ({ open, title }: { open: boolean; title: string }) => open ? <section aria-label="Plant 360">{title}</section> : null }));
vi.mock("./CultivationToday", () => ({ CultivationToday: () => null }));
vi.mock("./CultivationBatchManager", () => ({ CultivationBatchManager: () => null }));
vi.mock("./CultivationOperationsControl", () => ({ CultivationOperationsControl: () => null }));
vi.mock("./CultivationIntelligencePanel", () => ({ CultivationIntelligencePanel: () => null }));
vi.mock("./CultivationRegulatoryHealth", () => ({ CultivationRegulatoryHealth: () => null }));
afterEach(() => vi.unstubAllGlobals());

describe("Cultivation commercial navigation", () => {
  it.each([false, true])("respects commercial capability in flat and classic navigation: %s", commercial => {
    for (const classic of [false, true]) {
      vi.stubGlobal("localStorage", { getItem: (key: string) => key === "buyer-dash-operation" ? "Cultivation Ops" : key === "buyer-dash-classic-navigation" ? String(classic) : null });
      const client = new QueryClient();
      client.setQueryData(["account-context"], { user: { role: "operator" }, facilities: [{ id: "grow", capabilities: { cultivation: true, commercial } }], facility_id: "grow", capabilities: { cultivation: true, commercial } });
      const html = renderToStaticMarkup(<QueryClientProvider client={client}><AppShell active="Orders" onNavigate={() => {}} /></QueryClientProvider>);
      expect(html.includes("Orders &amp; Fulfillment")).toBe(commercial);
      expect(html.includes("Warehouse Pick / Pack")).toBe(commercial);
      expect(html).not.toContain(">Admin Tools<");
      expect(html).toContain("Cultivation Ops");
      client.clear();
    }
  });
});

describe("commercial record focus", () => {
  const workspace = { facility_name: "Grow", metrics: { inventory_value: 0, tracked_lots: 0, open_sales_value: 0, open_purchase_value: 0, fill_rate_pct: 0, overdue_orders: 0, inventory_exceptions: 0 }, partners: [{ id: "partner-a", name: "Canonical customer", partner_type: "customer" }], orders: [], products: [], lots: [], transactions: [], inventory_exceptions: [] };
  function render(orderId = "", partnerId = "") {
    const client = new QueryClient();
    client.setQueryData(["commercial-workspace"], workspace);
    client.setQueryData(["commercial-order", "order-a"], { order: { id: "order-a", partner_id: "partner-a", order_number: "SO-COMPLETE", status: "fulfilled" }, lines: [{ description: "Exact order line", quantity: 2, fulfilled_quantity: 2, unit: "ea" }] });
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><OrdersPage initialOrderId={orderId} initialPartnerId={partnerId}/></QueryClientProvider>);
    client.clear();
    return html;
  }
  it("shows the selected completed order using its detail, even outside the open board", () => {
    const html = render("order-a");
    expect(html).toContain("SO-COMPLETE");
    expect(html).toContain("Exact order line");
    expect(html).toContain("Canonical customer");
    expect(html).not.toContain("NaN");
  });
  it("focuses the canonical partner and handles missing IDs without selecting another", () => {
    expect(render("", "partner-a")).toContain("Canonical customer");
    expect(render("", "missing")).toContain("The requested partner is not available");
    expect(render("", "missing")).not.toContain("<h3>Canonical customer</h3>");
  });
});

it("opens only the requested plant and leaves bulk selection empty", () => {
  const client = new QueryClient();
  client.setQueryData(["plants-overview"], [{ id: "plant-a", plant_tag: "TAG-A", room_code: "ROOM-A" }, { id: "plant-b", plant_tag: "TAG-B", room_code: "ROOM-B" }]);
  const render = (id: string) => renderToStaticMarkup(<QueryClientProvider client={client}><PlantInventory initialPlantId={id}/></QueryClientProvider>);
  expect(render("plant-b")).toContain('aria-label="Plant 360">TAG-B');
  expect(render("plant-b")).not.toContain("plant(s) selected");
  expect(render("missing")).toContain("The requested plant is not available");
  expect(render("missing")).not.toContain('aria-label="Plant 360"');
  client.clear();
});

it("wires exact plant focus and remounts entity state when browser URLs change", () => {
  const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
  const plant = readFileSync(new URL("./PlantInventory.tsx", import.meta.url), "utf8");
  expect(app).toContain('key={packageCode || "package-picker"}');
  expect(app).toContain('key={[focus.get("plant"), focus.get("room"), focus.get("telemetry")].filter(Boolean).join(":") || "grow"}');
  expect(app).toContain('initialRoomId={focus.get("room") || ""}');
  expect(app).toContain('initialTelemetryId={focus.get("telemetry") || ""}');
  expect(app).toContain('<OrdersPage key={location.search}');
  expect(app).toContain('pendingPath === location.pathname + location.search');
  expect(plant).toContain('overview.data?.find(plant => plant.id === initialPlantId)');
  expect(plant).toContain('selectedPlant === undefined ? focusedPlant ?? null : selectedPlant');
});
