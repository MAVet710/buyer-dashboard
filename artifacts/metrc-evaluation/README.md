# Massachusetts Metrc Evaluation Finalization

This directory contains DoobieLogic's fail-closed execution and submission workflow for the regulator-provided `Generic_Evaluation_for_All_States_MASTER 10.2025.xlsx`.

The original workbook has **46 explicit Massachusetts regulator action rows** plus a mandatory `GET /facilities/v2` facilities/permissions prerequisite. DoobieLogic keeps the existing internal numbering **1-47** so historical evidence remains stable: internal check 1 is the facilities prerequisite and internal checks 2-47 map to the 46 workbook action rows.

A local package may say **`ready_for_metrc_review`** only when all 47 internal checks have valid evidence, required CompanyInformation is complete, the Permissions request table is populated, and all 46 visible regulator verification rows are filled. It never claims Metrc approval.

## Non-negotiable rerun rules

- **Reuse the existing active MA sandbox User API Key.**
- Do **not** call `/sandbox/v2/integrator/setup` during an evaluation rerun.
- Do **not** generate, rotate, replace, or silently switch the User API Key.
- `GET /facilities/v2` is the mandatory first provider check for the active User API Key.
- The workbook states that a permission-disabled action will typically return **HTTP 401 Unauthorized**.
- Do **not** use one global facility license for Grow, Lab, Sales, and Transfer actions. The workbook's `D` permissions are per facility/profile.
- Every non-context action must select an explicit facility license and that license must be returned exactly once by the fresh Facilities response.
- For Grow/Lab/Sales families the runner also validates the relevant provider capability before sending the bounded action.
- Task 17 retains its stricter `CanCreateImmaturePlantPackagesFromPlants` preflight and must not be retried while that capability is false.
- Only modify data Metrc directs you to and data created for the evaluation. Never delete unrelated sandbox data.
- Every regulator action must return HTTP 200 and be verifiable before submission.

## Workbook permission dependencies

`D` means dependent/required for the selected facility/profile; `O` means optional.

- **Grow:** Locations, Strains, Plant Batches / Plants, Harvests, Items, Packages, GET Transfers / Wholesale. Transfer Templates optional.
- **Processor:** Strains, Items, Packages, GET Transfers / Wholesale. Transfer Templates optional.
- **Labs:** Strains, Packages, Labs, GET Transfers / Wholesale. Items and Transfer Templates optional.
- **Sales:** Strains, Items, Packages, Sales, Sales Deliveries, GET Transfers / Wholesale. Transfer Templates optional.

Massachusetts is an **Open Loop** state in this workbook. `Closed Loop Environment ` is therefore a required setup/context sheet for MA beginning-inventory directions even though `Closed Loop States PlantBatches` is not an MA action sheet.

## Safety boundary

A task/check passes finalization only when its selected evidence records:

- `state = MA`
- `environment = sandbox`
- `http_status = 200`
- `stage = complete`
- `passed = true`

Additional protections:

- missing/failed evidence keeps the package `not_ready`;
- a later complete passing retry may supersede an earlier failed attempt for the same internal check;
- credential-like fields in evidence are rejected;
- Vendor/User API keys are never accepted by `finalize_report.py` and are never written to redacted manifests;
- the Vendor/User API keys enter only the local CompanyInformation workbook copy through environment variables;
- the completed XLSX, local company JSON, evidence directory, manifests, and generated final reports are gitignored and must remain local;
- `Metrc Use Only` cells are never modified by DoobieLogic's workbook writers.

## Files

- `company.example.json` — safe template for non-secret CompanyInformation values.
- `finalize_report.py` — builds the canonical redacted readiness report from local evidence.
- `preserve_workbook.py` — fills CompanyInformation and the two local key fields while preserving the regulator XLSX structure.
- `fill_workbook_results.py` — after all evidence passes, fills the Permissions request table and B:H on the 46 visible regulator `Step` rows. It refuses failed/non-200 evidence and never touches `Metrc Use Only`.
- `verify_final.mjs` — verifies the 47 internal checks, the CompanyInformation preservation manifest, and the verification-results manifest.
- `../../scripts/run_ma_metrc_evaluation.py` — bounded MA sandbox evaluator.
- `../../services/metrc_evaluation_instruction_contract.py` — regulator instruction/D-O dependency/rerun policy source of truth.

## 1. Prepare local CompanyInformation

```powershell
Copy-Item artifacts/metrc-evaluation/company.example.json artifacts/metrc-evaluation/company.local.json
```

or:

```bash
cp artifacts/metrc-evaluation/company.example.json artifacts/metrc-evaluation/company.local.json
```

Complete the non-secret company/contact fields. Never put the Vendor or User API key in this JSON.

## 2. Make the existing sandbox key pair available locally

Use the already-active keys. Do not regenerate them.

### PowerShell

```powershell
$env:METRC_INTEGRATOR_API_KEY = "<existing vendor key>"
$env:METRC_USER_API_KEY = "<existing active user key>"
```

### Bash

```bash
export METRC_INTEGRATOR_API_KEY="<existing vendor key>"
export METRC_USER_API_KEY="<existing active user key>"
```

A facility license is supplied **per evaluation action**, not as one global license for the whole workbook.

## 3. Confirm the workbook plan

No provider call is made.

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation workbook_plan \
  --output artifacts/metrc-evaluation/workbook-plan.json
```

Expected structure:

- 22 worksheets;
- 46 regulator action rows;
- 1 facilities/permissions prerequisite;
- 47 internal evidence checks.

## 4. Verify the existing User API Key and facilities

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation facilities \
  --output artifacts/metrc-evaluation/evidence/task-01-facilities.json
```

This is read-only. The returned facility records are provider truth for what the active User API Key can access.

## 5. Capture bounded task evidence using the correct facility

Every actual task requires an explicit `--license-number`.

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation <bounded_operation_name> \
  --license-number <EXACT_MA_SANDBOX_LICENSE_FOR_THIS_TASK> \
  --payload-file <local-payload.json> \
  --output artifacts/metrc-evaluation/evidence/task-<NN>-<operation>.json
```

The runner will first perform a fresh Facilities preflight with the existing key pair. It refuses the action when the selected license is missing, ambiguous, or lacks the provider capability required for the task family.

Examples of task-family routing must be chosen from current provider state, not hard-coded forever:

- cultivation/plant/harvest actions → a verified Grow facility;
- lab result action → a verified Lab facility with package-testing capability;
- receipt/delivery actions → a verified Sales facility with the required sell/deliver capability;
- transfer/template actions → an explicitly selected facility appropriate to the package/transfer fixture.

Do not hand-edit failed evidence into a pass.

## 6. Build the redacted readiness report

```bash
python artifacts/metrc-evaluation/finalize_report.py \
  --evidence-dir artifacts/metrc-evaluation/evidence \
  --company-info artifacts/metrc-evaluation/company.local.json \
  --require-ready
```

Default outputs:

- `artifacts/metrc-evaluation/evidence/final_report.json`
- `artifacts/metrc-evaluation/evidence/final_report.md`

`--require-ready` remains fail-closed unless all 47 internal checks pass and required non-secret CompanyInformation is complete.

## 7. Preserve and populate CompanyInformation

Use the real regulator workbook; do not recreate it.

```bash
python artifacts/metrc-evaluation/preserve_workbook.py \
  --input "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.xlsx" \
  --output "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.company-complete.xlsx" \
  --company-info artifacts/metrc-evaluation/company.local.json \
  --with-secret-keys \
  --require-complete
```

This produces the CompanyInformation preservation manifest and deliberately does **not** touch task verification or `Metrc Use Only` cells.

## 8. Populate the Permissions table and the 46 regulator verification rows

Only after the canonical evidence is all passed:

```bash
python artifacts/metrc-evaluation/fill_workbook_results.py \
  --input "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.company-complete.xlsx" \
  --output "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.completed.xlsx" \
  --evidence-dir artifacts/metrc-evaluation/evidence
```

The writer:

1. uses canonical task/evidence assignment;
2. refuses any regulator action that is missing, failed, or not HTTP 200;
3. finds each visible `Step` row dynamically instead of guessing row numbers;
4. fills B:H with result code, facility license, provider ID, last-modified value, tag when applicable, request, and minified JSON/response evidence;
5. fills the Permissions request table for DoobieLogic's full MA evaluation scope;
6. refuses conflicting non-empty cells;
7. refuses to write at or after the sheet's `Metrc Use Only` row;
8. writes a redacted `.results.manifest.json` with no API keys.

## 9. Run the final verifier

```bash
node artifacts/metrc-evaluation/verify_final.mjs \
  artifacts/metrc-evaluation/evidence/final_report.json \
  "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.company-complete.manifest.json" \
  "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.completed.results.manifest.json"
```

The verifier requires all of the following:

- 46 regulator action rows plus the facilities prerequisite are represented by all 47 passed internal checks;
- report summary is 47 passed / 0 failed / 0 missing;
- status is `ready_for_metrc_review`;
- regulator approval is explicitly not claimed;
- required CompanyInformation is complete;
- exact canonical 22-sheet structure is preserved;
- Vendor Key Used and User Key Used were filled only in the local workbook;
- all 46 visible task verification rows were intentionally populated;
- the Permissions request table was populated;
- neither workbook-writing step modified `Metrc Use Only` cells;
- no secret values were recorded in reports/manifests.

## Failure handling

Do not bypass a fail-closed result.

- **401 on an action:** first verify the selected facility/profile and the current Facilities permissions/capabilities. The workbook explicitly warns permission-disabled actions typically return 401.
- **Selected license missing/ambiguous:** choose the exact facility returned by the existing User API Key before doing anything else.
- **Task 17 capability false:** do not retry the POST. Preserve the provider blocker and obtain Metrc clarification/provisioning.
- **Missing lab/sales/transfer fixture:** do not fabricate provider state. Use provider-directed data or contact API support as the workbook instructs.
- **Failed/ambiguous mutation:** reconcile provider state; never blind-retry.
- **Workbook sheet/Step mismatch:** stop and confirm the regulator-provided version; never guess a target cell.
- **Verification JSON too large for one Excel cell:** reduce evidence to the exact returned verification record; never silently truncate it.

## Submission checklist

- [ ] Existing User API Key was reused; no new key was generated during the rerun.
- [ ] `GET /facilities/v2` evidence is current.
- [ ] Each action used an explicit, appropriate facility license.
- [ ] Real MA sandbox evidence exists for all 47 internal checks.
- [ ] All regulator actions returned HTTP 200 and are verifiable.
- [ ] `finalize_report.py --require-ready` succeeds.
- [ ] CompanyInformation workbook step succeeds.
- [ ] Result/Permissions workbook step fills all 46 regulator actions and leaves `Metrc Use Only` untouched.
- [ ] `verify_final.mjs` succeeds with both manifests.
- [ ] Exact-head repository CI is green.
- [ ] Completed workbook is manually reviewed before external submission.
- [ ] No keys, raw local evidence, completed workbook, or local manifests are staged in Git.
- [ ] Wording says **ready for Metrc review**, never **Metrc approved**, unless Metrc itself issues that approval.
