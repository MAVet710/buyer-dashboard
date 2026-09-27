import type { HelpWalkthroughRegistry } from "./types";

export const productionWalkthroughs: HelpWalkthroughRegistry = {
  "/help/production": {
    title: "Plan production and create a job",
    category: "production",
    summary: "Review the next runs, investigate blockers, and save a production order before scheduling or recording physical work.",
    navPath: "Production Ops → Production → Today / Production",
    appPath: "/production",
    beforeYouStart: ["Confirm the active facility is where the work will happen.", "Have the requested finished quantity, product identity, due date, and customer details for external work. A source reference alone doesn't reserve inventory."],
    steps: [
      { id: "review-production-plan", title: "Review what can run next", instructions: ["Open Production and stay on Plan. Read Ready / Next, Blocked, and the rows under What should we run next?.", "Check the material explanation for the run. Available · reserve to run means material still needs a reservation. Buyer review calls for a shortage decision, not an automatic purchase order."], expected: "You can identify a candidate run and the reason it's ready or blocked." },
      { id: "open-next-action", title: "Open the run behind a blocker", instructions: ["Under Next Actions, select the row for Review QA hold, Resolve material blocker, Review held run, or Continue run execution as appropriate.", "Check the order number in Run 360 before acting. Close the run window when you're ready to return to planning."], expected: "Run 360 opens the selected production order over the planning workspace." },
      { id: "open-new-job", title: "Open the job form", instructions: ["For new work, choose Operations, then New Job. Go to Committed production order.", "The Weight-based production recommendation section is a planning aid. Review any prefilled recommendation before saving it as an order."], expected: "The editable order form is visible; an unsaved form hasn't created a run." },
      { id: "enter-job-identity", title: "Enter the product and requested work", instructions: ["Use a distinct order number and the actual finished product name and format. Enter finished units, not bulk grams, in Requested units*.", "Choose Internal or External. For External, select the customer already set up in Customers."], fields: [
        { label: "Order number*", requirement: "Required.", guidance: "Use your team's job identifier so the order can be found later.", example: "PROD-DEMO-042" },
        { label: "Work type*", requirement: "Required selection.", guidance: "Choose Internal for your own work or External for customer work." },
        { label: "Requested units*", requirement: "Required positive quantity.", guidance: "Enter the number of finished units the job should produce.", example: "500" },
        { label: "Product name*", requirement: "Required.", guidance: "Match the intended finished product." },
        { label: "Product format*", requirement: "Required selection.", guidance: "Choose the actual format from the available options." },
        { label: "SKU", requirement: "Optional in this form.", guidance: "Use the existing product SKU when available to keep the job identifiable." },
        { label: "Customer* (external work)", requirement: "Conditional on External work.", guidance: "Select the customer responsible for this job." }
      ], expected: "The form describes the intended output and who the work is for." },
      { id: "enter-job-context", title: "Add timing, ownership, and floor instructions", instructions: ["Enter Due date and Priority to explain timing. Copy the correct source reference into Source lot / METRC package.", "Set Bulk material owner and Packaging owner independently. Use Production notes for weighing, packaging, or handling instructions that the next operator needs."], fields: [
        { label: "Due date", requirement: "Optional scheduling context.", guidance: "Choose the agreed delivery or completion date." },
        { label: "Priority", requirement: "Selection with a default.", guidance: "Choose Normal, High, Rush, or Low to reflect the actual priority." },
        { label: "Source lot / METRC package", requirement: "Optional reference.", guidance: "Record the known source identifier. This field doesn't consume or reserve it." },
        { label: "Bulk material owner", requirement: "Selection with a default.", guidance: "Choose Internal or Customer based on ownership of the material." },
        { label: "Packaging owner", requirement: "Selection with a default.", guidance: "Identify who supplies the packaging." },
        { label: "Production notes", requirement: "Optional.", guidance: "Write instructions that distinguish this job from a routine run.", example: "Keep the two finished package sizes on separate trays." }
      ], expected: "The order contains the timing and ownership information needed for planning." },
      { id: "save-and-review-job", title: "Save the job and check the queue", instructions: ["Choose Create production order and wait for Production order was saved. If a request fails ambiguously, check the queue for that order number before trying again.", "Open Dashboard to locate the saved order. Use Calendar for its schedule and Run 360 for reservations, actual consumption, outputs, QA, and costs."], expected: "The saved order appears in production records. Creating it has not by itself recorded physical consumption or finished output." }
    ],
    completion: ["The intended order number and product appear in the production queue.", "Any material or QA blockers are understood before the team starts physical work."],
    troubleshooting: [
      { symptom: "The planning view says material is available, but the run isn't reserved.", resolution: "Open the exact run, choose Materials, and review Preview reservations. Apply the reviewed reservation only after checking the lots and quantities." },
      { symptom: "A saved order isn't in an Operations list.", resolution: "Check Status filter, Priority filter, and Format filter on Dashboard. Read any notice that only the latest records are loaded; absence from a bounded list doesn't mean the order was deleted." },
      { symptom: "External work has no customer to select.", resolution: "Open Operations → Customers and have the customer set up before returning to the job. Don't substitute another customer to get past the form." }
    ],
    sourceFiles: ["frontend/src/App.tsx", "frontend/src/lib/workspaceRoutes.ts", "frontend/src/components/ProductionPlanningWorkspace.tsx", "frontend/src/components/ProductionPlanner.tsx", "frontend/src/components/ProductionNextActions.tsx", "frontend/src/pages/ProductionPage.tsx", "frontend/src/pages/ProductionPageLegacy.tsx", "backend/app/routers/coman_parity_legacy.py", "backend/app/routers/production.py"]
  },
  "/help/production/calendar": {
    title: "Schedule a production run",
    category: "production",
    summary: "Place an existing run on the calendar, review conflicts, and commit the exact schedule window.",
    navPath: "Production Ops → Production → Calendar",
    appPath: "/production/calendar",
    beforeYouStart: ["Create the production order first. Complete and cancelled orders aren't offered as active scheduling choices.", "Check your device's local time zone. Calendar inputs and displayed times use the browser's local time; the request stores timestamps in UTC."],
    steps: [
      { id: "find-calendar-month", title: "Find the intended month", instructions: ["Open Calendar. Use Previous, Today, and Next to move between months.", "Compare Active Unscheduled with Active Runs. Select an existing calendar event if you need to inspect its Run 360 before changing plans."], expected: "You can see existing placements for the intended date and identify unscheduled work." },
      { id: "choose-schedule-run", title: "Choose the run to place", instructions: ["Choose Schedule Run, or use the + on the intended day. The day shortcut proposes an 8:00 start but doesn't save it.", "Select Production run by order number and product. Selecting a run that already has a placement leads to a reschedule preview."], fields: [{ label: "Production run", requirement: "Required.", guidance: "Select the saved order you intend to schedule." }], expected: "The scheduler identifies the correct run and shows its BOM standard when available." },
      { id: "set-schedule-window", title: "Set the time, machine, and people", instructions: ["Enter Start and End. If a cycle standard exists, changing Start proposes End from that standard; check the proposed end before continuing.", "Select a facility machine when needed, enter People, and explain the timing in Reason / scheduling note."], fields: [
        { label: "Start", requirement: "Required.", guidance: "Enter the local date and time work should begin." },
        { label: "End", requirement: "Required and later than Start.", guidance: "Include enough time for the planned work and inspect any automatically proposed value." },
        { label: "Machine", requirement: "Optional.", guidance: "Choose an available facility machine or leave No machine assigned when appropriate." },
        { label: "People", requirement: "Nonnegative whole number.", guidance: "Enter the planned crew count, not labor hours.", example: "3" },
        { label: "Reason / scheduling note", requirement: "Optional context.", guidance: "Explain a shift, priority, or timing decision.", example: "Move to afternoon after the packaging crew finishes receiving." }
      ], expected: "The proposed schedule window and resources reflect the intended floor plan." },
      { id: "preview-schedule", title: "Read the schedule conflicts", instructions: ["Choose Preview Schedule. Review Start, End, Window, and Crew in Exact Change Preview.", "Read every material, labor, machine, QA, compliance, and due-date message. Return to the relevant run or resource setup to resolve an unexpected conflict. Editing any scheduler field clears the previous preview."], expected: "A fresh preview describes the exact placement and its conflicts; no schedule has been committed yet." },
      { id: "commit-schedule", title: "Commit the reviewed placement", instructions: ["If conflicts remain and you're authorized to accept them, select I reviewed these conflicts and still want to commit this schedule placement. This acknowledges the schedule conflict, not a QA release.", "Choose Commit Schedule or Commit Reschedule. Wait for the calendar to refresh and move to the placement's month."], expected: "The calendar contains the run at the saved start time with its machine and people count." },
      { id: "verify-calendar-run", title: "Open the scheduled run", instructions: ["Select the calendar event and check its order number and product in Run 360.", "Continue material and QA work in Run 360. A calendar placement doesn't reserve or consume material and doesn't release finished inventory."], expected: "The event opens the intended saved run." }
    ],
    completion: ["The event shows the intended start time, product, machine, and people count.", "Run 360 opens the same order from the calendar."],
    troubleshooting: [
      { symptom: "End changes when you edit Start.", resolution: "The BOM cycle standard proposes a duration. Review and adjust End after changing Start, then request a new preview." },
      { symptom: "A schedule commit is rejected after a successful preview.", resolution: "Review the error and refresh the schedule before previewing again. Another change can make the previous preview stale. Check whether a placement was saved before submitting another commit." },
      { symptom: "The date cell says there are more runs.", resolution: "The calendar displays up to four event buttons per day. Use the production queue or Run 360 selector to inspect other runs; the extra-count message isn't a deleted or missing record." }
    ],
    sourceFiles: ["frontend/src/components/ProductionPlanningWorkspace.tsx", "frontend/src/components/ProductionCalendar.tsx", "backend/app/routers/production.py", "modules/production_erp/scheduling.py"]
  },
  "/help/production/run-360": {
    title: "Record materials, output, and QA in Production Run 360",
    category: "production",
    summary: "Work one saved production order from material reservations through actual consumption, measured output, QA, and costs.",
    navPath: "Production Ops → Production → Production Run 360",
    appPath: "/production/runs",
    beforeYouStart: ["Have a saved production order and verify its facility, product, and planned quantity.", "Use measured quantities and the displayed units. Reservations, physical consumption, planned outputs, and recorded actuals are separate actions.", "QA decisions and physical consumption require server-side permission. If access is denied, ask the person responsible for that action to review it."],
    steps: [
      { id: "select-production-run", title: "Open the exact run", instructions: ["Choose Production run and match its order number and product. Check Planned, Actual, Attainment, and the status beside the heading.", "If a saved run link can't be opened, keep that identifier and resolve the access or facility issue. The page doesn't replace it with another run."], fields: [{ label: "Production run", requirement: "Required selection when using the picker.", guidance: "Choose the order you are physically working on." }], expected: "The heading identifies the intended order and its current recorded state." },
      { id: "review-run-standards", title: "Check the recipe and execution standards", instructions: ["Open Standards and review Expected for this run against Actual. Standards belong to a BOM version and scale to the requested quantity.", "If No active BOM is linked appears, set up the product BOM in Production → Operations → Inventory & BOM before relying on recipe requirements. A blank variance isn't proof of zero loss."], expected: "You know whether the run has a BOM, execution standard, and QA release requirement." },
      { id: "reserve-run-materials", title: "Reserve the planned materials", instructions: ["Open Materials. Compare Required vs reserved materials with Current reservations, then choose Preview reservations.", "Read the lots, quantities, and before-and-after values. Choose Apply exact change only for the allocation you've reviewed. A shortage stays a buyer review task and doesn't create a purchase order."], expected: "Current reservations shows the applied allocation. Reservation alone hasn't decremented the physical source balance." },
      { id: "consume-run-materials", title: "Record what physically went into the run", instructions: ["In Materials, use Add source lot and select each lot actually used. Enter Actual quantity used in that row's unit; remove rows that don't belong in this consumption.", "Choose Preview actual consumption and check the source balance and reservation consequences. Then choose Apply physical consumption."], fields: [{ label: "Actual quantity used", requirement: "Positive quantity for each submitted source.", guidance: "Enter the measured amount actually taken from this lot in its displayed unit, not the planned output count.", example: "250" }], warning: "Apply physical consumption decreases inventory and records the source relationship for finished output. Check the lot and quantity before applying it. Don't repeat an uncertain submission without checking the run.", expected: "The consumption result is recorded and Current reservations refreshes. Reopen Production Inventory to verify the current source balance before recording another consumption." },
      { id: "record-run-event", title: "Record the work as it happens", instructions: ["Open Execute. Select Event and enter Stage, measured quantities, hours, and Notes as appropriate.", "Started, Measurement, and Note use Post run event and save immediately. Hold, Release, Completed, Waste, and Rework use Preview change; review the consequences before Apply exact change."], fields: [
        { label: "Event", requirement: "Required selection.", guidance: "Choose the event that actually happened rather than using completion to clear a blocker." },
        { label: "Stage", requirement: "Stage identifier with a default.", guidance: "Name the process step the event describes.", example: "packaging" },
        { label: "Quantity", requirement: "Optional measurement.", guidance: "Enter a nonnegative measured quantity with its Unit." },
        { label: "Unit", requirement: "Needed to interpret quantities.", guidance: "Use the unit of the measurement, such as g or unit." },
        { label: "Waste quantity", requirement: "Optional, when waste occurred.", guidance: "Record the measured loss and explain it in Notes." },
        { label: "Labor hours", requirement: "Optional actual.", guidance: "Enter actual labor time, not crew headcount." },
        { label: "Machine hours", requirement: "Optional actual.", guidance: "Enter actual machine time." },
        { label: "Notes", requirement: "Context appropriate to the event.", guidance: "Explain the measurement, loss, hold, or rework so another operator can follow it." }
      ], expected: "The event is saved or a change preview is shown. Timeline provides the saved event evidence." },
      { id: "record-run-output", title: "Plan the output, then record its actual quantity", instructions: ["Open Outputs. If the required output isn't listed, choose Product, Planned quantity, Unit, and Label, then Add planned output.", "In the output row, enter the total measured Actual and a Lot code for a new finished lot. Choose Preview actual. Review the inventory change and any return to QA quarantine before Apply exact change. An updated actual is a total, not an extra quantity to add."], fields: [
        { label: "Product", requirement: "Required for a new planned output.", guidance: "Select the actual finished product." },
        { label: "Planned quantity", requirement: "Nonnegative planned quantity.", guidance: "Enter the intended output in the selected Unit." },
        { label: "Label", requirement: "Optional output description.", guidance: "Distinguish outputs when the run produces more than one item." },
        { label: "Actual", requirement: "Measured total for the output row.", guidance: "Enter the full actual quantity for this output, including any quantity already recorded." },
        { label: "Lot code", requirement: "Required when creating the finished lot.", guidance: "Use the actual finished lot identifier.", example: "DEMO-FIN-042" }
      ], warning: "Applying an output actual can create or change finished inventory and reapply quarantine. Check the preview before committing a correction.", expected: "The output row shows its recorded Actual and Status, and the run's Actual and Attainment update." },
      { id: "record-run-qa", title: "Record a supported QA decision", instructions: ["Open QA. Select Decision, Result, and the specific Output, or Whole run when the decision covers all outputs.", "Enter the supporting Document / COA and Notes. Choose Preview QA decision, inspect every affected lot, then Apply exact change if the decision is approved and no blocker remains."], fields: [
        { label: "Decision", requirement: "Required selection.", guidance: "Choose the actual QA action, such as Hold, Pass, Fail, or Release." },
        { label: "Result", requirement: "Required selection.", guidance: "Use the result supported by the evidence." },
        { label: "Output", requirement: "Required scope choice.", guidance: "Limit the decision to one output unless it truly applies to Whole run." },
        { label: "Document / COA", requirement: "Supporting evidence as applicable.", guidance: "Enter the reference for the reviewed lab or QA document." },
        { label: "Notes", requirement: "Decision context.", guidance: "Explain the evidence and reason for the decision." }
      ], warning: "A release can make output lots available. Don't release them merely because the production work is finished.", expected: "QA history records the decision, and the affected output status reflects the applied change." },
      { id: "cost-and-review-run", title: "Record costs and review the final history", instructions: ["In Costs, choose Category, enter Amount in USD, and add Source reference and Notes. Use Preview cost to compare total cost and cost per actual unit before Apply exact change.", "Open Timeline to review saved events and their times. If the work is complete, return to Execute, select Completed, and review Preview change before applying it. Check QA separately."], fields: [
        { label: "Category", requirement: "Required selection for a cost.", guidance: "Choose Material, Packaging, Labor, Machine, Overhead, Waste, or Other." },
        { label: "Amount", requirement: "Nonnegative USD amount.", guidance: "Enter the cost of this event; don't re-enter a cost already recorded." },
        { label: "Source reference", requirement: "Optional.", guidance: "Use an invoice, time record, or other reference that supports the cost." }
      ], expected: "Actual COGS and Timeline show the recorded work. The run status and QA history can be checked independently." }
    ],
    completion: ["Current reservations and actual material entries match the material used.", "Outputs show measured totals and the correct status; QA history contains the reviewed decisions.", "Timeline and Actual COGS show the saved events and costs."],
    troubleshooting: [
      { symptom: "Apply exact change is disabled.", resolution: "Read the blocker in the preview. Correct the missing material, output, or QA requirement in its owning tab, then create a fresh preview." },
      { symptom: "A corrected output returns to quarantine.", resolution: "Review the actual-output preview and obtain the QA decision appropriate to the corrected output. A prior release doesn't automatically approve a changed quantity." },
      { symptom: "The request failed and you don't know whether material was consumed.", resolution: "Reopen the exact run and review the material records and inventory balance before making another consumption entry. Ask a supervisor to reconcile an uncertain result." }
    ],
    sourceFiles: ["frontend/src/pages/ProductionRun360Page.tsx", "frontend/src/components/ProductionActualMaterials.tsx", "backend/app/routers/production.py", "backend/app/routers/production_mutations.py"]
  },
  "/help/extraction": {
    title: "Plan and work an extraction run",
    category: "production",
    summary: "Reserve compatible feedstock, confirm preflight, consume the source at start, and record measured progress through the extraction process.",
    navPath: "Production Ops → Production → Extraction",
    appPath: "/production/extraction",
    beforeYouStart: ["Confirm the active facility and identify the physical source package.", "Use a released, compatible source with available quantity after existing commitments. Finished packaged products aren't extraction feedstock just because they're in Production Inventory.", "Have the equipment, SOP, batch documentation, and a scale ready before starting physical work."],
    steps: [
      { id: "find-extraction-work", title: "Check today's work before creating another run", instructions: ["Open Extraction. Review Today, or choose Runs and use Find run to search by batch, strain, or method.", "Include Closed runs when checking whether a job already exists. Open the matching run rather than creating a duplicate."], fields: [{ label: "Find run", requirement: "Optional search.", guidance: "Enter part of the known batch, strain, or method." }], expected: "You either open the existing run or confirm that a new run is needed." },
      { id: "choose-extraction-source", title: "Choose a compatible process and source", instructions: ["Choose New run. Select Process / target first, then Source material from the compatible choices.", "Review the displayed package, location, available quantity, and unit. Set Amount to reserve and check Run ID before choosing Plan run & reserve."], fields: [
        { label: "Process / target", requirement: "Required.", guidance: "Choose the actual extraction workflow. This controls which source materials are offered." },
        { label: "Source material", requirement: "Required compatible source.", guidance: "Match the selected lot and package to the physical material." },
        { label: "Amount to reserve", requirement: "Greater than zero and no more than available.", guidance: "Use the source lot's displayed unit; this is not automatically grams for every lot." },
        { label: "Run ID", requirement: "Required run identity.", guidance: "Use the batch identifier your team will recognize.", example: "EXT-DEMO-042" }
      ], expected: "The run opens with reserved material. Planning hasn't consumed the source." },
      { id: "start-extraction-run", title: "Confirm preflight and start the run", instructions: ["Physically verify the source, equipment, and batch documentation. Select Source package/material verified, Required equipment/work area ready, and Required SOP/batch documentation ready only after those checks.", "Choose Start run & consume reserved material when the floor is ready to begin."], warning: "Starting consumes the reserved source and records the first stage start. If the request has an uncertain result, inspect Inputs and History in Run 360 before retrying; consumption and stage start are separate requests.", expected: "The run leaves preflight and shows the current process stage. The reserved source has been consumed for the run." },
      { id: "measure-extraction-stage", title: "Enter the actual stage measurement", instructions: ["Confirm the current stage in the heading. Review Stage input (g) and enter Scale output (g) from the scale.", "If What was measured? appears, select the output that the reading represents. Add Operator note when the next person needs context. Choose Save measurement to record a reading without advancing the stage."], fields: [
        { label: "Stage input (g)", requirement: "Stage measurement in grams.", guidance: "Check the carried-forward value against the material entering this stage." },
        { label: "Scale output (g)", requirement: "Required when the stage needs a measured output.", guidance: "Enter actual scale weight in grams, not the target yield." },
        { label: "What was measured?", requirement: "Conditional when multiple output readings are offered.", guidance: "Choose the material represented by the scale reading." },
        { label: "Operator note", requirement: "Optional for a routine measurement; needed for a process note.", guidance: "Describe anything the next operator should know." }
      ], expected: "The measurement is recorded while the current stage remains available for further work." },
      { id: "explain-extraction-variance", title: "Explain loss or unexpected results", instructions: ["Open More process / traceability options. Enter Loss / variance / deviation reason for an unexpected loss, gain, or process deviation.", "Use Add process note for a note or Record deviation / rework for a deviation. If work must stop, choose Put on hold. Use Resume run only after the hold has been addressed."], fields: [{ label: "Loss / variance / deviation reason", requirement: "Conditional on a variance or deviation and any displayed validation.", guidance: "Explain the actual cause instead of changing measured weights to force an expected yield.", example: "Material retained in filter; retained weight recorded on the batch sheet." }], expected: "The run retains the explanation or hold state alongside its process measurements." },
      { id: "complete-extraction-stage", title: "Advance only after the stage is finished", instructions: ["Check the input, output, and displayed calculations, then choose Complete step & continue when the physical step is done.", "Skip optional step appears only for an optional stage. Use it only when that step wasn't performed. At a formulation stage, review Base material (g), Terpene handling, and the calculated addition, then verify the actual scale output after blending."], fields: [
        { label: "Base material (g)", requirement: "Conditional on formulation.", guidance: "Enter the base mass being blended." },
        { label: "Terpene handling", requirement: "Conditional selection for formulation.", guidance: "Choose Native / No Add-Back when no terpene addition occurs, or the actual handling method." },
        { label: "Terpene %", requirement: "Conditional on add-back.", guidance: "Enter the intended percentage and check the calculated grams." },
        { label: "Weight override (g)", requirement: "Optional when an actual addition weight is used.", guidance: "A nonzero override supplies the addition weight; verify it against the scale." }
      ], expected: "The current-stage heading advances after a successful completion, or stays in place with a validation message to resolve." },
      { id: "open-extraction-release", title: "Hand off outputs and QA in Run 360", instructions: ["At the QA / COA or release gate, choose Open Run 360 or Advanced Run 360, then Outputs + QA.", "Create and review output packages, record QA evidence, and release only through the appropriate controls. Use the separate extraction outputs and QA guide for those actions. Process progress alone doesn't prove inventory release or Metrc acceptance."], expected: "The same run opens in Run 360 with its input, output, QA, cost, and traceability context." }
    ],
    completion: ["The intended Run ID is visible and its inputs reflect reservation and consumption accurately.", "The current stage and saved measurements match the physical work.", "The run's output and QA state are reviewed separately from process completion."],
    troubleshooting: [
      { symptom: "Source material is empty for the chosen process.", resolution: "Check Extraction → Inventory and the source's release state, material classification, and available quantity. Receive or transfer eligible material through its normal workflow; don't choose an unrelated process just to expose a lot." },
      { symptom: "Complete step & continue is disabled.", resolution: "Check whether the stage requires Scale output (g), and review the variance explanation and displayed stage validation. Record actual measurements rather than substituting an expected yield." },
      { symptom: "Planning failed after the run may have been created.", resolution: "Find the Run ID in Runs and inspect Inputs in Advanced Run 360. Run creation and input reservation are separate requests, so confirm what saved before creating another run." }
    ],
    sourceFiles: ["frontend/src/pages/ExtractionUnifiedPage.tsx", "frontend/src/pages/ExtractionOperatorWorkspace.tsx", "frontend/src/pages/ExtractionPage.tsx", "backend/app/routers/extraction.py", "modules/extraction/repository.py", "modules/extraction/hardening_hooks.py"]
  },
  "/help/extraction/outputs-qa": {
    title: "Create extraction outputs and record QA release",
    category: "production",
    summary: "Create measured output lots, attach QA evidence, and distinguish local release from a queued state-system action.",
    navPath: "Production Ops → Production → Extraction → Advanced Run 360 → Outputs + QA",
    appPath: "/production/extraction",
    beforeYouStart: ["Open the correct extraction run and check its consumed inputs.", "Create the actual output product in Product Master first. Output quantity uses that product's base unit.", "Have reviewed lab evidence available. A release requires a passed COA for every releasable output."],
    steps: [
      { id: "open-extraction-output-context", title: "Review the run before creating output", instructions: ["Select the run in Extraction, choose Open Run 360, and review Overview and Inputs.", "Compare Consumed input, Recorded output, and Yield. These are calculated from saved records; a missing output record doesn't mean the material physically disappeared."], expected: "The batch and source records match the work being packaged." },
      { id: "create-extraction-output", title: "Create the measured output lot", instructions: ["Open Outputs + QA and expand Create output / WIP package. Select Output product and enter Internal lot / batch code, Output quantity, and Output label.", "Verify the product's base unit before entering the quantity. Choose Create quarantined output once for this physical output."], fields: [
        { label: "Output product", requirement: "Required.", guidance: "Select the actual WIP or finished product; its base unit is sent with the quantity." },
        { label: "Internal lot / batch code", requirement: "Required.", guidance: "Use the actual new lot identifier and check that this output hasn't already been created.", example: "EXT-DEMO-042-OUT" },
        { label: "Output quantity", requirement: "Positive measured quantity.", guidance: "Enter the measured output in the selected product's base unit." },
        { label: "Output label", requirement: "Description with a product-name default.", guidance: "Keep a label that clearly identifies this output." }
      ], warning: "This creates a quarantined inventory output. Check existing rows before repeating a request with an uncertain result.", expected: "An output row appears with Qty, Unit, Status, and COA. The success message identifies a quarantined output." },
      { id: "record-extraction-qa-evidence", title: "Attach the QA decision to the correct output", instructions: ["Expand Record QA event. Select Output, then the actual QA event and Result.", "Enter COA / lab document reference and QA note. Use Deviation code when applicable. Choose Record QA and review the event in the QA / release history."], fields: [
        { label: "Output", requirement: "Required output selection.", guidance: "Match the sample and lab evidence to this exact output." },
        { label: "QA event", requirement: "Required selection.", guidance: "Choose the actual action, such as sample_submitted, coa_attached, failure, retest, remediation, deviation, or hold." },
        { label: "Result", requirement: "Required selection.", guidance: "Use pending, passed, failed, or not_applicable according to the reviewed evidence." },
        { label: "COA / lab document reference", requirement: "Supporting reference for the lab decision.", guidance: "Enter the reference for the reviewed document, not an invented test result." },
        { label: "Deviation code", requirement: "Optional unless needed for the event.", guidance: "Use your documented deviation identifier." },
        { label: "QA note", requirement: "Decision context.", guidance: "Explain the evidence or follow-up required." }
      ], expected: "The QA history shows the saved event and the output's COA state updates." },
      { id: "release-extraction-output", title: "Release only the reviewed output inventory", instructions: ["Review every output's Status and COA. Address pending, failed, or held outputs through QA before proceeding.", "When Release run + output inventory is available and the release is approved, choose it and wait for the saved result. Recheck Overview and the output table afterward."], warning: "This action releases the run and output inventory locally. It isn't an instruction to skip lab review, and it doesn't establish Metrc acceptance.", expected: "The release result is shown and the run and output status reflect the recorded release." },
      { id: "record-extraction-cost", title: "Add actual processing costs", instructions: ["Open COGS and review existing cost rows so you don't enter a cost twice.", "Expand Add cost, choose Category, enter Amount USD and Cost note, then Post cost. Compare Total and Cost per recorded output unit after the save."], fields: [
        { label: "Category", requirement: "Required selection.", guidance: "Choose the actual cost category offered by the form." },
        { label: "Amount USD", requirement: "Positive amount to post.", guidance: "Enter the cost of this event in dollars." },
        { label: "Cost note", requirement: "Optional supporting context.", guidance: "Reference the time sheet, packaging issue, or other cost basis." }
      ], expected: "The new cost appears in the cost table and totals refresh." },
      { id: "review-extraction-provider-status", title: "Check traceability separately", instructions: ["Open Traceability and read the saved action Status, Reference, and Error. No state-system actions means no provider action is attached to this run.", "If an authorized package-creation request is needed, expand Queue output package creation, select Output, enter New package tag and Metrc Item name, and use Validate + queue. Then use Open Traceability Operations to inspect execution and reconciliation. Queued is not accepted."], fields: [
        { label: "Output", requirement: "Required for a package-creation request.", guidance: "Select the output that needs the provider package." },
        { label: "New package tag", requirement: "Required.", guidance: "Use the assigned real tag after checking the output's existing provider state." },
        { label: "Metrc Item name", requirement: "Provider item identity for validation.", guidance: "Use the exact configured item name." },
        { label: "Metrc location (optional)", requirement: "Optional.", guidance: "Use the applicable provider location when required for this operation." }
      ], expected: "You can distinguish local output release from the state-system action's current status and evidence." }
    ],
    completion: ["Outputs + QA shows each output quantity, unit, status, and COA state.", "QA history contains the supporting decisions.", "Any provider request is reviewed by its recorded status, not assumed successful because local inventory exists."],
    troubleshooting: [
      { symptom: "Release run + output inventory isn't available.", resolution: "Ensure an output exists and review every WIP or quarantined output's COA. Record the supported passed result only after the evidence is reviewed; completed runs cannot be modified through this action." },
      { symptom: "Validate + queue fails or the provider status is uncertain.", resolution: "Read the validation error or open Traceability Operations to inspect the existing action and reconciliation evidence. Don't request another package with the same tag until the first action's outcome is known." }
    ],
    sourceFiles: ["frontend/src/pages/ExtractionUnifiedPage.tsx", "frontend/src/pages/ExtractionPage.tsx", "backend/app/routers/extraction.py", "modules/extraction/repository.py"]
  },
  "/help/white-label-repack": {
    title: "Save and approve a White Label / Repack plan",
    category: "production",
    summary: "Build a package and margin plan around existing source inventory, save a draft, and approve its production handoff.",
    navPath: "Production Ops → Production → White Label / Repack",
    appPath: "/production/repack",
    beforeYouStart: ["The source must already exist as weight-based inventory in the active facility, with available or released status, passed QA, and COA evidence.", "Have the bulk weight, cost, package sizes, packaging costs, and target prices. Planning figures don't release inventory or certify labels.", "Saving and approval require access to manage White Label plans. Approval also requires a production-capable facility."],
    steps: [
      { id: "select-repack-source", title: "Name the plan and choose existing inventory", instructions: ["Enter Scenario Name. Use Find source lot or package to narrow Existing source inventory, then select the correct lot.", "Match the lot, product, package, and status. Search narrows the first 100 matches, so use a specific identifier when needed."], fields: [
        { label: "Scenario Name", requirement: "Required to save.", guidance: "Use a name that identifies the source and intended job.", example: "Demo flower 3.5 g repack" },
        { label: "Find source lot or package", requirement: "Optional search.", guidance: "Search the known lot, package, or product." },
        { label: "Existing source inventory", requirement: "Required to save or approve.", guidance: "Choose the real source lot in this facility." }
      ], expected: "The form is tied to the intended source inventory, but no draft has been saved yet." },
      { id: "enter-repack-bulk-lot", title: "Enter the bulk lot facts", instructions: ["Open Step 1: Bulk Lot. Enter the actual source identity, weight and unit, total purchase cost, COA reference, and reported percentages.", "Use Advanced Lot Details for the source package, batch, dates, and supporting notes. Typed COA or potency values don't replace the source lot's stored QA evidence."], fields: [
        { label: "Strain Name *", requirement: "Marked required in the form.", guidance: "Use the source strain name." },
        { label: "Strain Type *", requirement: "Required selection.", guidance: "Choose the documented type, or Unknown when it isn't known." },
        { label: "Cultivator Name *", requirement: "Marked required in the form.", guidance: "Use the actual cultivator." },
        { label: "Vendor Name *", requirement: "Marked required in the form.", guidance: "Use the supplier for this source lot." },
        { label: "Bulk Weight *", requirement: "Positive weight within available inventory.", guidance: "Enter the amount this plan uses after existing commitments." },
        { label: "Weight Unit *", requirement: "Required selection.", guidance: "Choose g, oz, or lb to match the entered bulk weight." },
        { label: "Total Bulk Cost ($) *", requirement: "Nonnegative cost; marked required.", guidance: "Enter the total source cost, not a per-gram price." },
        { label: "Certificate of Analysis (COA) Link *", requirement: "Marked required in the form.", guidance: "Use the reviewed source document reference." },
        { label: "THCA (%) *", requirement: "Percentage from 0 to 100.", guidance: "Use the reported THCA percentage from the source evidence." },
        { label: "Terpenes (%) *", requirement: "Percentage from 0 to 100.", guidance: "Use the reported terpene percentage." }
      ], expected: "The plan's source facts and weight units match the selected inventory and evidence." },
      { id: "enter-repack-costs", title: "Add the costs and loss assumptions", instructions: ["Open Step 2: Costs. Enter the purchase discount, expected shrink, labor cost, and other costs.", "Expand Advanced Costs when freight, testing, administration, QA hold loss, trim loss, or moisture loss applies. These are planning assumptions, so don't treat the resulting usable weight as an actual inventory adjustment."], fields: [
        { label: "Purchase Discount (%)", requirement: "Optional assumption, 0 to 100.", guidance: "Enter the agreed discount percentage." },
        { label: "Expected Shrink Loss (%)", requirement: "Optional assumption, 0 to 100.", guidance: "Estimate physical shrink without altering the source balance." },
        { label: "Total Labor Cost ($)", requirement: "Nonnegative planning amount.", guidance: "Enter the total labor cost for the job." },
        { label: "Other Costs ($)", requirement: "Optional nonnegative amount.", guidance: "Include costs not captured elsewhere without double-counting them." }
      ], expected: "The cost assumptions are available to the package margin calculation." },
      { id: "allocate-repack-sizes", title: "Allocate weight to package sizes", instructions: ["Open Step 3: Package Plan. Enable only the rows you intend to make; use Add row for another size.", "Set package_size_g, allocation_pct, and target_retail_price_per_unit. Enabled allocations must total no more than 100%. A total below 100% leaves material unallocated. Turn off Simple Mode and open Packaging Cost Details to enter each packaging cost."], fields: [
        { label: "enabled", requirement: "Select for each intended output size.", guidance: "Disabled rows aren't part of the package allocation." },
        { label: "package_size_g", requirement: "Positive for every enabled row.", guidance: "Enter grams per finished package.", example: "3.5" },
        { label: "allocation_pct", requirement: "0 to 100 per row; enabled total at most 100.", guidance: "Enter the share of usable weight assigned to this size." },
        { label: "target_retail_price_per_unit", requirement: "Nonnegative planning price.", guidance: "Enter the target retail price for one finished package." }
      ], expected: "The allocation warnings reflect the actual total and every enabled size is positive." },
      { id: "review-repack-results", title: "Review units, leftovers, and missing evidence", instructions: ["Open Step 4: Results. Check Usable Weight, Total Units, Leftover Grams, and each row's Status and Missing Inputs before trusting Gross Margin %.", "Open Step 5: Compliance and review Requirement and Status. The checklist describes entered documentation; approval separately validates the source inventory's QA and COA evidence."], expected: "You understand the expected units, rounding leftovers, incomplete margins, and documentation gaps." },
      { id: "save-repack-draft", title: "Save the draft and confirm what was stored", instructions: ["Choose Save durable plan. Wait for the saved-plan notice and confirm Plan status is draft.", "To return later, choose the plan in Load Scenario and select Apply Loaded Scenario. Save any intended edits before approval; Unsaved changes means the displayed form differs from the saved version."], expected: "A saved draft can be selected and loaded with its source and scenario values." },
      { id: "approve-repack-plan", title: "Approve the saved handoff", instructions: ["Review the saved draft one last time, then choose Approve plan. The app rechecks the source availability and evidence.", "Use the resulting Production Run 360 or Package Studio link to execute the approved job. In Package Studio, enter actual outputs against the approved source. Use Label Studio for the labels."], warning: "Approval creates a production handoff and the plan stops being an editable draft. It doesn't reserve or consume inventory. Confirm the source and package plan before approval.", expected: "The approved plan shows execution links and the message that inventory has not been reserved or consumed." },
      { id: "manage-repack-versions", title: "Keep later changes separate from approved work", instructions: ["Use Duplicate Scenario when planning a variation, then name and save the new plan. Clear Scenario clears the working form, so save changes you need first.", "Use Cancel draft only for a draft you no longer need. Review an approved job through Production Run 360 rather than trying to cancel it as a draft. Export Retail Ops Report produces the planning PDF; it isn't evidence of finished output."], expected: "The original approved handoff remains identifiable while later planning changes are kept in their own saved draft." }
    ],
    completion: ["The plan reloads from Load Scenario with the correct source and allocation.", "An approved plan shows Production Run 360 and Package Studio links.", "Actual execution and label review remain separate from the margin estimate."],
    troubleshooting: [
      { symptom: "Saving rejects a source even though it appears in the dropdown.", resolution: "The dropdown is a search result, not approval. Check source status, passed QA, COA evidence, unit consistency, and availability after commitments. Correct the source record through its normal workflow." },
      { symptom: "Approve plan is disabled or the plan changed elsewhere.", resolution: "Save intended edits, then reload the current draft before approving. If another operator changed its revision or status, review that version instead of overwriting it." },
      { symptom: "Margins are incomplete or unexpectedly high.", resolution: "Read Missing Inputs in Step 4: Results, then check bulk cost, enabled allocation, target prices, and Packaging Cost Details. Missing costs aren't proof that the work is free." }
    ],
    sourceFiles: ["frontend/src/pages/WhiteLabelRepackPage.tsx", "frontend/src/pages/whiteLabelRepackParity.ts", "frontend/src/pages/PackageStudioPage.tsx", "backend/app/routers/white_label.py", "modules/repack/execution.py"]
  },
  "/help/package-studio": {
    title: "Transform a package in Package Studio",
    category: "production",
    summary: "Define actual outputs and source use, review the mass balance, and commit a local package transformation with its source trail.",
    navPath: "Production Ops → Production → Package Studio",
    appPath: "/production/package-studio",
    beforeYouStart: ["Have an available source package in the active facility and active output products.", "Measure the physical output and loss before committing. Finished quantity and Source used can use different units.", "For approved White Label work, open Package Studio from the saved plan so execution keeps the approved source relationship."],
    steps: [
      { id: "choose-package-action", title: "Choose the package action", instructions: ["Open New Run and choose Package action: Breakdown, Pack Down, Build Run, Multi-Build, Sample Pull, Rework, or Source Correction.", "Choose the action that describes the work. Breakdown and Sample Pull keep the source product identity. Multi-Build requires at least two outputs; Sample Pull uses one output in this screen."], fields: [{ label: "Package action", requirement: "Required selection.", guidance: "Match the action to the physical transformation." }], expected: "The output form is configured for the selected action." },
      { id: "select-package-source", title: "Check the exact source package", instructions: ["Select Source package and compare Source, Product, Location, and Available with the physical package.", "If you opened an approved White Label handoff, keep its approved source. A missing approved source must be resolved in the production run before execution."], fields: [{ label: "Source package", requirement: "Required available source.", guidance: "Match both product and lot or package identifier. Read Available in its displayed unit." }], expected: "The source identity and available balance match the intended work." },
      { id: "define-package-outputs", title: "Enter the finished outputs", instructions: ["Set Number of outputs between 1 and 8. For every output, select Output product when editable and enter a unique Lot / package code.", "Enter Finished quantity and Finished unit for the inventory being created. Add the actual METRC package tag only when known. The tag is a reference here; entering it doesn't create a provider package."], fields: [
        { label: "Number of outputs", requirement: "1 to 8; Sample Pull is fixed to one.", guidance: "Use one row per output lot." },
        { label: "Output product", requirement: "Required; locked for Breakdown and Sample Pull.", guidance: "Choose the actual output product rather than accepting an unrelated default." },
        { label: "Lot / package code", requirement: "Required and unique within the run and existing inventory.", guidance: "Use the output's real identifier.", example: "DEMO-PACK-042-A" },
        { label: "METRC package tag", requirement: "Optional in this form.", guidance: "Use a known assigned tag; leave it blank rather than inventing one." },
        { label: "Finished quantity", requirement: "Positive for every output.", guidance: "Enter the measured or counted quantity being created." },
        { label: "Finished unit", requirement: "Required unit for the output quantity.", guidance: "Check the product's unit and the quantity together, such as 100 unit rather than 100 g." }
      ], expected: "Every output describes a distinct inventory lot with a positive finished quantity." },
      { id: "enter-package-source-use", title: "Account for source use and loss", instructions: ["For each output, enter Source used in the unit shown beside that field. This is the source-equivalent amount consumed to make that output, not necessarily the finished count.", "Enter Recorded loss / waste in the source unit and explain it in Reason / work note. Select Output purpose or Sample type where shown. Review Remaining source before continuing."], fields: [
        { label: "Source used (g)", requirement: "Positive for each output; the label uses the selected source unit.", guidance: "For a gram-based source, enter grams assigned to this output. With another source unit, use that displayed unit." },
        { label: "Recorded loss / waste (g)", requirement: "Nonnegative; the label uses the selected source unit.", guidance: "Enter measured loss separately from source assigned to outputs." },
        { label: "Reason / work note", requirement: "Optional operational explanation.", guidance: "Explain loss, rework, or correction so the next operator can follow the source trail." },
        { label: "Output purpose", requirement: "Shown for applicable actions.", guidance: "Choose the actual standard or sample purpose." },
        { label: "Sample type", requirement: "Required selection for Sample Pull.", guidance: "Choose Lab sample, Trade sample, or Retail sample as appropriate." }
      ], expected: "Mass balance preview shows source selected, output equivalents, loss, and the remaining source balance." },
      { id: "review-package-balance", title: "Review the server-checked plan", instructions: ["Wait for the Balanced result. Resolve validation errors such as missing output codes, zero quantities, repeated codes, or excessive source use.", "Check that output equivalents plus loss equal the source selected and that Remaining source is plausible. Read the note that external sync remains Not requested."], expected: "A successful preview is visible without changing inventory." },
      { id: "commit-package-transform", title: "Commit the reviewed transformation", instructions: ["Select I reviewed the source, outputs, and mass balance. Choose the displayed Commit action, such as Commit Pack Down.", "Wait for the run-number message confirming how many output packages were committed. Record that run number before leaving the page."], warning: "Commit consumes source inventory and creates output inventory. Don't click again after an uncertain response until you've checked Recent Runs and the source balance. This doesn't automatically create or adjust packages in Metrc.", expected: "A success message names the committed run and its output count." },
      { id: "verify-package-source-trail", title: "Check the saved run and source trail", instructions: ["Open Recent Runs and find the new run. Review its external sync status independently from the local commit.", "Open Source Trail, choose Package, and review Current balance, Parent source, and Downstream use. Expand the relevant run to inspect its outputs."], fields: [{ label: "Package", requirement: "Required selection in Source Trail.", guidance: "Choose the available source or output whose relationships you want to inspect." }], expected: "The saved transformation appears in Recent Runs and its available packages show the recorded source relationships." }
    ],
    completion: ["The commit message identifies the run and output count.", "Recent Runs shows the operation, and Source Trail shows the applicable parent or downstream relationship.", "External sync is understood separately from the local inventory commit."],
    troubleshooting: [
      { symptom: "The form says it consumes more than the source contains.", resolution: "Check each Source used value and Recorded loss / waste in the source unit. Reduce the plan to the actual available amount or resolve the source inventory discrepancy before committing." },
      { symptom: "No Commit button is available for your role.", resolution: "You can review the plan, but an authorized operator must commit inventory transformations. Don't switch identities or alter source state to bypass the permission." },
      { symptom: "A consumed package isn't offered in Source Trail.", resolution: "The picker uses the available-package list. Use Recent Runs or open the package identifier in Package 360 to investigate a depleted source." }
    ],
    sourceFiles: ["frontend/src/pages/PackageStudioPage.tsx", "backend/app/routers/package_studio.py", "modules/package_studio/service.py", "modules/repack/execution.py"]
  },
  "/help/production/inventory": {
    title: "Review and receive production inventory",
    category: "production",
    summary: "Find production packages, read available quantity after commitments, and receive material into the active facility.",
    navPath: "Production Ops → Inventory → Materials",
    appPath: "/production/inventory",
    beforeYouStart: ["Confirm the active facility and that the page shows PRODUCTION OPS.", "For receiving, have the existing Product Master item, actual quantity, unit, lot or package identity, source, and transfer reference.", "Use the transfer receipt workflow for an existing DoobieLogic transfer so you don't receive the same shipment twice."],
    steps: [
      { id: "filter-production-inventory", title: "Find the material or package", instructions: ["Search the material, package, lot, or room. Narrow Status, Source, Room, and Material type as needed.", "Use Clear filters when a known package is missing. Production uses Packages as its inventory view, so inspect the exact lot rather than treating a product total as one physical package."], fields: [
        { label: "Status", requirement: "Optional filter.", guidance: "Limit the list to the status you need to investigate." },
        { label: "Source", requirement: "Optional filter.", guidance: "Choose the known source or supplier." },
        { label: "Room", requirement: "Optional filter.", guidance: "Choose the physical location being checked." },
        { label: "Material type", requirement: "Optional filter.", guidance: "Narrow the list to the relevant production material class." }
      ], expected: "The visible rows match the intended material and facility context." },
      { id: "read-production-availability", title: "Compare on-hand stock with available stock", instructions: ["Open Columns if you need to show On Hand, Available, Reserved For, and Room.", "Read Available before planning work. The page subtracts active wholesale and production commitments; stock on hand isn't necessarily free to use. Check hold or quarantine status separately."], expected: "You can explain the difference between physical stock and uncommitted quantity for the selected package." },
      { id: "inspect-production-package", title: "Inspect the package before changing it", instructions: ["Select one package and choose Package 360 to inspect its identity and history.", "Use Work on package for Package Studio, Transfer for a cross-facility movement, or Audit for a focused count. These are distinct workflows; don't record an adjustment just to simulate a transfer or transformation."], expected: "The intended package opens in the selected workflow with its identity preserved." },
      { id: "open-production-receipt", title: "Choose the material to receive", instructions: ["For a new production receipt, choose Receive inventory. The dialog is titled Receive material.", "Select Material / product by name and SKU. Enter METRC package ID when applicable and Internal lot / batch. At least one identifier is needed; the lot defaults to the package ID when no separate lot is entered."], fields: [
        { label: "Material / product", requirement: "Required.", guidance: "Select the existing material that matches the shipment." },
        { label: "METRC package ID", requirement: "Conditional on tracked material; at least this or an internal lot is required by the form.", guidance: "Copy the actual package identifier from the shipment." },
        { label: "Internal lot / batch", requirement: "Required when there is no package ID.", guidance: "Use the actual lot code when it differs from the package ID.", example: "DEMO-BULK-042" }
      ], expected: "The receipt form identifies the exact product and lot being received." },
      { id: "enter-production-receipt", title: "Enter the physical receipt details", instructions: ["Enter a positive Quantity and verify Unit. The unit list includes the product's base unit and g, kg, oz, lb, and unit.", "Set Room / location and add Source facility / supplier, Manifest / transfer #, and Notes from the actual shipment. A package identifier entered here isn't evidence that a provider receipt was accepted."], fields: [
        { label: "Quantity", requirement: "Positive quantity.", guidance: "Enter the amount physically received in the selected Unit." },
        { label: "Unit", requirement: "Required selection.", guidance: "Match the measured quantity and verify compatibility with the product." },
        { label: "Room / location", requirement: "Defaults to RECEIVING if left blank.", guidance: "Enter the real receiving or storage location." },
        { label: "Source facility / supplier", requirement: "Optional supporting reference.", guidance: "Identify where the material came from." },
        { label: "Manifest / transfer #", requirement: "Optional in this form.", guidance: "Copy the shipment reference when applicable." },
        { label: "Notes", requirement: "Optional.", guidance: "Record receiving details that need follow-up." }
      ], expected: "The form matches the counted or weighed receipt and its receiving location." },
      { id: "post-production-receipt", title: "Post the receipt and check its history", instructions: ["Choose Receive material once and wait for the dialog to close and the receipt message to appear.", "Find the lot in the refreshed package list and inspect Receive history. Check the quantity, unit, and location. This receipt form doesn't collect a COA document; review quality evidence in the relevant workflow before using material that requires it."], warning: "Receive material posts inventory to the active facility. Check Receive history before repeating a request whose result is uncertain.", expected: "The success message identifies the received lot and the refreshed inventory and receipt history show the local receipt." }
    ],
    completion: ["The intended package is visible with its current available quantity and location.", "A posted receipt appears in Receive history and matches the actual shipment."],
    troubleshooting: [
      { symptom: "On Hand is positive but a package can't be transferred or used.", resolution: "Inspect Available, Reserved For, and status. Resolve the existing commitment or hold in its owning workflow instead of treating the physical balance as uncommitted stock." },
      { symptom: "The material isn't in the receiving selector.", resolution: "Check Product Master for the correct active production item. Have the missing material set up before receiving; don't use a similar product as a substitute." },
      { symptom: "Receive inventory is disabled.", resolution: "Check the button's permission explanation and ask an authorized receiving operator to post the receipt in the correct facility." }
    ],
    sourceFiles: ["frontend/src/pages/InventoryPage.tsx", "frontend/src/components/ProductionReceiveInventory.tsx", "backend/app/routers/inventory.py", "backend/app/schemas/inventory.py"]
  },
  "/help/production/inventory/transfers": {
    title: "Transfer production inventory between facilities",
    category: "production",
    summary: "Post the physical transfer out, receive its package lines at the destination, and retain the manifest relationship.",
    navPath: "Production Ops → Inventory → Transfers",
    appPath: "/production/inventory/transfers",
    beforeYouStart: ["Confirm the source and destination facilities and the actual shipment manifest.", "The required state-system transfer must already be created before you confirm it here. These local posting controls don't create that manifest for you.", "Only available, uncommitted packages should be selected. Held, quarantined, failed, and zero-available packages are excluded or blocked."],
    steps: [
      { id: "select-production-transfer-packages", title: "Select the physical packages", instructions: ["Open Transfers in the source facility. Select the packages that are on the shipment manifest.", "Compare Package, Product, Available, and Room for every row. If you entered from an inventory selection, review all selected packages before proceeding."], expected: "The selected rows are the packages actually leaving this facility." },
      { id: "enter-production-transfer-reference", title: "Set the destination and manifest", instructions: ["Choose Destination facility and enter Manifest / transfer #. Add External transfer ID when you have that reference.", "Check each transfer quantity against the manifest and its available balance. Use the row's displayed unit; don't combine unlike units into one physical total."], fields: [
        { label: "Destination facility", requirement: "Required.", guidance: "Choose the receiving facility from the available organization facilities." },
        { label: "Manifest / transfer #", requirement: "Required.", guidance: "Enter the real shipment reference." },
        { label: "External transfer ID", requirement: "Optional.", guidance: "Enter the known state-system or internal transfer identifier." }
      ], expected: "The destination, shipment reference, and positive quantities match the physical shipment." },
      { id: "post-production-transfer-out", title: "Confirm the state-system transfer and post out", instructions: ["Verify that the required state-system transfer and manifest already exist. Select the confirmation checkbox only after that check.", "Choose Post transfer out. Wait for the dispatched message and inspect Transfers sent from this license."], warning: "Post transfer out removes the shipped quantity from source inventory. It doesn't stand in for state-system approval. Check transfer history before retrying an uncertain post.", expected: "Outbound history shows the manifest, destination, and shipped package lines." },
      { id: "open-production-transfer-in", title: "Open the incoming line at the destination", instructions: ["Switch to the receiving facility through the normal facility selector and open Production Inventory Transfers.", "Under Transfers arriving at this license, match the manifest and source license. Choose Receive package for the line that has physically arrived and been accepted in the required state system."], expected: "Post received package opens for the selected inbound line." },
      { id: "post-production-transfer-in", title: "Post the accepted package into destination inventory", instructions: ["Check Destination package ID and Destination lot / batch against the accepted package. Enter Room / location.", "Select I confirm this package was accepted/received in the required state system, then choose Post transfer in. This posts the selected shipment line; it isn't a form for silently changing the shipped amount."], fields: [
        { label: "Destination package ID", requirement: "Use the actual accepted identifier when applicable.", guidance: "Verify the prefilled source identifier against the destination receipt." },
        { label: "Destination lot / batch", requirement: "Destination lot identity.", guidance: "Use the actual received lot code." },
        { label: "Room / location", requirement: "Defaults to RECEIVING if blank.", guidance: "Enter where the package is now stored." }
      ], warning: "Post transfer in adds destination inventory. If the physical quantity doesn't match the line, resolve the discrepancy before posting rather than accepting an incorrect amount.", expected: "The line shows its received state and destination package, with a receipt-posted message." },
      { id: "review-production-transfer-closeout", title: "Review remaining lines or a cancelled shipment", instructions: ["Check every inbound line. A transfer with outstanding lines is still partially received even if one package has been posted.", "For a shipment cancelled before receipt, return to the source facility, document Cancellation reason, and confirm the required state-system cancellation has already been completed before choosing Restore source inventory after cancellation."], fields: [{ label: "Cancellation reason", requirement: "Applicable only when restoring a cancelled shipment.", guidance: "Explain why the shipment was cancelled and retain the actual cancellation reference." }], warning: "Restoring source inventory is an inventory change. Don't use it for goods already received at the destination or before the required state-system cancellation is complete.", expected: "Transfer history reflects the actual received, partially received, or cancelled state." }
    ],
    completion: ["Outbound history identifies the correct manifest and destination.", "Received lines show their destination package and state; outstanding lines remain visible.", "Source and destination inventory reflect only the lines actually posted."],
    troubleshooting: [
      { symptom: "Post transfer out is disabled.", resolution: "Check destination, manifest, selected packages, positive quantities within Available, and the state-system confirmation. If write access is missing, have an authorized transfer operator review it." },
      { symptom: "The inbound transfer isn't visible.", resolution: "Confirm you're in the destination facility named on the outbound record. Check that the source posting succeeded before attempting a separate manual receipt." },
      { symptom: "A receipt request timed out.", resolution: "Reload the inbound transfer and inspect the line's status and destination package before posting again. Don't create a second receipt for the same shipment." }
    ],
    sourceFiles: ["frontend/src/pages/InventoryTransfersPage.tsx", "frontend/src/components/InventoryTransferManager.tsx", "backend/app/routers/inventory_transfers.py", "backend/app/schemas/inventory_transfers.py"]
  },
  "/help/production/package-360": {
    title: "Inspect a production package in Package 360",
    category: "production",
    summary: "Check one package's local balance, source relationships, event history, and separate compliance sync state.",
    navPath: "Production Ops → Inventory → Package 360",
    appPath: "/inventory/packages",
    beforeYouStart: ["Confirm the active production facility and have the exact package, lot, or barcode identifier.", "This is the shared Package 360 route. Opening it from a selected Production Inventory package helps retain the intended package identity."],
    steps: [
      { id: "resolve-production-package", title: "Open the exact package", instructions: ["From Production Inventory, select one package and choose Package 360. On the standalone page, scan or enter Package / lot identifier and choose Open Package 360.", "Match the returned product, SKU, lot, and package ID to the physical package before interpreting its balance."], fields: [{ label: "Package / lot identifier", requirement: "Required on the standalone picker.", guidance: "Scan or enter the actual package, lot, or barcode identifier." }], expected: "The package heading shows the intended product and identity, or an error explains why it couldn't be resolved." },
      { id: "check-production-package-state", title: "Check quantity, unit, and location", instructions: ["Read On hand and its unit. In Current state, review Package ID, Lot code, Location, Status, Received, and Expiration.", "Treat blank dates or locations as missing information. On hand is the physical balance; use Production Inventory to inspect Available and Reserved For before allocating it."], expected: "You know the recorded physical balance and location without assuming all of it is available." },
      { id: "read-production-package-lineage", title: "Follow the recorded source relationship", instructions: ["Under Inputs & outputs, compare source and child package identifiers, quantities, units, and purposes.", "If the page says no Package Studio source inputs or child outputs are linked, it means that relationship isn't recorded here. Don't infer an origin or a transformation that the page doesn't show."], expected: "You can identify the displayed parent and child package relationships and any missing linkage." },
      { id: "read-production-package-timeline", title: "Review what changed and when", instructions: ["Read What happened, in order. Match each event's area, quantity, unit, status, actor, and reference to the work you're investigating.", "Displayed event times use your browser's local time. Unknown time means the timestamp isn't available; it doesn't establish when the action occurred."], expected: "The timeline provides the recorded evidence for the package's movements or other linked events." },
      { id: "check-production-package-sync", title: "Check provider state separately", instructions: ["Read COMPLIANCE SYNC, including Provider, Latest operation, License, Attempts, Last attempt, and Provider reference.", "If a mismatch or error appears, use Inspect reconciliation evidence. Retry eligible indicates that review is required, not that you should submit the action again immediately. A local balance or stored package tag doesn't prove provider acceptance."], expected: "You can distinguish the local package record from the latest state-system action and its evidence." }
    ],
    completion: ["The package identity, On hand unit, location, and status have been checked.", "Recorded source relationships and timeline events support the investigation.", "Any compliance sync mismatch is identified for review rather than assumed resolved."],
    troubleshooting: [
      { symptom: "The identifier isn't found.", resolution: "Confirm the active facility and scan the exact lot or package again. The resolver searches within the active facility; don't substitute a similar package." },
      { symptom: "Package 360 shows stock but Production Inventory shows less available.", resolution: "Compare Available and Reserved For in Production Inventory. Package 360's On hand doesn't subtract every commitment into an available-to-use figure." },
      { symptom: "The Inventory button opens the general inventory route.", resolution: "Return through Production Ops → Inventory → Materials to inspect production availability. The shared Package 360 page uses the general Inventory navigation target." }
    ],
    sourceFiles: ["frontend/src/pages/Package360Page.tsx", "frontend/src/pages/InventoryPage.tsx", "frontend/src/components/MetrcPackageControls.tsx", "frontend/src/lib/workspaceRoutes.ts", "backend/app/routers/package_360.py"]
  },
  "/help/production/products": {
    title: "Set up a production product",
    category: "production",
    summary: "Create or maintain the material and output identities used by production, including units, catalog scope, packaging defaults, and cost history.",
    navPath: "Production Ops → Inventory → Products",
    appPath: "/production/products",
    beforeYouStart: ["Search before creating a product. SKU and UPC conflicts are checked when saving.", "Decide whether the item is Cannabis material, Ingredient, Packaging, Work in process, or Finished good, and agree on its base unit.", "Catalog records can be shared across workspaces. Keep the intended Production Ops catalog scope enabled."],
    steps: [
      { id: "find-production-product", title: "Search the production catalog first", instructions: ["Confirm Production Ops is selected. Search by name, SKU, UPC, or external ID.", "Use Active, Archived, or All and the item-type filter to check for an existing record. Select the matching product to edit its details instead of creating another identity."], expected: "You either select the existing item or establish that a new production item is needed." },
      { id: "create-production-product", title: "Create the material or output identity", instructions: ["Choose New product. Enter Product name, SKU, Item type, and Base unit. Production defaults to Cannabis material and g, so change them when the item is packaging, WIP, or a counted finished product.", "Enter UPC or External product ID only when known. Keep Production Ops selected and choose Create catalog product."], fields: [
        { label: "Product name", requirement: "Required.", guidance: "Use the recognized material or finished-product name.", example: "Demo bulk flower" },
        { label: "SKU", requirement: "Required and unique.", guidance: "Use the internal item code.", example: "DEMO-BULK-042" },
        { label: "Item type", requirement: "Required selection.", guidance: "Choose the role of the item in production." },
        { label: "Base unit", requirement: "Required unit identity.", guidance: "Choose the unit in which the product is tracked. Check g versus unit carefully." },
        { label: "UPC", requirement: "Optional; must not belong to another item.", guidance: "Enter a known barcode identity." },
        { label: "External product ID", requirement: "Optional.", guidance: "Enter the known external product identity rather than a package tag." },
        { label: "Production Ops", requirement: "Enable for a production product.", guidance: "At least one workspace scope must remain enabled." }
      ], expected: "The new product is selected and its catalog detail is visible." },
      { id: "classify-production-product", title: "Save classification and workspace scope", instructions: ["In Classification & scope, fill in the applicable brand, category, subcategory, strain, manufacturer, and product format.", "Review Retail Ops catalog and Production Ops catalog independently, then choose Save catalog rules. Editing these fields alone doesn't save them."], fields: [
        { label: "category", requirement: "Optional classification.", guidance: "Use the team's established category so lists and reports group the product consistently." },
        { label: "product format", requirement: "Optional classification.", guidance: "Describe the actual bulk or finished format." },
        { label: "Production Ops catalog", requirement: "Enable to include the item in production catalog scope.", guidance: "Keep this selected for production materials and outputs." },
        { label: "Description", requirement: "Optional.", guidance: "Add useful distinguishing product information." }
      ], expected: "The saved product detail reflects the classification and intended workspace scope." },
      { id: "set-production-packaging", title: "Save packaging and label facts", instructions: ["For packaged outputs, enter Net content and Net content unit separately from Units per package and Sellable unit. Check Case pack as appropriate.", "Choose Print layout, label dimensions, and Tested sources. Tested sources is editable for the compact split layout. Enter only approved Package warning statement text, then Save packaging & label defaults."], fields: [
        { label: "Net content", requirement: "Nonnegative package content.", guidance: "Enter the content of one finished package.", example: "3.5" },
        { label: "Net content unit", requirement: "Unit for net content.", guidance: "Use the content unit, such as g." },
        { label: "Units per package", requirement: "Positive value.", guidance: "Enter how many sellable units the package contains." },
        { label: "Sellable unit", requirement: "Package unit description.", guidance: "Use the intended sales unit, such as each." },
        { label: "Case pack", requirement: "Nonnegative value.", guidance: "Enter units in a case when applicable." },
        { label: "Print layout", requirement: "Selection with a default.", guidance: "Choose the layout appropriate to the physical label." },
        { label: "Label width (in)", requirement: "0.5 to 12 inches.", guidance: "Match the actual label stock." },
        { label: "Label height (in)", requirement: "0.5 to 12 inches.", guidance: "Match the actual label stock." },
        { label: "Tested sources", requirement: "One or two for the applicable split layout.", guidance: "Choose the number of tested sources represented by the label." },
        { label: "Package warning statement", requirement: "Approved wording when applicable.", guidance: "Use reviewed warning text; this field doesn't verify regulations for you." }
      ], expected: "Label Studio print target and the saved packaging values match the intended package." },
      { id: "map-production-product", title: "Add known external identities", instructions: ["Use Aliases for an alternate product name when needed, then choose Add in that section.", "In External mappings, choose System and enter External ID and External name, then Map external product. This records a mapping; it doesn't create or rename a product in that external system."], fields: [
        { label: "System", requirement: "Required for a mapping.", guidance: "Choose dutchie, metrc, leaflink, or other to match the identity." },
        { label: "External ID", requirement: "Required for a mapping.", guidance: "Use the verified external product ID, not a guessed identifier." },
        { label: "External name", requirement: "Optional supporting name.", guidance: "Copy the known name from the external product record." }
      ], expected: "The alias or mapping appears beneath its section after saving." },
      { id: "record-production-cost-history", title: "Record cost history and review active status", instructions: ["In Price & cost history, select Unit cost or Landed cost as appropriate, enter the nonnegative amount, and choose Record. Review the new history entry and its effective time.", "Use Archive only when the item should stop appearing in active selections. Restore is available on an archived record. Before changing status, check whether operators still need the item for open work."], warning: "Archive changes the product's active state immediately. Confirm the selected product before using it.", expected: "The value history contains the saved amount, and the active or archived badge reflects the intended catalog status." }
    ],
    completion: ["The product can be found in the Production Ops catalog with the intended SKU, item type, and unit.", "Classification and packaging changes are saved with their own save buttons.", "Mappings and cost history show only verified identities and recorded values."],
    troubleshooting: [
      { symptom: "Create catalog product reports a duplicate SKU or UPC.", resolution: "Search All, including archived items, for that identifier. Use the existing product or resolve the identity conflict instead of adding a suffix to hide a duplicate." },
      { symptom: "A product disappears from the production list after editing scope.", resolution: "Check All and the other workspace scope. Restore Production Ops catalog on the correct record if it was unintentionally disabled, then Save catalog rules." },
      { symptom: "A new item has the wrong base unit.", resolution: "Stop before receiving or consuming inventory against it. This detail screen doesn't offer a general base-unit edit; ask the catalog owner to correct the identity through the supported process." }
    ],
    sourceFiles: ["frontend/src/pages/ProductMasterPage.tsx", "backend/app/routers/product_master.py", "frontend/src/lib/workspaceRoutes.ts"]
  },
  "/help/production/inventory-audits": {
    title: "Count production inventory and close an audit",
    category: "production",
    summary: "Start a scoped production count, record and recount physical quantities, then review whether completion should post inventory corrections.",
    navPath: "Production Ops → Inventory → Inventory Audits",
    appPath: "/inventory/audits",
    beforeYouStart: ["Use Production Ops and the correct facility. The audit route is shared, and the active operation or selected inventory focus determines the count context.", "For a focused count, select the exact packages in Production Inventory and choose Audit.", "Production counts use existing production inventory. The Dutchie snapshot upload is a retail-only workflow."],
    steps: [
      { id: "choose-production-audit-scope", title: "Review the inventory selected for counting", instructions: ["Open the audit from Production Inventory. If a focused selection is shown, read how many package / lot rows will be selected and confirm they are the intended production scope.", "Use Clear inventory focus if that selection is wrong. For a general new audit, review Inventory to count and select only the packages you intend to count."], fields: [{ label: "Inventory to count", requirement: "At least one package for a general new audit.", guidance: "Select the physical packages included in this count; excluded packages won't be counted by this audit." }], expected: "The count scope matches the intended production packages rather than an unrelated retail or previous selection." },
      { id: "start-production-audit", title: "Name and start the audit", instructions: ["Enter Audit name / number and a nonnegative Recount tolerance. Choose Blind first count if the first pass should hide expected stock.", "Use Start focused audit for a focused selection, then find its name in Audit Dashboard and choose Open. Start New Audit in the general form opens the new audit directly. In the general form, add Scope and Notes (optional) so another operator understands the count."], fields: [
        { label: "Audit name / number", requirement: "Required.", guidance: "Use an identifier for this count session.", example: "PROD-DEMO-ROOM-A" },
        { label: "Recount tolerance", requirement: "Nonnegative value.", guidance: "Set the allowed count variance threshold under your team's count procedure; this isn't a percentage field." },
        { label: "Blind first count", requirement: "Optional count setting.", guidance: "Hide expected quantity during the first pass to encourage an independent physical count." },
        { label: "Scope", requirement: "General-audit description.", guidance: "Describe the room, material group, or count boundary." },
        { label: "Notes (optional)", requirement: "Optional.", guidance: "Record any special count instructions." }
      ], expected: "The saved audit opens and shows Products scanned, Remaining, Recounts, and Scan exceptions." },
      { id: "find-production-count-item", title: "Find the physical item to count", instructions: ["Use the camera scanner or expand Bluetooth / USB scanner or typed code. Enter Scan or enter item code and choose Find item.", "If you can't scan, expand Cannot scan? Choose the inventory item, select Inventory item, and choose Enter count for selected item. Verify product, lot, and location in the count dialog."], fields: [
        { label: "Scan or enter item code", requirement: "Required for typed lookup.", guidance: "Use an exact package, lot, SKU, or other recognized code from the item." },
        { label: "Inventory item", requirement: "Required for manual selection.", guidance: "Match the actual lot and location before opening the count." }
      ], expected: "Enter inventory count opens for the intended audit line." },
      { id: "save-production-physical-count", title: "Record the measured physical quantity", instructions: ["Enter Physical quantity in stock in the audit line's unit. Choose Variance reason and add Count note (optional) when useful.", "Choose Save & scan next. If the app says the capture is stored locally, it isn't committed to the server yet. Keep that distinction in mind when reviewing progress."], fields: [
        { label: "Physical quantity in stock", requirement: "Nonnegative actual quantity.", guidance: "Count or weigh the item using its displayed unit; enter zero only when you verified no stock is present." },
        { label: "Variance reason", requirement: "Reason selection for the count.", guidance: "Choose the available reason that describes the discrepancy." },
        { label: "Count note (optional)", requirement: "Optional.", guidance: "Explain the physical finding or the evidence for a variance.", example: "Counted sealed units and the open tray separately." }
      ], expected: "A successful server save advances progress; an offline save is clearly marked as a local capture awaiting replay." },
      { id: "recount-production-discrepancies", title: "Resolve recounts and exceptions", instructions: ["Review Recounts and use Recount scanner for the lines needing another count. Recheck the physical stock rather than copying the first quantity.", "Resolve Scan exceptions and any offline captures before treating the scope as finished. Use Pause Audit to leave and return, or Stop & Review when work should stop with the current results preserved."], expected: "The intended lines are counted, required recounts are resolved, and incomplete work remains visible." },
      { id: "review-production-audit-report", title: "Review the report before completion", instructions: ["Choose Generate Current Report. Compare Expected, First Count, Recount, Final Count, Variance, Unit, Reason, and Notes.", "Review Activity log when a quantity needs explanation. Export CSV or Export Excel if you need a review copy. A Partial report isn't a completed audit."], expected: "The report explains each count and variance without presenting unscanned items as finished." },
      { id: "complete-production-audit", title: "Choose whether to post approved corrections", instructions: ["When no remaining counts or recounts remain, review the completion panel and select I reviewed the count and confirm the intended audit scope is complete.", "Select Post approved corrections to the append-only inventory ledger only when those corrections are authorized. Choose Complete Audit, then verify the completed-history message."], warning: "Completing with corrections selected changes inventory. Review the count scope, units, and approved variances first. A local audit correction isn't proof of a state-system adjustment.", expected: "The page states that the audit is completed and preserved as a historical record." }
    ],
    completion: ["The intended scope is fully counted and required recounts are resolved.", "The completed-history message appears and the report preserves final counts and variances.", "The decision to post inventory corrections was made explicitly."],
    troubleshooting: [
      { symptom: "The page opens the wrong operation or an old focused selection.", resolution: "Return to Production Inventory in the correct facility, select the intended packages, and choose Audit. Clear inventory focus when the previously staged scope is no longer appropriate." },
      { symptom: "A scan doesn't match one unique item.", resolution: "Check the exact package or lot code and use manual Inventory item selection when needed. Confirm the lot and room before counting; don't choose a similar item to clear the scan." },
      { symptom: "Offline count captures are still listed.", resolution: "Reconnect in the same authorized facility context and wait for verified replay. Review any replay error. Discard local capture only if you're intentionally removing that unsaved capture and will account for the physical count another way." },
      { symptom: "Complete Audit is unavailable or rejected.", resolution: "Check Remaining, Recounts, offline captures, and the review checkbox. Completion also requires permission; have the authorized reviewer complete the audit rather than changing the count scope to bypass outstanding work." }
    ],
    sourceFiles: ["frontend/src/components/FocusedInventoryAudits.tsx", "frontend/src/components/InventoryAudits.tsx", "frontend/src/pages/InventoryPage.tsx", "backend/app/routers/audits.py", "backend/app/schemas/inventory.py", "modules/inventory_audit/repository.py"]
  }
};
