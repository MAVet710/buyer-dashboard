import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { pageForPath, pathForPage } from "../lib/workspaceRoutes";

const page = readFileSync(new URL("./WorkQueuePage.tsx", import.meta.url), "utf8");
const home = readFileSync(new URL("./HomePage.tsx", import.meta.url), "utf8");
const shell = readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./work-queue.css", import.meta.url), "utf8");

describe("Doobie Work UI contract", () => {
  it("restores the queue and inbox detail route from Home", () => {
    expect(pathForPage("Work Queue")).toBe("/work");
    expect(pageForPath("/work?item=abc")).toBe("Work Queue");
    expect(home).toContain('page: "Work Queue"');
    expect(home).toContain("item.route || item.workspace");
    expect(shell).toContain('label: "Work Queue"');
  });
  it("supports lifecycle, assignment, evidence and linked workspace navigation", () => {
    for (const text of ["Start work", "Block work", "Complete work", "Open / reopen", "Blocked reason", "Evidence / references", "Open linked workspace", "My work", "Overdue", "Due in 24 hours"]) expect(page).toContain(text);
    expect(page).toContain("onNavigate(item.route)");
    expect(page).toContain("version: item.version");
    expect(page).toContain("disabled={!writable || busy}");
  });
  it("uses bounded reads, detail on demand and explicit recurring generation", () => {
    expect(page).toContain('enabled: Boolean(selected)');
    expect(page).toContain('"/api/v1/work/templates/generate"');
    expect(page).toContain("queue.data?.has_more");
    expect(page).toContain("daily"); expect(page).toContain("weekly"); expect(page).toContain("monthly");
    expect(css).toContain("min-height: 44px");
    expect(css).toContain("max-width: 600px");
    expect(page).not.toContain("—");
  });
});
