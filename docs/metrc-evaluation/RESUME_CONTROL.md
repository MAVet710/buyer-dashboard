# Massachusetts Metrc Evaluation Resume Control

## Scope

Resume the Massachusetts `Generic_Evaluation_for_All_States_MASTER 10.2025` evaluation from the established `DL-EVAL-20260912-RESUME-01` checkpoint without repeating already verified writes.

This document is an engineering control record. It does not claim Metrc approval.

## Trusted checkpoint

The operator-provided blocker review reports:

- **16 passed**
- **4 failed**
- **27 missing**
- **47 Massachusetts-applicable evidence tasks total**

Tasks **1–16** have verified passing attempts in the referenced local run and should be preserved unless evidence-integrity or current-provider-state reconciliation proves otherwise.

Unresolved attempts are:

- **Task 17** — `POST /plants/v2/plantbatch/packages`, observed HTTP 401; outcome unresolved and source plant/tag must be preserved.
- **Task 37** — incoming transfer read returned HTTP 200 with no records.
- **Task 38** — outgoing transfer read returned HTTP 200 with no records.
- **Task 39** — rejected transfer read returned HTTP 200 with no records.

A separate retail prerequisite attempt against `POST /sandbox/v2/packages/create` returned HTTP 401. That prerequisite is not task 25 and must never be counted as an evaluation pass.

Task 30 has no provider execution evidence yet; an existing lab item does not establish an eligible lab package.

## Resume policy

1. Do not rerun tasks 1–16 merely because an older summary is stale.
2. Reconcile uncertain create outcomes before retrying them.
3. Do not destroy the task-17 source plant or consume its reserved package tag while task 17 is unresolved.
4. Do not count HTTP 200 + empty transfer lists as workbook find-record passes.
5. Do not fabricate transfer IDs, lab packages, test values, retail stock, or provider timestamps.
6. Keep sandbox-only routing fail closed.
7. Keep API keys out of evidence, reports, support requests, logs, and commits.
8. Package finalization tasks 27–29 remain deliberately last so downstream consumers retain inventory.

## Blocker tracks

### A — Task 17: plant → plant-batch package

Current evidence supports three facts only:

- the official current MA v2 documentation still exposes `POST /plants/v2/plantbatch/packages`;
- the captured attempt returned HTTP 401;
- all 18 captured facility records reported `FacilityType.CanCreateImmaturePlantPackagesFromPlants=false`.

The cause of the 401 remains **unknown**. The capability flag is consistent with an applicability/capability restriction, but it is not proof of the response cause.

Next gate: reconcile source plant/tag, verify transport parity, then obtain authoritative provider clarification or an eligible/provisioned MA evaluation facility before any retry.

### B — Retail stock / sandbox package provisioning

The official current MA API still exposes `POST /sandbox/v2/packages/create`. A prior prerequisite attempt returned HTTP 401 after successful reference reads.

Next gate: first discover whether already-existing active package inventory can satisfy the sales/delivery evaluation. Only pursue sandbox package provisioning if no legitimate stock exists.

### C — Transfers and wholesale

The blocker review records 54 additional unfiltered reads across 18 facilities (incoming/outgoing/rejected), all HTTP 200 and all empty.

Next gate: determine whether official sandbox provisioning can create legitimate transfer fixtures. If not, obtain provider-supplied incoming, outgoing, and rejected transfer references with linked delivery/package/wholesale children.

### D — Lab task 30

The official current MA API still exposes `POST /labtests/v2/record` and `GET /labtests/v2/types`.

Next gate: discover an eligible package in an authorized lab facility and current test definitions. If none exists, obtain provider-supplied eligible lab inventory/procedure. Never invent test names or values.

## Conservative dependency graph

```text
17 <- 16,10
18 <- 17
19 <- 18
20 <- 19
21 <- 20,10
22 <- 21
23 <- 22
24 <- 23
25 <- 21
26 <- 25
30 <- 1
31 <- 26
32 <- 31
33 <- 32
34 <- 33
35 <- 34
36 <- 35
37 <- 1
38 <- 1
39 <- 1
40 <- 37,38
41 <- 40
42 <- 41
43 <- 26,42
44 <- 43
45 <- 43,44
46 <- 45
47 <- 46
27 <- 26,30,33,36,47
28 <- 27
29 <- 28
```

A narrowly reviewed task-43 independence policy, if present in the execution runtime, must not be treated as a pass for task 42 and must not remove task 26 or required template transport/package inputs.

## Read-only diagnostics

`scripts/diagnose_ma_metrc_resume_blockers.py` performs GET requests only and is intended to answer current prerequisite questions without consuming evaluation resources. The matching GitHub Action is `.github/workflows/ma-metrc-resume-diagnostics.yml`.

The diagnostic checks all facilities accessible to the saved MA sandbox credential pair for:

- task-17 capability declaration;
- active package candidates;
- lab-sample package candidates;
- lab test types;
- sales customer-type reference access.

The detailed artifact is short-lived because it can contain sandbox facility/package identifiers. The persistent summary contains only counts and pseudonymous facility aliases.

## Definition of complete

The evaluation is not complete until the generated final report records:

- 47 passed
- 0 failed
- 0 missing
- state `MA`
- environment `sandbox`
- HTTP 200 for every applicable task
- `stage=complete`
- `passed=true`

A fully passing DoobieLogic evidence package may be described as **ready for Metrc review**. Only Metrc can approve the official evaluation.
