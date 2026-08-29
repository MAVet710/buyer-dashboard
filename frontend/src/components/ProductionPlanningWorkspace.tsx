import { useEffect, useState } from "react";
import { ProductionPage } from "../pages/ProductionPage";
import "../production-planning.css";
import { ProductionCalendar } from "./ProductionCalendar";
import { ProductionNextActions } from "./ProductionNextActions";
import { ProductionPlanner } from "./ProductionPlanner";

type PlanningView = "Plan" | "Calendar" | "Operations";

const VIEW_COPY: Record<PlanningView, string> = {
  Plan: "See what should run now, what should run next, and what is blocked before opening deeper tools.",
  Calendar: "Place work on a real production calendar and preview labor, machine, material, QA, compliance, and due-date conflicts before committing it.",
  Operations: "Open the deeper production tools for jobs, capacity, resources, BOMs, customers, and performance when the work requires them.",
};

export function ProductionPlanningWorkspace({
  onOpenRun,
  initialView = "Plan",
}: {
  onOpenRun: (orderId: string) => void;
  initialView?: PlanningView;
}) {
  const [view, setView] = useState<PlanningView>(initialView);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  return (
    <div className="page production-planning-workspace">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Production Ops</div>
          <h1>Production Planning</h1>
          <p>
            Decide what runs next, place it on the calendar, and open Run 360
            without losing the production context.
          </p>
        </div>
      </div>

      <div className="view-tabs production-planning-tabs" aria-label="Production planning views">
        {(["Plan", "Calendar", "Operations"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={view === value ? "active" : ""}
            aria-pressed={view === value}
            onClick={() => setView(value)}
          >
            {value}
          </button>
        ))}
      </div>
      <p className="source-caption production-planning-tab-copy">{VIEW_COPY[view]}</p>

      {view === "Plan" ? (
        <>
          <ProductionPlanner onOpenRun={onOpenRun} />
          <ProductionNextActions onOpenRun={onOpenRun} />
        </>
      ) : null}

      {view === "Calendar" ? <ProductionCalendar onOpenRun={onOpenRun} /> : null}

      {view === "Operations" ? (
        <div className="production-planning-operations">
          <ProductionPage />
        </div>
      ) : null}
    </div>
  );
}
