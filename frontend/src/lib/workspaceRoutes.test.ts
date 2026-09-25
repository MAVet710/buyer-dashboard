import { describe, expect, it } from "vitest";
import { entityContextForPath, pageForPath, pathForPage, pathForSearchResult } from "./workspaceRoutes";

describe("global search exact routing", () => {
  const id = "record / + ? # % &";
  it.each(["package", "lot"])("opens %s by canonical lot ID", kind => {
    const path = pathForSearchResult({ kind, id, workspace: "Inventory" });
    expect(pageForPath(path)).toBe("Package 360");
    expect(entityContextForPath(path)).toEqual({ kind: "package", id });
  });
  it("opens the exact production run", () => {
    const path = pathForSearchResult({ kind: "production order", id, workspace: "Production" });
    expect(pageForPath(path)).toBe("Production Run 360");
    expect(entityContextForPath(path)).toEqual({ kind: "production-run", id });
  });
  it.each([
    ["commercial order", "Orders", "order"],
    ["partner", "Orders", "partner"],
    ["plant", "Cultivation", "plant"],
  ])("preserves %s focus in a reloadable browser URL", (kind, page, parameter) => {
    const path = pathForSearchResult({ kind, id, workspace: "Inventory" });
    const url = new URL(path, "https://ops.doobielogic.io");
    expect(pageForPath(url.pathname)).toBe(page);
    expect(url.searchParams.get(parameter)).toBe(id);
    expect(url.hash).toBe("");
    expect(url.origin).toBe("https://ops.doobielogic.io");
  });
  it("keeps known tools and unknown workspaces fail closed", () => {
    expect(pathForSearchResult({ kind: "tool", id: "orders", workspace: "Orders" })).toBe(pathForPage("Orders"));
    const path = pathForSearchResult({ kind: "unknown", id, workspace: "Missing workspace" });
    expect(pageForPath(path)).toBeNull();
    expect(pageForPath("/wholesale/orders/unknown/extra")).toBeNull();
    expect(pageForPath("/production/runs/one/extra")).toBeNull();
  });
});
