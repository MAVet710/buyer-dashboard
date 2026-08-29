import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const workspace = readFileSync(new URL("./ProductionPlanningWorkspace.tsx", import.meta.url), "utf8");
const calendar = readFileSync(new URL("./ProductionCalendar.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const home = readFileSync(new URL("../pages/HomePage.tsx", import.meta.url), "utf8");

describe("Production Planning UX", () => {
  it("keeps production simple on top without removing deep operations", () => {
    expect(workspace).toContain("<h1>Production Planning</h1>");
    expect(workspace).toContain('["Plan", "Calendar", "Operations"]');
    expect(workspace).toContain("<ProductionPlanner onOpenRun={onOpenRun} />");
    expect(workspace).toContain("<ProductionCalendar onOpenRun={onOpenRun} />");
    expect(workspace).toContain("<ProductionPage />");
  });

  it("uses a literal month calendar with conflict-aware scheduling", () => {
    expect(calendar).toContain("production-calendar-grid");
    expect(calendar).toContain("monthGrid(cursor)");
    expect(calendar).toContain(">Previous</button>");
    expect(calendar).toContain(">Today</button>");
    expect(calendar).toContain(">Next</button>");
    expect(calendar).toContain("Preview Schedule");
    expect(calendar).toContain("Commit Schedule");
  });

  it("keeps the production workspace code split and removes Co-Man from the home task", () => {
    expect(app).toContain('lazy(() => import("./components/ProductionPlanningWorkspace")');
    expect(app).toContain('initialView="Calendar"');
    expect(home).toContain('label: "Plan production"');
    expect(home).not.toContain('label: "Plan Co-Man production"');
  });
});
