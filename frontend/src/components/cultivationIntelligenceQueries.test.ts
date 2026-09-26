import { describe, expect, it } from "vitest";
import { currentEvidenceRefresh } from "./cultivationIntelligenceQueries";

describe("bounded current evidence refresh", () => {
  it("refreshes only current room and selected connection health", () => {
    expect(currentEvidenceRefresh("/rooms/room-1")).toBe(30_000);
    expect(currentEvidenceRefresh("/connections/connection-1/health")).toBe(30_000);
  });
  it.each(["/workspace", "/connections", "/recipes", "/cycles/cycle-1", "/rooms/room-1/zones",
    "/connections/connection-1/ingress-grants", "/rooms/room-1?start=2026-09-01&end=2026-09-02",
    "/connections/connection-1/health?history=true", "/rooms/", "/rooms/one/two"])("does not poll %s", path => {
    expect(currentEvidenceRefresh(path)).toBe(false);
  });
  it("never enables a disabled evidence query", () => {
    expect(currentEvidenceRefresh("/rooms/room-1", false)).toBe(false);
    expect(currentEvidenceRefresh("/connections/connection-1/health", false)).toBe(false);
  });
});
