# Production Planning UX

DoobieLogic's human-facing production workspace is **Production Planning**.

The product rule is simple: **complex underneath, simple and fast on top**. Operators should first see what should run, what is blocked, and where work sits on the calendar. Detailed configuration stays available when the job requires it.

The Plan view must use a bounded planning read model. It must not build the decision table by fetching full Run 360 detail once per production order. Production Run 360 remains the detailed hydration point when the operator opens a run. Performance work must preserve the visible planning UI and the existing decision/safety semantics.

## Workspace model

Production Planning exposes three top-level views:

1. **Plan** — decision-first view for what should run now, next, or needs intervention.
2. **Calendar** — literal month calendar for scheduled production with conflict-aware placement.
3. **Operations** — deeper job, capacity, resource, BOM, customer, and performance tools.

Production Run 360 remains a contextual work window so an operator can inspect a run without leaving Production Planning.

## Co-Man terminology

Co-manufacturing remains a valid **workflow / order type** for customer-owned or contract production. It is no longer the name of the entire production workspace.

Existing `coman` / `coman-parity` module, database, and API identifiers remain intact as compatibility implementation details. Renaming internal identifiers would add migration and regression risk without improving the operator experience.

## Calendar safety contract

The calendar is intentionally not a cosmetic scheduler. A placement must use the existing preview-and-commit path so DoobieLogic can surface conflicts involving:

- BOM cycle standards
- material readiness and reservations
- labor / crew capacity
- machine assignments and conflicts
- QA requirements
- compliance checkpoints
- due dates

The UI hides these checks until they matter, but does not bypass them.

## Future calendar interactions

Drag-and-drop rescheduling is a useful future enhancement only if it preserves the same preview-and-commit contract. A drag action should propose a change, show any relevant blockers or warnings, and require the same safe commit path rather than silently moving production work.
