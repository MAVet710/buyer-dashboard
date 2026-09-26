import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConnectionHealthPanel, CultivationPushSetup } from "./CultivationPushSetup";
import { CurrentRoomConditions } from "./CurrentRoomConditions";
import type { Connection, IngressGrants, PushHealth, LatestReading } from "./cultivationIntelligenceTypes";

const connection: Connection = { id: "fixture-push", label: "Fixture producer", mode: "push", provider: "json", version: 3, status: "configured", revoked_at: null, live_supported: false };
const health: PushHealth = { ingress: { grant_state: "active", grants_truncated: false, transport_state: "receiving", last_push_received_at: new Date().toISOString(), last_push_batch_id: "fixture-batch" }, freshness: { basis: "connection_scope_not_room_condition", last_import_at: null, last_received_at: new Date().toISOString(), last_valid_observed_at: "2020-01-01T00:00:00Z", observation_status: "stale", sensor_freshness_status: "unknown", last_provider_contact_at: null, live_connected: false }, connection: { ...connection, stale_after_seconds: 120 }, edge: { last_push_received_at: "2026-09-26T12:00:00Z", last_valid_observed_at: "2020-01-01T00:00:00Z", counts: { pending: 2 } }, live_contract_status: "blocked" };

describe("normalized push operator evidence", () => {
  it("keeps newly received old observations stale and backlog independent", () => {
    const html = renderToStaticMarkup(<ConnectionHealthPanel data={health} />);
    expect(html).toContain("Readings are stale");
    expect(html).toContain("Mapping backlog");
    expect(html).toContain("Last committed push");
    expect(html).not.toContain("Receiving readings");
  });
  it("does not turn imports into push receipt or missing diagnostics into health", () => {
    expect(renderToStaticMarkup(<ConnectionHealthPanel data={{ ...health, ingress: { ...health.ingress!, transport_state: "awaiting", last_push_received_at: null }, edge: { last_received_at: "2026-09-26T12:00:00Z" } }} />)).toContain("Awaiting first reading");
    expect(renderToStaticMarkup(<ConnectionHealthPanel data={{ ...health, edge: null }} />)).toContain("Status unavailable");
  });
  it("allows receiving, mapping backlog and full storage to coexist", () => {
    const html = renderToStaticMarkup(<ConnectionHealthPanel data={{ ...health, freshness: { ...health.freshness!, observation_status: "recent", last_valid_observed_at: new Date().toISOString() }, edge: { ...health.edge, counts: { pending: 3 }, capacity: { state: "full", limiting_resource: "rows" } } }} />);
    expect(html).toContain("Receiving readings");
    expect(html).toContain("Mapping backlog");
    expect(html).toContain("Storage limit reached");
    expect(html).toContain("No hours of remaining collection are estimated");
  });
  it("keeps grants inspectable without mutation controls for a read-only operator", () => {
    const client = new QueryClient();
    const grants: IngressGrants = { grants: [{ id: "g1", connection_id: connection.id, service_account_id: "sa1", label: "Fixture grant", version: 2, created_at: "2026-09-26T12:00:00Z", expires_at: "2027-01-01T00:00:00Z", revoked_at: null, status: "active" }], truncated: false };
    client.setQueryData(["cultivation-intelligence", `/connections/${connection.id}/ingress-grants`], grants);
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><CultivationPushSetup connection={connection} canManage={false} /></QueryClientProvider>);
    expect(html).toContain("Fixture grant");
    expect(html).not.toContain(">Create ingress grant<");
    expect(html).not.toContain(">Revoke Fixture grant<");
    client.clear();
  });
  it("labels a missing zone without claiming room coverage", () => {
    const reading: LatestReading = { connection_id: connection.id, source_device_id: "probe", source_channel: "t", device_id: "d", sensor_id: "s", metric: "temperature", value: 25, unit: "C", original_value: 25, original_unit: "C", observed_at: "2020-01-01T00:00:00Z", received_at: "2026-09-26T12:00:00Z", data_age_seconds: 1000, latency_seconds: 1000, quality: "valid", state: "ready", freshness: "stale", status: "stale", reason: null, snapshot: { organization_id: "fixture-org", facility_id: "fixture-facility", connection_id: connection.id, room_id: "r", device_id: "d", sensor_id: "s", mapping_revision: 1, metric: "temperature", effective_from: "2019-01-01T00:00:00Z", effective_to: "2027-01-01T00:00:00Z", zone_id: null } };
    const html = renderToStaticMarkup(<CurrentRoomConditions roomId="r" latest={{ as_of: "2026-09-26T12:00:00Z", readings: [reading], truncated: false, status: "stale" }} />);
    expect(html).toContain("No zone assigned");
    expect(html).not.toContain("Whole room");
    expect(html).toContain("Current value unknown");
  });
});
