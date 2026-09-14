# DoobieLogic project invariants

These are standing project rules. Treat them as contract, not suggestions. Any code, Codex task, evaluation rerun, local deployment change, or auth change that conflicts with these rules must fail closed until the conflict is resolved.

## Local-first execution

- The active DoobieLogic development/evaluation environment is the user's local stack unless the user explicitly says otherwise.
- Do not assume Render, Cloud Run, or another hosted environment is the execution target for local debugging or the Metrc evaluation.
- Hosted deployment context may be inspected only when the user explicitly asks for hosted deployment work.

## DoobieLogic username login

- DoobieLogic supports durable username login through `POST /api/v1/account/username-login`.
- Username matching is case-insensitive via `normalized_username`.
- A username is resolved to the durable `app_users` row, then the linked Supabase auth identity is authenticated.
- The returned Supabase auth user id must match the durable DoobieLogic `AppUser.id` before a session is issued.
- Do not fabricate an email address from a username in the browser.
- Do not silently switch a user from username login to email login.
- Do not create a replacement DoobieLogic user simply because username login fails.
- For the current owner/developer account, the intended local login username is `God`. This is a login identifier, not a password or secret. Never commit or log the corresponding password.

## Metrc evaluation credentials

- The existing active Metrc Vendor/Integrator Key and existing active API User Key are reused for evaluation reruns.
- Evaluation code must never call `POST /sandbox/v2/integrator/setup`.
- Evaluation code must never generate, rotate, replace, or overwrite the API User Key.
- A Metrc sandbox data reset does not imply credential invalidation.
- Never expose raw Metrc keys in logs, JSON evidence, Markdown, CI summaries, or Git history.
- Credential fingerprints are allowed when needed for evidence.

## Metrc evaluation source of truth

- The actual regulator-provided `Generic_Evaluation_for_All_States_MASTER 10.2025` XLSX is the evaluation contract.
- Current official Massachusetts Metrc v2 documentation is the API contract.
- Live `GET /facilities/v2/` state is the facility/capability routing contract.
- Provider readback is required before an action can be credited as passed.
- Unit tests, code readiness, or a locally valid payload do not count as regulator evidence.

## Evaluation counting

- The workbook contains 46 explicit regulator action rows.
- DoobieLogic retains one additional internal prerequisite: `GET /facilities/v2/`.
- Historical evidence numbering remains 47 internal checks for compatibility.
- Reports must distinguish 46 regulator action rows from 47 internal checks.

## Facility permissions

- Do not force one global Metrc license onto the entire evaluation.
- The workbook Permissions sheet controls which sections are required for Grow, Processor, Labs, and Sales.
- Sections marked `D` are completed per applicable facility family.
- Shared sections may therefore require execution/evidence in more than one facility family.
- Facility selection must be data-driven from the authenticated Facilities response and the workbook permission matrix.
- Processor, Grow, Lab, and Sales are separate permission families even when one physical sandbox facility exposes multiple capabilities.

## Evaluation writes

- Refresh current provider state before resuming a branch because generic sandbox data can reset.
- Validate workbook semantics before dispatch, not merely the JSON schema.
- Persist mutation intent before dispatch where the governed action ledger supports it.
- Send a mutation once.
- Never automatically replay POST, PUT, or DELETE after timeout, ambiguous connection failure, HTTP 429, or HTTP 5xx.
- Ambiguous writes become `RECONCILIATION_REQUIRED` until provider state proves the outcome.
- Do not mutate or delete generic provider data that the evaluation did not create unless the workbook or Metrc explicitly directs it.

## Task 17

- Task 17 (`POST /plants/v2/plantbatch/packages`) is one example of the broader permission/facility problem, not the center of the project.
- Do not mark it N/A.
- Do not infer invalid credentials from an action-specific HTTP 401.
- Do not blindly retry it.
- Keep facility capability, user permission, vendor permission, fixture readiness, request contract, and provider result as separate evidence categories.

## Workbook submission

- Preserve the original 22-sheet workbook and exact sheet names.
- `Closed Loop Environment ` is Massachusetts open-loop setup context; `Closed Loop States PlantBatches` remains N/A for MA.
- CompanyInformation alone is not a submission-complete workbook.
- Populate evaluator-owned verification/result fields from real evidence.
- Never modify `Metrc Use Only` cells.
- Raw keys may appear only in the private local submission workbook cells that explicitly require them, never in committed artifacts.
