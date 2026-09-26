# Real local cultivation browser acceptance

This harness mounts the existing React fixture entry and application stylesheet,
serves the current cultivation-intelligence FastAPI router over real HTTP, and
uses a fresh SQLite database upgraded through the complete Alembic head chain.
It does not substitute API responses, domain services, authentication context,
database dependencies, or EdgeStore responses. The isolated FastAPI app deliberately
registers only the cultivation-intelligence router, with no production startup
workers. It is not a full production middleware or Supabase login acceptance test.

Run from the repository root with the approved interpreter:

```powershell
& 'C:\Users\ndasi\.codex\worktrees\ceec\repo-next-20260912-174618\.pilot-venv\Scripts\python.exe' scripts/acceptance/cultivation_intelligence_browser.py
```

Use `--evidence-root <authorized-directory>` to place the uniquely named run
directory beneath a chosen directory. The default is an isolated system temporary
directory. This session could not create the requested
`C:\Users\ndasi\Documents\DoobieLogic\release-evidence\cultivation-intelligence-20260926\real-browser`
directory: the filesystem sandbox returned access denied. No permission was relaxed.

The runner checks that loopback ports 8016 and 4198 are free before migrating or
launching. Vite uses `--strictPort`, disables environment-file loading, blanks
Supabase/browser API configuration, and proxies `/api` only to 127.0.0.1:8016.
Installed headless Chrome runs the cases with one worker and no retries. Browser
requests outside loopback are aborted and fail acceptance. Python's outbound
socket guard also rejects non-loopback connections. The child environment is
allowlisted and explicitly sets test mode, both isolated SQLite URLs, an isolated
local edge path, cloud fallback false and startup seeding false. Settings disable
`.env` reading before router imports. No credentials or production data are read.

The Vite fixture uses native TypeScript configuration loading. A narrowly scoped
dependency resolver reads installed relative dependency files with Node because
esbuild's native resolver probes inaccessible worktree ancestors in this sandbox.
Bare package imports retain Vite/esbuild's normal browser resolution. No dependency
installation or application component change is needed.

Fixture data consists of a synthetic organization, cultivation-enabled facility,
room, two canonical plants, active `web-local-developer` admin and a read-only
principal. Browser request headers go through actual development authentication,
facility capability and permission checks. Development auth does not exercise
the bearer-token AppUser/Supabase login branch; the real AppUser exists for actor
references and permissions. Connection, device and sensor setup use actual HTTP
mutations, recorded in `setup-http.json`. Historical recipe stages and targets are
inserted while the recipe is draft, then approved with a past effective timestamp
before cycle, membership, occupancy and mapping fixtures are inserted. These are
explicit historical fixture records, not claims of a real vendor connection.

Eight cases cover 390px and 1280px viewports:

- Canonical plant count and stage, exact room URL, UI cycle creation, real HTTP
  readback and reload.
- UI JSON preview and digest-confirmed commit; accepted, unknown-device pending,
  and future-observation quarantine counts; local evidence readback preserving 77 F,
  normalized 25 C, exact room and cycle attribution.
- Exact room/cycle dialogs, historical partial coverage and 25 C mean, current
  normalized conditions and reload. Missing current data fails.
- Canonical plant links, explicitly unknown individual exposure, missing room
  404 without fallback, read-only controls and real mutation 403. Read-only browser
  routing changes request identity headers only, never response bodies.

Per-case JSON contains viewport, synthetic scope, actual API methods/paths/status,
request origins, page errors, horizontal overflow and failures. Synthetic screenshots,
local evidence, migration/API/Vite/browser logs and the Playwright report are stored
outside the repository. `receipt.json` records base SHA, uncommitted state before and
after, run status and cleanup verification. A failed or interrupted run is never
promoted to acceptance. Windows job objects contain only runner-owned processes;
cleanup stops their descendants and checks both listener ports. Creating a
`stop-requested` file inside the current evidence directory ends the browser run as
failed and cleans up the owned job.

No inventory, Metrc, equipment or automatic Work actions are requested. No commit,
push, deployment, DNS, Caddy, scheduled task or production port changes occur.

## Observed result

On September 26, 2026, the completed run at base SHA
`24b615def545e6c7103e55e1d4f27d4a11b93e16` produced **6 passed, 2 failed**.
The receipt records the actual uncommitted working-tree state. This is a failed
application acceptance result, not release verification. No test was skipped.

Both failing cases are the required current-condition integration check, at 390px
and 1280px. Reproduction: seed the historical context, UI-preview and commit a
registered 77 F observation timestamped three seconds before the run, then open
the exact Room 360 Environment tab and reload. The local evidence is ready with
canonical 25 C and the exact cycle/room snapshot. Historical cycle and room
aggregates render a 25 C mean with partial coverage. However, the room response's
`environment.readings` contains legacy missing-observation entries rather than
the imported 25 C stream, and the UI table does not show 25 C before or after
reload. `TelemetryGatewayService.room()` currently adds aggregate summaries but
does not merge `EdgeStore.latest()` into the current-condition response. The
test intentionally fails until that promised integration is wired.

Passing cases at both sizes verify canonical room plant count 2, current stage,
UI-created cycle readback/reload, actual preview/commit, accepted 2 / pending 1 /
quarantined 1, the future-observation reason, local raw 77 F to canonical 25 C,
exact room/cycle attribution, UI-triggered historical rollup, plant relationship
URLs, exact missing-room 404 and read-only mutation 403. The API setup also used
real HTTP for connection, device and sensor registration. No unexpected API status,
server 5xx, page error, non-loopback request or document horizontal overflow was
observed. Both owned listeners were confirmed stopped after the run.

Screenshot inspection found an additional visual limitation: existing fixture
windows have a computed transparent background with an unset `--surface` variable,
so background text shows through and simultaneous room/cycle windows overlap
visually, especially at 390px. Computed window styles are recorded in case JSON.
The six functional passes are not a claim of complete visual acceptance. Neither
the existing fixture entry nor application styles were modified to conceal this.

Harness iteration failures are retained in separate temporary run directories.
Those include dependency-optimizer configuration, the missing explicit import
mapping in an early test input, and a fixture timestamp formatted with `+00:00`
instead of the UI's required `Z`. These were corrected in the owned harness;
they are not reported as product regressions.

Final candidate run: **6 passed, 2 failed in 18.2 seconds**, process exit 1.
Evidence directory:
`C:\Users\ndasi\AppData\Local\Temp\cultivation-real-browser-0qf18k5n`.
Start with `receipt.json`, `playwright.json`, `room-response-390.json`,
`room-response-1280.json`, both `edge-normalization-*.json` files and the
`cycle-coverage-*.png` screenshots. There are 88 recorded real API responses
across the eight browser cases, plus three setup HTTP mutations. API 8016 and
Vite 4198 both had no listener after owned-job cleanup.

## Primary integrated rerun after repairs

The earlier failure record above is retained as historical evidence. The primary rerun on September 26, 2026 passed **10 of 10 actual React/FastAPI browser cases**, zero skipped, with both 390px and 1280px covered. It used the trusted Python executable and the same guarded synthetic loopback harness. Both owned listeners, 8016 and 4198, were confirmed closed afterward.

The repaired contract exposes current local sensor readings through `edge_latest`, separately from legacy manual observations and historical aggregates. The tests now inspect that exact response and the Latest sensor readings region before and after reload. Invalid future evidence uses a separate source so it cannot conceal a genuine invalid-latest regression. Two new real-HTTP cases copy an approved recipe, save and approve a new version, and verify the original standards remain unchanged. A selector encoding error in an intermediate run was corrected without changing application behavior.

The shared popup surface correction is included in this rerun. Dedicated popup acceptance separately passed six Chrome cases covering both themes, mobile/desktop, solid computed surfaces and popup interaction preservation. See `POPUP_READABILITY.md`.

The final primary rerun receipt is retained privately under `real-browser-final/cultivation-real-browser-uccyr_3w/receipt.json` in the program evidence directory. This is an integrated local synthetic acceptance result, not a Supabase production-login or PC release claim. Final GitHub/PostgreSQL gates and authenticated PC/public acceptance remain mandatory.
