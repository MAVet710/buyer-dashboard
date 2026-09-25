# Doobie Work foundation

Work Queue is available from Home and the Home navigation at `/work`. Tasks are scoped to the authenticated organization and active facility. Entity type, entity ID, workspace and local route are references only; completing work never changes linked inventory, production or compliance records.

## Permissions and lifecycle

The existing `dev`, `admin`, `buyer`, `planner`, `supervisor`, `operator` and `qa` roles may create, assign and change work in their authorized facility. Other roles can read but cannot mutate. Assignees must be active users in the same organization with a work-capable facility assignment, or organization administrators/developers. Cross-organization developer access does not make that developer an eligible assignee in another organization.

Work moves between open, in progress, blocked and completed. Blocking requires a reason. Completion records actor and time. Reopening clears completion attribution while retaining the historical audit event and evidence. Assignment can be cleared. Every update requires the last observed version; stale edits return HTTP 409. All work mutations and their before/after audit entries commit in the same transaction through `modules/coman/audit.py`. Notes and evidence edits retain previous values in that ledger. No deletion API is exposed.

## Recurrence

Templates retain a timezone-aware start, optional inclusive end, daily/weekly/monthly frequency and durable occurrence cursor. Schedules are evaluated in UTC. Daily and weekly work retains UTC time across daylight saving changes. Monthly work uses the original day and clamps to the month's last day without drifting later months. The UI accepts local times and converts them to UTC.

`POST /api/v1/work/templates/generate` generates due occurrences through server time in one transaction. Use the Work Queue's **Generate due work** action on each operating day, or invoke the same authenticated API from an approved internal process. GET requests and Home rendering do not generate work. No external scheduler, provider, startup worker or notification service is required.

Generation considers at most 100 active templates and creates at most 100 occurrences per request. Template checks rotate by last update to avoid starving later templates. Repeat while `may_have_more` is true; it is a conservative batch indicator. Locks, version checks, and the unique `(template_id, occurrence_at)` constraint prevent duplicate occurrences. A failed transaction leaves the cursor unchanged. A lost successful response is safe to retry. Paused templates retain their cursor and catch up when resumed. Resuming an ended template does not extend its end date. Create a replacement template to change cadence or end date; existing occurrences remain unchanged.

An inactive or no-longer-eligible template assignee blocks that generation transaction with an actionable validation error. Repair the template assignment with PATCH, or pause the template, then retry. Template assignment changes affect only subsequent occurrences.

## API

All endpoints require the existing request context and organization/facility headers.

| Endpoint | Behavior |
| --- | --- |
| GET /api/v1/work | Filter by view, status, priority, assignee_id, workspace, entity_type, entity_id; limit 1-100, offset pagination |
| POST /api/v1/work | Create work with link metadata and optional assignment, due time, notes and evidence |
| GET /api/v1/work/{id} | Hydrate description, notes and evidence only on inspection |
| PATCH /api/v1/work/{id} | Versioned status, priority, assignment, due time, blocked reason, notes or evidence changes |
| POST /api/v1/work/{id}/complete | Complete with `{ "version": 1 }` |
| POST /api/v1/work/{id}/reopen | Reopen with the current version |
| GET /api/v1/work/assignees | Bounded eligible user selector, 500 rows and has_more |
| GET /api/v1/work/templates | Bounded template page, 50 rows and has_more |
| POST /api/v1/work/templates | Create a durable recurrence definition |
| PATCH /api/v1/work/templates/{id} | Versioned active state or assignee_id change |
| POST /api/v1/work/templates/generate | Bounded, repeatable generation through server time |

Views: `all`, `mine` (my unfinished work), `due` (unfinished work due in the next 24 hours), `overdue` (unfinished work past due), and `attention` (my unfinished overdue/high/critical work). Assignment and other filters combine with the selected view. Queue responses omit large text; the Home Inbox adds at most 20 assigned attention items while retaining existing exception behavior.

## Schema and release

`0080_doobie_work` follows `0079_security_observation`. It adds `doobie_work_items` and `doobie_work_templates`, scoped queue indexes, lifecycle checks and a unique recurrence occurrence constraint. No existing domain rows are rewritten. Browser database roles have no table access; RLS is enabled and the existing server runtime identity receives SELECT/INSERT/UPDATE grants. Server-side tenant and facility predicates remain mandatory. The migration refuses downgrade when work records exist; roll back application code while retaining this additive schema.

This implementation is a local candidate only. Integration must validate the migration on PostgreSQL and the authenticated PC-hosted workflow before any release claim. The implementation-worker scope explicitly excludes deployment.

## Candidate verification

Local validation passed: 97 focused and broader Python tests, 110 frontend unit/contract tests, frontend lint, production build, and three synthetic Playwright checks covering lifecycle, mobile navigation/layout and read-only behavior. Alembic reports the single head `0080_doobie_work`. Schema checks include SQLite upgrade/model parity and PostgreSQL DDL generation; no production database migration was executed.

Run the browser checks against an isolated development server on `127.0.0.1:5179` with `pnpm exec playwright test --config playwright.work.config.ts`. They intercept API traffic with synthetic fixtures and do not authorize provider or production mutations.
