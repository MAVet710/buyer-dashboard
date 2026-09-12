# Massachusetts Metrc Evaluation — External Prerequisites

Snapshot purpose: identify only the prerequisites that cannot be truthfully manufactured inside DoobieLogic while preserving the already-verified 1–16 task evidence.

## Current checkpoint

- Evaluation run under review: `DL-EVAL-20260912-RESUME-01`
- Reported evidence state: **16 passed / 4 failed / 27 missing of 47**
- Tasks 1–16 remain preserved.
- DoobieLogic's hosted Supabase currently contains **19 connected Metrc integration configurations with encrypted secrets present**. Credential values were not queried or exported.
- GitHub Actions currently has **no values** for `METRC_INTEGRATOR_API_KEY` or `METRC_MA_SANDBOX_USER_API_KEY`; the read-only resume diagnostic therefore failed before any provider request was sent.

## A. Task 17 — plant to plant-batch package

### Confirmed

- Current official MA v2 API exposes `POST /plants/v2/plantbatch/packages`.
- Existing task-17 attempt returned HTTP 401.
- All 18 current synchronized MA sandbox facility profiles in DoobieLogic report `CanCreateImmaturePlantPackagesFromPlants=false`.
- The source plant and reserved package tag must remain untouched until applicability/authorization is resolved.

### Not established

- The exact cause of the 401.
- Whether Metrc must provision a different evaluation facility/capability.
- Whether Massachusetts uses a provider-approved alternative procedure for this workbook step.

### External resolution

Use `artifacts/metrc-evaluation/support/task17-clarification-request.md` if provider clarification is required.

## B. Eligible retail/sales stock

### Confirmed

- A prerequisite `POST /sandbox/v2/packages/create` attempt returned HTTP 401.
- The synchronized provider snapshot currently has **zero present package rows**. Historical package sync exists, but stale/historical rows must not be treated as current provider inventory.
- Package tags are present, but a tag alone is not sellable stock.

### External resolution

Either:

1. identify current eligible package inventory through the authenticated Metrc runtime; or
2. resolve the supported sandbox package-provisioning procedure/provider authorization.

Use `artifacts/metrc-evaluation/support/sandbox-package-seed-request.md` if provider assistance is required.

## C. Transfer / wholesale reference records

### Confirmed

- Current official MA v2 API exposes incoming, outgoing, rejected, delivery, package, and wholesale-package reads required by the workbook.
- The operator blocker review records 54 read-only transfer discovery requests across 18 facilities, all HTTP 200 and all empty.
- DoobieLogic's synchronized Metrc states independently show successful incoming/outgoing/rejected transfer reads with zero records across facility scopes.
- Empty lists do not satisfy workbook tasks that require actual parent/child records.

### External resolution

Metrc must either provide/identify appropriate sandbox fixtures or identify an official procedure by which the integrator can create them.

Use `artifacts/metrc-evaluation/support/transfer-fixture-request.md`.

## D. Eligible lab package / test data

### Confirmed

- Task 30 has no passing provider evidence.
- A lab-related Item does not establish an eligible lab package.
- Current synchronized provider snapshots do not establish an eligible present lab package.
- Current official MA v2 API exposes `POST /labtests/v2/record` and lab test-type reads.

### External resolution

Identify/provision an actual eligible lab package plus legitimate current sandbox test definitions/result procedure.

Use `artifacts/metrc-evaluation/support/lab-package-request.md`.

## Credential execution boundary

DoobieLogic stores Metrc integration credentials encrypted in its application database. They are not copied into this repository or evidence package. GitHub Actions secrets are currently absent, so GitHub-based provider diagnostics cannot run until secrets are deliberately configured.

Do **not** solve this by exporting encrypted application secrets into source control or logs. Either:

- run the resume diagnostics inside the already-authorized DoobieLogic runtime using its normal credential service; or
- deliberately configure the existing GitHub Actions secret names through the repository's secure secret controls.

## Resume condition

Once a prerequisite is resolved, first perform read-only reconciliation against current provider state. Resume only the affected branch of the dependency graph. Do not restart tasks 1–16 and do not blindly retry an uncertain create.
