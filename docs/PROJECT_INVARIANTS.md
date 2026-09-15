# DoobieLogic project invariants

These are standing project rules. Treat them as contract, not suggestions. Any code, Codex task, evaluation rerun, local deployment change, or auth change that conflicts with these rules must fail closed until the conflict is resolved.

## Local-first execution

- The **local stack** is the active DoobieLogic development/evaluation environment unless Nelson explicitly says otherwise; on Nelson's workstation this means the local Windows application stack.
- The active DoobieLogic application compute is hosted from Nelson's Windows PC and exposed publicly through Cloudflare/Cloudflare Tunnel unless Nelson explicitly changes that architecture.
- The verified PC-hosted application request chain is: browser -> Cloudflare HTTPS/Tunnel -> Windows Caddy on loopback `8080` -> built React assets and `/api/*` reverse proxy -> FastAPI on loopback `8010`.
- Durable DoobieLogic production auth/data remain on the existing hosted Supabase project `fovxtygwcxubjzjgovva` at `https://fovxtygwcxubjzjgovva.supabase.co` unless Nelson explicitly changes the data/auth architecture.
- PC-hosted application compute and hosted Supabase auth/data are separate architecture decisions. Do **not** move Supabase Auth to a fresh local `127.0.0.1:54321` instance merely because FastAPI runs on the PC.
- The production browser uses same-origin `/api/*` for DoobieLogic API calls through `ops.doobielogic.io`, while Supabase JS uses the existing hosted Supabase project directly for Auth/session operations.
- The PC-hosted FastAPI backend and production browser must target the same Supabase project and compatible enabled publishable/anon client key.
- Caddy `8080` is the local web/reverse-proxy edge. It is **not** the FastAPI listener. FastAPI is `127.0.0.1:8010`.
- The separate loopback Vite preview uses `4173`; Vite development on `5173` should proxy `/api` and `/health` directly to FastAPI `8010` unless explicitly overridden.
- Port `8000` is not part of the active DoobieLogic PC-hosting contract and must not be assumed to be FastAPI.
- Do not assume Render, Cloud Run, or another hosted application environment is the execution target for local debugging, the live operator app, or the Metrc evaluation unless Nelson explicitly says the hosting architecture changed.
- Hosted **Supabase** is not a retired application host; it remains the production auth/data authority.
- A local failure must be traced through the PC-hosted frontend/Caddy/FastAPI configuration and the existing hosted Supabase project before making deployment or identity changes.

## DoobieLogic username login

- `God` is Nelson's DoobieLogic application username. It is unrelated to Metrc credentials, Metrc facilities, Metrc licenses, or the Metrc API User Key.
- DoobieLogic supports durable username login through `POST /api/v1/account/username-login`.
- Username matching is case-insensitive via `normalized_username`; `God` resolves through `god` while preserving the canonical durable user identity.
- A username is resolved to the durable `app_users` row, then the linked Supabase Auth identity is authenticated in the existing hosted DoobieLogic Supabase project.
- The returned Supabase Auth user id must match the durable DoobieLogic `AppUser.id` before a session is issued.
- The durable `app_users` row and linked `auth.users` identity must preserve the same UUID and linked email. Diagnose the existing identity/link/configuration before creating, recreating, or relinking a user.
- Do not fabricate an email address from a username in the browser.
- Do not silently switch a user from username login to email login.
- Do not create a replacement DoobieLogic user simply because username login fails.
- Never commit, log, or expose the password for `God` or any other user.
- A live `God` login regression must be traced end to end: browser -> Cloudflare Tunnel -> Caddy `8080` -> FastAPI `8010` `/api/v1/account/username-login` -> hosted Supabase Auth project `fovxtygwcxubjzjgovva` -> linked auth identity/session.
- Do not assume a healthy durable user record proves login is healthy. Verify the browser reaches the intended PC-hosted FastAPI process and that FastAPI/browser both point to `https://fovxtygwcxubjzjgovva.supabase.co` with the intended client Auth key.

## Metrc evaluation credentials

- Reuse Nelson's existing active Metrc Vendor/Integrator Key and existing active API User Key for evaluation reruns.
- The existing API User Key is considered active/useable unless direct provider evidence proves otherwise.
- Evaluation code must never call `POST /sandbox/v2/integrator/setup`.
- Evaluation code must never generate, rotate, replace, or overwrite the API User Key.
- `POST /sandbox/v2/integrator/setup` is a separate user-key bootstrap operation using the documented `x-metrc-key` vendor-key header; it is not part of an evaluation rerun.
- A Metrc sandbox data reset does not imply credential invalidation; Metrc states that user/vendor keys are preserved through generic-data resets.
- Never expose raw Metrc keys in logs, JSON evidence, Markdown, CI summaries, or Git history.
- Credential fingerprints are allowed when needed for evidence.
- An action-specific HTTP 401 must not automatically be classified as an invalid key. The workbook explicitly notes that 401 commonly indicates that the action permission is not enabled for the API user.

## Metrc evaluation source of truth

- The actual regulator-provided `Generic_Evaluation_for_All_States_MASTER 10.2025` XLSX is the evaluation contract.
- Current official Massachusetts Metrc v2 documentation is the API contract.
- Postman is only an example client mentioned by Metrc. It is not a special evaluation mode or architecture requirement.
- Live `GET /facilities/v2/` state is the facility/capability routing evidence.
- Provider readback is required before an action can be credited as passed.
- Unit tests, code readiness, or a locally valid payload do not count as regulator evidence.
- Never promote an example, historical assumption, support hypothesis, or diagnostic convention into an evaluation rule without direct workbook/documentation support.

## Evaluation counting

- The workbook contains 46 explicit regulator action rows.
- DoobieLogic retains one additional internal prerequisite: `GET /facilities/v2/`.
- Historical evidence numbering remains 47 internal checks for compatibility.
- Reports must distinguish 46 regulator action rows from 47 internal checks.

## Facility permissions and routing

- Do not force one global Metrc license onto the entire evaluation.
- Discover the facilities visible to the authenticated key pair and select/validate the exact facility appropriate to the specific workbook action.
- The workbook Permissions sheet D/O grid is an access-dependency table. It does **not** create extra regulator action rows and does **not**, by itself, mean that one shared API action must be repeated once for every Grow/Processor/Lab/Sales family.
- Do not multiply the 46 action rows into duplicate runs unless the workbook explicitly creates separate verification rows or Metrc explicitly instructs duplicate execution.
- For a shared section that is valid in several D/O permission contexts, require an explicit facility-family context rather than silently choosing Grow or another family.
- Grow, Processor, Lab, and Sales remain distinct permission/access contexts for diagnosing authorization and selecting valid fixtures/facilities.
- Facility type/capability, API-user permission, vendor permission, fixture availability, credential validity, and request correctness are separate evidence categories.

## Evaluation dependencies

- Do not infer cross-task dependencies that the workbook does not state.
- A blocked Task 17 does not automatically block every later Plants/Harvest task. Each action must be evaluated against the literal workbook wording and the provider objects it actually requires.
- Where the workbook explicitly says "created in Step 1", "using the delivery created above", "package created in Step 1", or equivalent, preserve that exact object identity through subsequent steps and verify it by provider ID/readback.
- Where the workbook allows an existing provider object, do not invent a dependency on an earlier evaluation-created object.

## Evaluation writes

- Refresh current provider state before resuming a branch because generic sandbox data can reset.
- Validate workbook semantics and required source state before dispatch, not merely the JSON schema.
- Persist mutation intent before dispatch where the governed action ledger supports it.
- Send a mutation once.
- Never automatically replay POST, PUT, or DELETE after timeout, ambiguous connection failure, HTTP 429, or HTTP 5xx.
- Ambiguous writes become `RECONCILIATION_REQUIRED` until provider state proves the outcome.
- Do not mutate or delete generic provider data that the evaluation did not create unless the workbook or Metrc explicitly directs it.
- Provider-changing evaluation workers must never run automatically on application import, startup, restart, or deployment.
- HTTP 200 alone is insufficient when the workbook requires a specific field/state change; readback must prove the literal task.
- Do not change the authoritative evaluation score from inferred provider state. Only centralized verified-pass scoring may advance it.

## Literal workbook rules currently enforced

- Plant Batches Step 1: create a new batch containing exactly 6 plants.
- Plant Batches Step 2: package exactly 3 clones from the Step 1 batch.
- Plant Batches Step 3: move exactly 2 plants to Vegetative using individual tags.
- Plant Batches Step 4: destroy/delete exactly 1 plant.
- Plants Step 1: move an existing Flowering Plant to a different location.
- Plants Step 6: use exactly 2 remaining plants to create one harvest; both plants must use the exact same harvest name on the same calendar day.
- Harvest Step 2: remove the remaining harvest weight as waste; moisture loss is explicitly not waste.
- Packages Step 3: the adjustment must result in final package quantity 0 and provider readback must prove quantity 0.
- Package finish/unfinish must operate on the exact evaluation package and verified preceding state.
- Sales Delivery sequence is exactly 3 transactions -> remove 1 so 2 remain -> complete with exactly 1 accepted package and 1 returned package.
- Lab Results requires an eligible existing package in the Lab.
- Transfer/Wholesale find tasks require actual matching provider records; HTTP 200 with an empty result does not pass a find-record task.
- Transfer Templates require two created templates, retrieval of both using the requested date search, required template-linked delivery evidence, and update of one template created in the evaluation.

## Task 17

- Task 17 (`POST /plants/v2/plantbatch/packages`) is one action in the evaluation, not the center of the evaluation architecture.
- Do not mark it N/A.
- Do not infer invalid credentials from its action-specific HTTP 401.
- Do not blindly retry it.
- Keep facility capability, user permission, vendor permission, fixture readiness, request contract, and provider result as separate evidence categories.

## Workbook submission

- Preserve the original 22-sheet workbook and exact sheet names, including intentional trailing spaces.
- `Closed Loop Environment ` is Massachusetts open-loop setup context; `Closed Loop States PlantBatches` remains N/A for MA.
- CompanyInformation alone is not a submission-complete workbook.
- Populate evaluator-owned verification/result fields from real evidence: result code, facility license, provider ID, last-modified value, required name/tag, request, and minified JSON/response as applicable.
- Never modify `Metrc Use Only` cells, regulator formulas, formatting, or unrelated workbook content.
- Raw keys may appear only in the private local submission workbook cells that explicitly require them, never in committed artifacts.

## Regression discipline

- Every confirmed root-cause fix should gain a regression test wherever practical.
- A future agent must read this file before changing authentication, local execution, Metrc evaluation logic, facility routing, credentials, scoring, or workbook submission behavior.
- If code, tests, docs, or prior chat context conflicts with these invariants, stop and resolve the conflict from the authoritative workbook/current docs rather than silently choosing one interpretation.
