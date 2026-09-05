# Massachusetts Metrc Evaluation Finalization

This directory contains the **local finalization and submission-safety workflow** for the Massachusetts Metrc Generic Evaluation workbook (`Generic_Evaluation_for_All_States_MASTER 10.2025.xlsx`).

It is intentionally fail-closed. A locally generated package may say **`ready_for_metrc_review`** only when all 47 Massachusetts-applicable evaluation tasks have valid evidence and all required non-secret CompanyInformation fields are present. It never claims that Metrc has approved the evaluation.

## Safety boundary

- Evaluation execution is restricted to the verified **Massachusetts sandbox**.
- A task passes finalization only when its selected evidence records:
  - `state = MA`
  - `environment = sandbox`
  - `http_status = 200`
  - `stage = complete`
  - `passed = true`
- Missing or failed evidence keeps the package `not_ready`.
- A later complete passing retry may supersede an earlier failed attempt for the same task.
- Credential-like fields in evidence are rejected.
- Vendor/User API keys are never accepted by `finalize_report.py` and are never written to the final report or redacted workbook manifest.
- Vendor/User API keys may enter the local submission workbook only from:
  - `METRC_INTEGRATOR_API_KEY`
  - `METRC_USER_API_KEY`
- The completed `.xlsx`, local company JSON, evidence directory, manifests, and generated final reports are gitignored and must remain local.
- The workbook preservation step does **not** populate task-result cells and does **not** modify `Metrc Use Only` cells.

## Files

- `company.example.json` — safe template for non-secret CompanyInformation values.
- `finalize_report.py` — builds redacted JSON and Markdown readiness reports from local runner evidence.
- `preserve_workbook.py` — fills label-matched CompanyInformation values while preserving the regulator workbook structure.
- `verify_final.mjs` — final fail-closed check for a 47/47 local evidence package plus the preserved 22-sheet workbook manifest.
- `../../scripts/run_ma_metrc_evaluation.py` — bounded MA sandbox evaluation runner that creates the source evidence.
- `../../services/metrc_evaluation_finalization.py` — canonical evidence assignment, validation, redaction, and readiness logic.

## Prerequisites

Run commands from the repository root.

You need:

- the repository's Python environment/dependencies installed;
- Node.js for `verify_final.mjs`;
- valid Massachusetts Metrc sandbox credentials for real evaluation execution;
- the regulator-provided `Generic_Evaluation_for_All_States_MASTER 10.2025.xlsx` for the workbook-preservation smoke test and final local submission package.

Do **not** substitute a recreated workbook for the regulator-provided file.

## 1. Prepare local CompanyInformation

Copy the safe example to the gitignored local file:

### PowerShell

```powershell
Copy-Item artifacts/metrc-evaluation/company.example.json artifacts/metrc-evaluation/company.local.json
```

### Bash

```bash
cp artifacts/metrc-evaluation/company.example.json artifacts/metrc-evaluation/company.local.json
```

Edit `company.local.json` with the real non-secret company/contact information.

**Never add Vendor/User keys to this JSON.** Both finalizers reject that pattern by design.

## 2. Set sandbox secrets locally

### PowerShell

```powershell
$env:METRC_INTEGRATOR_API_KEY = "<vendor/integrator key>"
$env:METRC_USER_API_KEY = "<user key>"
$env:METRC_LICENSE_NUMBER = "<MA sandbox license>"
```

### Bash

```bash
export METRC_INTEGRATOR_API_KEY="<vendor/integrator key>"
export METRC_USER_API_KEY="<user key>"
export METRC_LICENSE_NUMBER="<MA sandbox license>"
```

Keep these values out of shell history, screenshots, tickets, evidence JSON, reports, commits, and PR comments.

## 3. Confirm the workbook plan

This does not call Metrc and does not prove any task passed. It prints/writes the canonical workbook plan used by the runner.

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation workbook_plan \
  --output artifacts/metrc-evaluation/workbook-plan.json
```

The canonical plan contains 22 workbook sheets and 47 Massachusetts-applicable task rows.

## 4. Capture real MA sandbox evidence

Run each bounded workbook operation with `scripts/run_ma_metrc_evaluation.py`. Most operations require an operation-specific payload JSON.

Example shape:

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation <bounded_operation_name> \
  --payload-file <local-payload.json> \
  --output artifacts/metrc-evaluation/evidence/task-<NN>-<operation>.json
```

The facilities row does not require a payload file:

```bash
python scripts/run_ma_metrc_evaluation.py \
  --operation facilities \
  --output artifacts/metrc-evaluation/evidence/task-01-facilities.json
```

Use stable task-prefixed filenames (`task-01-...json`, `task-02-...json`, etc.) when an operation type appears more than once in the workbook. The finalizer can also use an explicit `task_number` field when present.

A finalizable evidence file must match the expected workbook operation and ultimately record HTTP 200, `stage=complete`, `passed=true`, `state=MA`, and `environment=sandbox`. Failed attempts may remain in the local evidence directory; a valid later passing retry can supersede them.

Do not hand-edit a failed runner response into a pass.

## 5. Build the redacted readiness report

```bash
python artifacts/metrc-evaluation/finalize_report.py \
  --evidence-dir artifacts/metrc-evaluation/evidence \
  --company-info artifacts/metrc-evaluation/company.local.json \
  --require-ready
```

Default outputs:

- `artifacts/metrc-evaluation/evidence/final_report.json`
- `artifacts/metrc-evaluation/evidence/final_report.md`

With `--require-ready`, the command exits non-zero unless all 47 tasks pass and all required non-secret CompanyInformation values are present.

The report status means:

- `not_ready` — local evidence and/or required company information is incomplete;
- `ready_for_metrc_review` — the local package passed DoobieLogic's finalization rules and is ready to be presented to Metrc;
- **neither status means regulator approval**. Metrc remains the authority that accepts or rejects the official evaluation.

## 6. Preserve and populate the regulator workbook locally

Place the regulator-provided workbook locally under `artifacts/metrc-evaluation/`. `.xlsx` files in this directory are gitignored.

Then run:

```bash
python artifacts/metrc-evaluation/preserve_workbook.py \
  --input "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.xlsx" \
  --output "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.completed.xlsx" \
  --company-info artifacts/metrc-evaluation/company.local.json \
  --with-secret-keys \
  --require-complete
```

This step:

1. requires the exact canonical 22-sheet structure;
2. finds CompanyInformation fields by their labels instead of hard-coded guessed cell coordinates;
3. fills only safely identified value cells;
4. obtains Vendor/User keys only from environment variables when `--with-secret-keys` is supplied;
5. refuses to overwrite a non-empty conflicting value unless `--overwrite-existing` is deliberately supplied;
6. produces a redacted `.manifest.json` next to the completed workbook by default;
7. verifies the output still has the canonical 22-sheet structure.

`--overwrite-existing` should be used only after manually reviewing the real regulator template and the existing value being replaced.

## 7. Run the final verifier

After the report and workbook manifest exist:

```bash
node artifacts/metrc-evaluation/verify_final.mjs \
  artifacts/metrc-evaluation/evidence/final_report.json \
  "artifacts/metrc-evaluation/Generic_Evaluation_for_All_States_MASTER 10.2025.completed.manifest.json"
```

The verifier exits non-zero unless all of the following are true:

- exactly 47 MA-applicable tasks are present and passed;
- the report summary is 47 passed / 0 failed / 0 missing;
- status is `ready_for_metrc_review`;
- regulator approval is explicitly **not** claimed;
- required non-secret CompanyInformation is complete;
- the workbook manifest reports the exact canonical 22 sheets;
- Vendor Key Used and User Key Used were filled in the local workbook;
- no secret values were recorded in the report or manifest;
- task-result and `Metrc Use Only` cells were not modified by the preservation step.

## 8. Run regression tests

These tests use synthetic/local fixtures. Passing them proves the finalization code behaves as designed; it does **not** prove the real Metrc evaluation passed.

```bash
pytest -q \
  tests/test_metrc_evaluation_finalization.py \
  tests/test_metrc_evaluation_workbook_preservation.py \
  tests/test_metrc_evaluation_final_verifier.py
```

The normal repository PR CI must also be green at the exact PR head before merge.

## Failure handling

Do not bypass a fail-closed result.

- **Missing evidence:** run the missing bounded workbook task against the verified MA sandbox.
- **Failed evidence:** correct the underlying request/data/setup issue and rerun; keep the real new evidence.
- **Operation mismatch:** confirm the task number and bounded operation are the matching workbook row.
- **Credential-like field detected:** remove the credential from the source workflow, rotate it if it may have been exposed, and regenerate clean evidence.
- **Workbook sheet mismatch:** stop. Confirm the file is the regulator-provided 10.2025 workbook/version expected by the code. Do not force the script through a structurally different template.
- **Missing/ambiguous CompanyInformation label:** stop and review the real workbook. Do not guess a cell coordinate.
- **Existing conflicting CompanyInformation value:** review the template/value before intentionally using `--overwrite-existing`.

## Submission checklist

Before calling the package ready for Metrc review:

- [ ] Real regulator-provided 10.2025 workbook is being used.
- [ ] Real MA sandbox evidence exists for all 47 applicable tasks.
- [ ] `finalize_report.py --require-ready` succeeds.
- [ ] `preserve_workbook.py --with-secret-keys --require-complete` succeeds against the real workbook.
- [ ] `verify_final.mjs` succeeds.
- [ ] Exact-head repository CI is green.
- [ ] Completed workbook is manually reviewed before external submission.
- [ ] No secrets, raw local evidence, completed workbook, or local manifests are staged in Git.
- [ ] Wording says **ready for Metrc review**, never **Metrc approved**, unless Metrc itself has actually issued that approval.

## Current repository boundary

The code and synthetic tests can validate the finalization mechanics without the regulator workbook or live sandbox evidence. However, the workflow is **not fully smoke-tested against the actual regulator workbook until that exact `.xlsx` is supplied locally**, and the 47 tasks are **not considered passed until real Massachusetts sandbox evidence satisfies the finalizer**.
