# Extraction process parity audit

The current Extraction workspace has the right architectural pieces — source inventory, method-specific workflows, stage events, mass balance, QA, COGS, traceability, outputs, and Run 360 — but the floor workflow is still too linear and several operational controls are either missing or positioned at the wrong boundary.

This document intentionally describes workflow/state tracking only. Equipment setpoints, solvent ratios, temperatures, pressures, times, and other process instructions belong in approved facility SOPs and manufacturer documentation, not hard-coded product logic.

## Primary findings

### 1. Planning, reservation, and actual consumption are collapsed together

The current Quick Start creates a run, reserves a source lot, immediately consumes the selected quantity, and then records the first stage as started.

That makes planning look like physical consumption. The safer operational model is:

**Planned → Material reserved → Preflight ready → Run started → Material consumed**

Inventory should not be consumed merely because an operator created/planned a run. Consumption belongs to the actual process-start event, with the quantity confirmed at that moment.

### 2. Intake needs a real preflight gate

"Intake / Staging" is currently a normal stage. It should function as a structured preflight that can verify, as applicable:

- source package/lot identity and quantity
- source location
- material state/type and workflow eligibility
- release/hold status
- COA/lab status when required
- production order/customer/toll-processing link
- operator/resource assignment
- required equipment/resource readiness acknowledgement
- required compliance/package references
- planned output family

A failed preflight should block Start Run rather than becoming another note in the history.

### 3. Workflows should model material-state transitions, not one giant linear checklist

Hydrocarbon, ethanol, CO2, solventless, distillation, and formulation do not all have the same meaningful path. Optional stages alone are not enough. DoobieLogic should support stage branches such as:

- source material → primary extract/intermediate
- intermediate → refined intermediate
- refined intermediate → formulated bulk
- bulk → filled/packaged output
- output → QA/release

Each transition should be able to create or link the appropriate intermediate inventory/package instead of keeping the entire run as one abstract number until Final Output.

### 4. Intermediate output inventory is underrepresented

At a stage that materially creates a new controlled intermediate, the operator should be able to record:

- measured output
- output material/product type
- destination location
- internal lot/package reference
- regulatory package reference when required
- whether the output continues in the same run, enters hold/WIP inventory, or feeds a downstream run

This is especially important for crude/refined oil, distillate, hash, rosin, separated fractions, and formulated bulk.

### 5. QA should not exist only at the end

The existing common `QA / COA → Release` tail is useful but incomplete. A workflow can need multiple gates:

- incoming/material eligibility gate
- in-process QA/deviation hold
- intermediate release/hold gate
- final testing/COA gate
- final operational release

DoobieLogic should let method/workflow definitions declare the gates that apply rather than assuming one universal final QA stage.

### 6. Holds, deviations, rework, and resume need first-class states

A run should support:

**Active · Hold · QA Hold · Deviation · Rework · Waiting on Test · Waiting on Material · Complete · Cancelled**

A hold should record why work stopped, who placed it, what inventory is affected, and what is required to resume. Rework should create a traceable branch rather than overwriting the original process history.

### 7. Loss, waste, and reconciliation need clearer separation

A stage event currently has loss weight/reason. That is useful but should be separated conceptually into:

- expected/process loss
- recoverable material
- waste/destruction requiring separate operational/compliance handling
- unexplained variance requiring investigation

Final run closeout should reconcile source consumed, intermediate/output inventory, recorded losses/waste, and remaining reserved material.

### 8. Packaging and regulatory package creation are separate concerns

"Filling / Packaging" should track physical production. Regulatory package/tag creation and label/COA readiness should be explicit controlled actions linked to the output. This avoids pretending that a physical filling step automatically completed the state-system action.

### 9. Run closeout is missing as an explicit operational step

After release/terminal disposition, DoobieLogic should perform a closeout checklist:

- all reserved inputs consumed or released back to inventory
- outputs posted to inventory
- intermediate/WIP disposition known
- losses/waste reconciled
- QA/release disposition recorded
- traceability actions verified or flagged for reconciliation
- labor/machine/cost data finalized
- source-to-output lineage complete

Only then should the run become Complete.

## Recommended canonical run lifecycle

The UI should present this simply while the underlying workflow remains method-specific:

1. **Plan** — choose workflow/product intent and source material.
2. **Reserve Material** — reserve inventory without consuming it.
3. **Preflight** — validate material, location, status, resources, compliance context, and planned output.
4. **Start Run** — operator confirms actual input; consumption is posted here.
5. **Process** — method-specific stage sequence with measurements and holds.
6. **Create / Route Intermediate** — when a stage produces controlled WIP, post it or keep it attached to the run with explicit disposition.
7. **Refine / Formulate** — optional downstream branch only when applicable.
8. **Fill / Package** — record finished bulk/fill output separately from regulatory package creation.
9. **QA / Test / Release** — workflow-specific gate(s), including COA where required.
10. **Closeout** — reconcile inventory, losses/waste, outputs, traceability, labor/resources, and release unused reservations.

## Method-level direction

### Hydrocarbon

Keep intake, primary extraction, recovery/post-process, optional separation/crystallization, formulation, filling/packaging, QA/release — but add preflight, explicit intermediate creation/routing, deviation/hold, and closeout. Do not force separation/crystallization on products that do not use it.

### Ethanol

Treat primary extraction, solvent recovery, winterization/filtration/refinement, decarb/distillation, formulation, and filling as composable downstream branches. A crude-only run should be able to stop and release an intermediate without walking through distillation/formulation screens.

### CO2

Use the same composable principle: extraction/separation creates an intermediate; refinement/winterization/decarb/distillation may continue in the same run or become a downstream run depending on facility practice.

### Ice-water hash / solventless

Track source staging, wash/collection, drying, grading, optional press, curing/post-process where applicable, packaging, QA/release, and closeout. Hash that is intentionally sold/held as hash should not be forced through a rosin step.

### Dry sift

Track sift/refinement and allow terminal dry-sift output, pressed-hash branch, or rosin branch rather than presenting all as one linear path.

### Distillation

Treat crude/distillate processing as its own downstream workflow fed by an intermediate inventory object. This is already partially represented by `crude_distillate` and should become a clean handoff from upstream extraction.

### Formulation / vape oil / filling

Treat formulation and filling as downstream manufacturing workflows fed by released bulk oil/rosin/distillate inventory. They should not be mandatory tail stages on every extraction workflow.

## UX recommendation

The floor view should answer only:

- What run am I on?
- What is the current required action?
- What material is in the run?
- What output did I just create?
- Is anything blocking me?
- What happens next?

Run 360 should hold the deeper mass-balance history, COGS, QA, traceability, equipment/labor, customer/toll-processing, deviations, and complete source-to-output lineage.

The product rule remains: **complex underneath, simple on top.**