import { describe, expect, it } from "vitest";
import { isOfflineReplayAllowed } from "./offlineQueue";

describe("offline replay safety policy", () => {
  it("allows only the approved tenant-scoped inventory audit count replay routes", () => {
    expect(isOfflineReplayAllowed("/api/v1/inventory/retail/audits/audit-123/scan/count/replay", "physical_capture")).toBe(true);
    expect(isOfflineReplayAllowed("/api/v1/inventory/production/audits/audit-456/scan/count/replay", "physical_capture")).toBe(true);
  });

  it("blocks generic drafts and non-approved local mutations even when classified as physical capture", () => {
    const blocked = [
      "/api/v1/inventory/retail/audits/audit-123/counts",
      "/api/v1/production/drafts",
      "/api/v1/inventory/retail/audits/audit-123/scan/preview",
      "/api/v1/inventory/retail/audits/audit-123/complete",
    ];
    for (const path of blocked) {
      expect(isOfflineReplayAllowed(path, "physical_capture")).toBe(false);
    }
    expect(isOfflineReplayAllowed("/api/v1/inventory/retail/audits/audit-123/scan/count/replay", "local_draft")).toBe(false);
  });

  it("blocks regulatory and provider-changing routes", () => {
    const blocked = [
      "/api/v1/traceability/actions",
      "/api/v1/inventory/regulatory",
      "/api/v1/metrc/packages",
      "/api/v1/integrations/metrc",
      "/api/v1/wholesale/manifest/create",
      "/api/v1/transfer/dispatch",
    ];
    for (const path of blocked) {
      expect(isOfflineReplayAllowed(path, "physical_capture")).toBe(false);
    }
  });

  it("rejects non-DoobieLogic API paths", () => {
    expect(isOfflineReplayAllowed("https://example.com/write", "physical_capture")).toBe(false);
    expect(isOfflineReplayAllowed("/health", "physical_capture")).toBe(false);
  });
});
