import { expect, test, type Locator, type Page, type Response } from "@playwright/test";

/**
 * Human acceptance gate: one zero-training operator takes a new Blue Dream
 * lineage from plant creation to a received cross-license package, then proves
 * the source trail in Package 360 / Recall 360 and Doobie Agent.
 *
 * All business-state mutations happen through the same React controls an
 * operator uses. Network responses are observed only to capture durable IDs and
 * to quantify API friction; they are never used to mutate application state.
 */

type Friction = {
  clicks: number;
  decisions: number;
  manualInputs: number;
  duplicateEntries: number;
  contextSwitches: number;
  backtracks: number;
  warnings: string[];
  handoffGaps: string[];
  deadEnds: string[];
  browserErrors: string[];
  api4xx: string[];
  api5xx: string[];
  milestones: string[];
};

const IDs = {
  plant: "ZT-BD-001",
  harvest: "ZT-HARV-BD-001",
  harvestLot: "ZT-BD-HARVEST-001",
  run: "ZT-EXT-BD-001",
  extractLot: "ZT-BD-EXTRACT-001",
  finishedLot: "ZT-BD-VAPE-1G-PKG",
  finishedTag: "ZT-BD-VAPE-METRC",
  order: "ZT-SO-BD-001",
  fulfillment: "ZT-SHIP-BD-001",
  manifest: "ZT-XFER-BD-001",
  destinationLot: "ZT-BD-VAPE-1G-DEST",
  destinationTag: "ZT-BD-VAPE-METRC-DEST",
};

const friction: Friction = freshFriction();

function freshFriction(): Friction {
  return {
    clicks: 0,
    decisions: 0,
    manualInputs: 0,
    duplicateEntries: 0,
    contextSwitches: 0,
    backtracks: 0,
    warnings: [],
    handoffGaps: [],
    deadEnds: [],
    browserErrors: [],
    api4xx: [],
    api5xx: [],
    milestones: [],
  };
}

function requiredEnv(name: string) {
  const value = String(process.env[name] ?? "").trim();
  if (!value) throw new Error(`${name} is required for the zero-training acceptance run.`);
  return value;
}

async function operatorClick(locator: Locator) {
  friction.clicks += 1;
  await locator.click();
}

async function operatorFill(locator: Locator, value: string) {
  friction.manualInputs += 1;
  await locator.fill(value);
}

async function operatorSelect(locator: Locator, labelOrValue: string | RegExp) {
  friction.clicks += 1;
  friction.decisions += 1;
  if (typeof labelOrValue === "string") {
    await locator.selectOption({ label: labelOrValue }).catch(async () => locator.selectOption(labelOrValue));
    return;
  }
  const options = await locator.locator("option").allTextContents();
  const match = options.find(value => labelOrValue.test(value));
  if (!match) throw new Error(`No select option matched ${labelOrValue}. Available: ${options.join(" | ")}`);
  await locator.selectOption({ label: match });
}

async function operatorCheck(locator: Locator) {
  friction.clicks += 1;
  friction.decisions += 1;
  await locator.check();
}

async function rowClick(row: Locator) {
  friction.clicks += 1;
  await row.click();
}

async function switchWorkspace(page: Page, path: string, facilityId: string, operation: "Production Ops" | "Retail Ops") {
  friction.contextSwitches += 1;
  await page.evaluate(({ facilityId, operation }) => {
    localStorage.setItem("buyer-dash-facility", facilityId);
    localStorage.setItem("buyer-dash-operation", operation);
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  }, { facilityId, operation });
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function milestone(label: string) {
  friction.milestones.push(label);
}

async function collectWarnings(page: Page) {
  const warnings = await page.locator(".warning-banner:visible").allTextContents();
  for (const value of warnings.map(item => item.trim()).filter(Boolean)) {
    if (!friction.warnings.includes(value)) friction.warnings.push(value);
  }
}

async function auditDeadEnd(page: Page, stage: string) {
  const body = (await page.locator("body").innerText()).toLowerCase();
  const patterns = ["something went wrong", "unexpected error", "page not found", "cannot continue", "service unavailable"];
  const hit = patterns.find(pattern => body.includes(pattern));
  if (hit) friction.deadEnds.push(`${stage}: ${hit}`);
}

function attachRuntimeFriction(page: Page) {
  page.on("pageerror", error => friction.browserErrors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error") friction.browserErrors.push(`console: ${message.text()}`);
  });
  page.on("response", response => {
    if (!response.url().includes("/api/")) return;
    const status = response.status();
    const entry = `${status} ${response.request().method()} ${response.url()}`;
    if (status >= 500) friction.api5xx.push(entry);
    else if (status >= 400) friction.api4xx.push(entry);
  });
}

async function awaitJson(responsePromise: Promise<Response>) {
  const response = await responsePromise;
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy();
  return response.json() as Promise<Record<string, unknown>>;
}

async function completeCurrentExtractionStep(page: Page, options: { heading: string | RegExp; input?: string; output?: string; optional?: boolean }) {
  await expect(page.getByRole("heading", { name: options.heading }).first()).toBeVisible({ timeout: 15_000 });
  if (options.optional) {
    await operatorClick(page.getByRole("button", { name: "Skip optional step" }));
  } else {
    if (options.input) await operatorFill(page.getByLabel("Stage input (g)"), options.input);
    if (options.output) await operatorFill(page.getByLabel("Scale output (g)"), options.output);
    await operatorClick(page.getByRole("button", { name: "Complete step & continue" }));
  }
  await expect(page.getByText("Process event saved and run status refreshed.").first()).toBeVisible({ timeout: 15_000 }).catch(() => undefined);
}

test("zero-training operator takes Blue Dream from plant to received wholesale package and proves lineage", async ({ page }, testInfo) => {
  const organizationId = requiredEnv("ALPHA_ORGANIZATION_ID");
  const sourceFacilityId = requiredEnv("ALPHA_FACILITY_ID");
  const destinationFacilityId = requiredEnv("ALPHA_DESTINATION_FACILITY_ID");
  Object.assign(friction, freshFriction());
  attachRuntimeFriction(page);

  await page.addInitScript(({ organizationId, sourceFacilityId }) => {
    localStorage.setItem("buyer-dash-theme", "dark");
    localStorage.setItem("buyer-dash-organization", organizationId);
    localStorage.setItem("buyer-dash-facility", sourceFacilityId);
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  }, { organizationId, sourceFacilityId });

  // 1. CULTIVATION — create a plant and move it to flowering.
  await switchWorkspace(page, "/production/inventory", sourceFacilityId, "Production Ops");
  await expect(page.getByRole("heading", { name: "Production Inventory" })).toBeVisible();
  await operatorClick(page.getByRole("button", { name: "Plants" }));
  await operatorClick(page.getByRole("button", { name: "Add one plant" }));
  await operatorFill(page.getByLabel("Plant tag"), IDs.plant);
  await operatorFill(page.getByLabel("Strain"), "Blue Dream");
  await operatorSelect(page.getByLabel("Phase"), "clone");
  await operatorFill(page.getByLabel("Room"), "ZT-VEG-A");
  await operatorFill(page.getByLabel("Estimated harvest"), "2026-10-15");
  await operatorFill(page.getByLabel("Notes"), "Zero-training operator acceptance plant.");
  await operatorClick(page.getByRole("button", { name: "Save plant" }));
  await expect(page.getByRole("row").filter({ hasText: IDs.plant })).toBeVisible({ timeout: 15_000 });
  await milestone("plant-created");

  await rowClick(page.getByRole("row").filter({ hasText: IDs.plant }));
  await expect(page.getByRole("dialog", { name: "Plant 360" })).toBeVisible();
  await operatorSelect(page.getByLabel("Next phase"), "vegetative");
  await operatorFill(page.getByLabel("Room"), "ZT-VEG-A");
  await operatorFill(page.getByLabel("Reason"), "Clone established and ready for vegetative growth.");
  await operatorClick(page.getByRole("button", { name: "Record change" }));
  await expect(page.getByLabel("Next phase")).toHaveValue("flowering", { timeout: 15_000 });
  await operatorFill(page.getByLabel("Room"), "ZT-FLOWER-A");
  await operatorFill(page.getByLabel("Reason"), "Vegetative target reached; move to flower.");
  await operatorClick(page.getByRole("button", { name: "Record change" }));
  await expect(page.getByRole("dialog", { name: "Plant 360" }).getByText(/Flowering/i).first()).toBeVisible({ timeout: 15_000 });
  await milestone("plant-flowering");
  await operatorClick(page.getByRole("dialog", { name: "Plant 360" }).getByRole("button", { name: "Close window" }));

  // 2. HARVEST — plan, weigh and create the physical harvest inventory lot.
  await operatorClick(page.getByRole("button", { name: "Plan harvest" }));
  await operatorFill(page.getByLabel("Harvest code"), IDs.harvest);
  await operatorFill(page.getByLabel("Notes"), "Zero-training Blue Dream harvest.");
  await rowClick(page.getByRole("dialog", { name: "Plan harvest" }).getByRole("row").filter({ hasText: IDs.plant }));
  await operatorClick(page.getByRole("button", { name: "Create harvest" }));
  const harvest360 = page.getByRole("dialog", { name: "Harvest 360" });
  await expect(harvest360).toBeVisible({ timeout: 15_000 });
  await operatorFill(harvest360.getByLabel("Wet weight (g)"), "5000");
  await operatorFill(harvest360.getByLabel("Execution notes"), "Harvest started at recorded wet weight.");
  await operatorClick(harvest360.getByRole("button", { name: "Start harvest" }));
  await expect(harvest360.getByRole("button", { name: "Move to drying" })).toBeVisible({ timeout: 15_000 });
  await operatorFill(harvest360.getByLabel("Dry weight (g)"), "1000");
  await operatorFill(harvest360.getByLabel("Waste weight (g)"), "50");
  await operatorFill(harvest360.getByLabel("Execution notes"), "Dry weight stabilized and recorded.");
  await operatorClick(harvest360.getByRole("button", { name: "Move to drying" }));
  await expect(harvest360.getByText("Allocate physical harvest output")).toBeVisible({ timeout: 15_000 });

  const harvestOutput = harvest360.locator("section.inventory-panel").filter({ hasText: "Allocate physical harvest output" });
  const harvestRow = harvestOutput.locator("tbody tr").first();
  await operatorSelect(harvestRow.locator("select").nth(0), /Blue Dream Harvest Material/);
  await operatorFill(harvestRow.getByPlaceholder("GP-0830-FLOWER"), IDs.harvestLot);
  await operatorSelect(harvestRow.locator("select").nth(1), "Finished flower");
  await operatorSelect(harvestRow.locator("select").nth(2), "Dry basis");
  await operatorFill(harvestRow.getByLabel("Harvest output quantity"), "1000");
  await operatorFill(harvestRow.getByPlaceholder("DRY-ROOM-1"), "ZT-DRY-A");
  await operatorSelect(harvestRow.locator("select").nth(3), "Available");
  await operatorClick(harvestOutput.getByRole("button", { name: "Preview allocation" }));
  await expect(harvestOutput.getByText("Exact harvest allocation preview")).toBeVisible({ timeout: 15_000 });
  await operatorClick(harvestOutput.getByRole("button", { name: "Post exact allocation" }));
  await expect(harvestOutput.getByText(/1 harvest output lot posted to Production Inventory/i)).toBeVisible({ timeout: 15_000 });
  await operatorClick(harvest360.getByRole("button", { name: "Complete harvest" }));
  await milestone("harvest-inventory-created");
  await collectWarnings(page);
  await operatorClick(harvest360.getByRole("button", { name: "Close window" }));

  // 3. EXTRACTION — reserve/consume the harvested lot and execute a real run.
  await switchWorkspace(page, "/production/extraction", sourceFacilityId, "Production Ops");
  await operatorClick(page.getByRole("button", { name: "New run" }));
  await operatorSelect(page.getByLabel("Process / target"), "Solventless · Hash Rosin");
  await operatorSelect(page.getByLabel("Source material"), new RegExp(IDs.harvestLot));
  await operatorFill(page.getByLabel("Amount to reserve"), "250");
  await operatorFill(page.getByLabel("Run ID"), IDs.run);
  await operatorClick(page.getByRole("button", { name: "Plan run & reserve" }));
  await expect(page.getByRole("heading", { name: IDs.run })).toBeVisible({ timeout: 15_000 });
  await milestone("production-run-planned");

  await operatorCheck(page.getByLabel(/Source package\/material verified/));
  await operatorCheck(page.getByLabel(/Required equipment\/work area ready/));
  await operatorCheck(page.getByLabel(/Required SOP\/batch documentation ready/));
  await operatorClick(page.getByRole("button", { name: "Start run & consume reserved material" }));
  await expect(page.getByText(/current stage:/i).first()).toBeVisible({ timeout: 15_000 });
  await milestone("source-consumed");

  await completeCurrentExtractionStep(page, { heading: "Intake / Staging" });
  await completeCurrentExtractionStep(page, { heading: "Preparation / Bagging", optional: true });
  await completeCurrentExtractionStep(page, { heading: "Press", input: "250", output: "160" });
  await completeCurrentExtractionStep(page, { heading: "Collection", input: "160", output: "150" });
  await completeCurrentExtractionStep(page, { heading: "Curing / Jar Tech", optional: true });
  await completeCurrentExtractionStep(page, { heading: "Formulation", optional: true });
  await completeCurrentExtractionStep(page, { heading: "Filling / Packaging" });
  await completeCurrentExtractionStep(page, { heading: "Final Output" });
  await expect(page.getByText("This run is at the QA / COA gate.")).toBeVisible({ timeout: 15_000 });
  await milestone("production-process-complete");

  // Deep Run 360 is intentionally contextual. This extra hop is counted as operator friction.
  await operatorClick(page.getByRole("button", { name: "Open Run 360" }));
  const advanced = page.getByRole("dialog", { name: "Advanced Extraction Run 360" });
  await expect(advanced).toBeVisible({ timeout: 15_000 });
  await operatorFill(advanced.getByLabel("Search runs"), IDs.run);
  await rowClick(advanced.getByRole("row").filter({ hasText: IDs.run }));
  const run360 = page.getByRole("dialog").filter({ hasText: IDs.run }).last();
  await expect(run360).toBeVisible({ timeout: 15_000 });
  await operatorClick(run360.getByRole("button", { name: "Outputs + QA" }));
  await operatorClick(run360.getByText("Create output / WIP package"));
  await operatorSelect(run360.getByLabel("Output product"), /Blue Dream Extract/);
  await operatorFill(run360.getByLabel("Internal lot / batch code"), IDs.extractLot);
  await operatorFill(run360.getByLabel("Output quantity"), "150");
  await operatorFill(run360.getByLabel("Output label"), "Blue Dream Extract");
  await operatorClick(run360.getByRole("button", { name: "Create quarantined output" }));
  await expect(run360.getByText("Quarantined output created.")).toBeVisible({ timeout: 15_000 });
  await milestone("extract-output-created");

  await operatorClick(run360.getByText("Record QA event"));
  await operatorSelect(run360.getByLabel("QA event"), "coa_attached");
  await operatorSelect(run360.getByLabel("Result"), "passed");
  await operatorFill(run360.getByLabel("COA / lab document reference"), "ZT-COA-BD-001");
  await operatorFill(run360.getByLabel("QA note"), "Acceptance COA passed and reviewed.");
  await operatorClick(run360.getByRole("button", { name: "Record QA" }));
  await expect(run360.getByText("QA event recorded.")).toBeVisible({ timeout: 15_000 });
  await expect(run360.getByRole("button", { name: "Release run + output inventory" })).toBeVisible({ timeout: 15_000 });
  await operatorClick(run360.getByRole("button", { name: "Release run + output inventory" }));
  await expect(run360.getByText("Run and output inventory released.")).toBeVisible({ timeout: 15_000 });
  await milestone("qa-released");
  await collectWarnings(page);

  // 4. PACKAGE STUDIO — convert released bulk extract into finished sellable units.
  await switchWorkspace(page, "/production/package-studio", sourceFacilityId, "Production Ops");
  await operatorSelect(page.getByLabel("Package action"), "Pack Down");
  await operatorSelect(page.getByLabel("Source package"), new RegExp(IDs.extractLot));
  const outputCard = page.locator(".package-output-card").first();
  await operatorSelect(outputCard.getByLabel("Output product"), /Blue Dream Vape 1g/);
  await operatorFill(outputCard.getByLabel("Lot / package code"), IDs.finishedLot);
  await operatorFill(outputCard.getByLabel("METRC package tag"), IDs.finishedTag);
  await operatorFill(outputCard.getByLabel("Finished quantity"), "100");
  await operatorFill(outputCard.getByLabel(/Source used/), "100");
  await operatorFill(page.getByLabel("Reason / work note"), "Pack released Blue Dream extract into 1g finished units.");
  await expect(page.getByText(/^Balanced ·/)).toBeVisible({ timeout: 15_000 });
  await operatorCheck(page.getByLabel("I reviewed the source, outputs, and mass balance."));
  const packageCommitResponse = page.waitForResponse(response => response.url().includes("/api/v1/package-studio/commit") && response.request().method() === "POST");
  await operatorClick(page.getByRole("button", { name: "Commit Pack Down" }));
  const packageCommit = await awaitJson(packageCommitResponse);
  const finishedLotId = String((packageCommit.output_lot_ids as unknown[] | undefined)?.[0] ?? "");
  expect(finishedLotId).not.toBe("");
  await expect(page.getByText(/committed with 1 output package/i)).toBeVisible({ timeout: 15_000 });
  await milestone("finished-package-created");

  // 5. WHOLESALE — create, confirm, allocate and post a customer shipment.
  await switchWorkspace(page, "/wholesale/orders", sourceFacilityId, "Production Ops");
  await operatorClick(page.getByRole("button", { name: "New Order" }));
  await operatorSelect(page.getByLabel("Order type"), "Sales");
  await operatorSelect(page.getByLabel("Customer"), /.*/);
  await operatorFill(page.getByLabel("Order number"), IDs.order);
  const orderLine = page.locator(".commercial-order-line").first().or(page.locator("table tbody tr").first());
  const productSelect = orderLine.locator("select").first();
  await operatorSelect(productSelect, /Blue Dream Vape 1g/);
  const numberInputs = orderLine.locator('input[type="number"]');
  await operatorFill(numberInputs.nth(0), "10");
  await operatorFill(numberInputs.nth(1), "18");
  const createOrderResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/commercial/orders") && response.request().method() === "POST");
  await operatorClick(page.getByRole("button", { name: "Create draft order" }));
  await awaitJson(createOrderResponse);
  await milestone("wholesale-order-created");

  await operatorClick(page.getByRole("button", { name: "Allocate & Fulfill" }));
  await operatorSelect(page.getByLabel("Open order"), new RegExp(IDs.order));
  await operatorClick(page.getByRole("button", { name: "Confirm order" }));
  await operatorSelect(page.getByLabel("Inventory lot"), new RegExp(IDs.finishedLot));
  await operatorFill(page.getByLabel("Quantity"), "10");
  await operatorFill(page.getByLabel("Fulfillment reference"), IDs.fulfillment);
  await operatorClick(page.getByRole("button", { name: "Reserve lot" }));
  await expect(page.getByText("Inventory reserved.")).toBeVisible({ timeout: 15_000 });
  await operatorClick(page.getByRole("button", { name: "Post shipment" }));
  await expect(page.getByText("Shipment posted to the immutable inventory ledger.")).toBeVisible({ timeout: 15_000 });
  await milestone("wholesale-fulfilled");

  // Commercial fulfillment and license transfer are currently separate workflows.
  // Record the duplicate operator context instead of hiding it from the usability score.
  friction.duplicateEntries += 1;
  friction.handoffGaps.push("Wholesale shipment does not automatically stage its physical package into the cross-license transfer workspace; the operator must select the package again and enter a separate manifest reference.");

  // 6. LICENSE TRANSFER — dispatch remaining finished units to a second license.
  await switchWorkspace(page, "/production/inventory/transfers", sourceFacilityId, "Production Ops");
  await operatorCheck(page.getByRole("checkbox", { name: `Select ${IDs.finishedTag}` }));
  await operatorSelect(page.getByLabel("Destination facility"), /Zero Training Destination Dispensary/);
  await operatorFill(page.getByLabel("Manifest / transfer #"), IDs.manifest);
  const outboundSection = page.locator("section.inventory-panel").filter({ hasText: "Dispatch packages to another license" });
  const transferQuantity = outboundSection.locator("tbody tr").filter({ hasText: "Blue Dream Vape 1g" }).locator('input[type="number"]');
  await operatorFill(transferQuantity, "10");
  await operatorCheck(page.getByLabel(/I confirm the required state-system\/Metrc transfer and manifest have already been created/));
  await operatorClick(page.getByRole("button", { name: "Post transfer out" }));
  await expect(page.getByText(new RegExp(`Transfer ${IDs.manifest} dispatched`))).toBeVisible({ timeout: 15_000 });
  await milestone("transfer-dispatched");
  await collectWarnings(page);

  // 7. DESTINATION RECEIPT — change license context and physically receive it.
  await switchWorkspace(page, "/inventory/transfers", destinationFacilityId, "Retail Ops");
  const inbound = page.locator("section.inventory-panel").filter({ hasText: "Transfers arriving at this license" });
  await expect(inbound.getByText(IDs.manifest)).toBeVisible({ timeout: 15_000 });
  await operatorClick(inbound.getByRole("button", { name: "Receive package" }));
  await operatorFill(page.getByLabel("Destination package ID"), IDs.destinationTag);
  await operatorFill(page.getByLabel("Destination lot / batch"), IDs.destinationLot);
  await operatorFill(page.getByLabel("Room / location"), "ZT-RECEIVING");
  await operatorCheck(page.getByLabel(/I confirm this package was accepted\/received in the required state system/));
  await operatorClick(page.getByRole("button", { name: "Post transfer in" }));
  await expect(page.getByText(new RegExp(`Transfer ${IDs.manifest} receipt posted`))).toBeVisible({ timeout: 15_000 });
  await milestone("destination-received");
  await collectWarnings(page);

  // 8. PACKAGE 360 + RECALL 360 — return to source and prove the full material trail.
  await switchWorkspace(page, "/production/inventory", sourceFacilityId, "Production Ops");
  await operatorFill(page.getByPlaceholder("Material, package, lot, room…"), "Blue Dream Vape 1g");
  await expect(page.getByRole("row").filter({ hasText: IDs.finishedTag })).toBeVisible({ timeout: 15_000 });
  await operatorCheck(page.getByRole("checkbox", { name: "Select Blue Dream Vape 1g" }));
  await operatorClick(page.getByRole("button", { name: "Package 360" }));
  const package360 = page.getByRole("dialog", { name: "Package 360" });
  await expect(package360).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText("SEED-TO-SALE GENEALOGY")).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText(new RegExp(`Plant source:.*${IDs.plant}`))).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText(new RegExp(`Harvest source:.*${IDs.harvest}`))).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText(new RegExp(`Cross-license trail:.*${IDs.manifest}`))).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText("RECALL 360 · BLAST RADIUS")).toBeVisible({ timeout: 15_000 });
  await expect(package360.getByText(IDs.destinationTag)).toBeVisible({ timeout: 15_000 });
  await milestone("recall-lineage-proved");

  // 9. DOOBIE AGENT — invoke deterministic lineage from the same operator context.
  await operatorClick(page.getByRole("button", { name: "Open Doobie Agent" }));
  const agent = page.getByRole("dialog", { name: "Doobie Agent" });
  await expect(agent).toBeVisible();
  const question = `Trace the lineage for package ${IDs.finishedTag}.`;
  await operatorFill(agent.locator("#workspace-agent-question"), question);
  const agentResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/ai-agents/run") && response.request().method() === "POST");
  await operatorClick(agent.getByRole("button", { name: "Run agent" }));
  const agentRun = await awaitJson(agentResponse);
  expect((agentRun.tool_calls as unknown[] | undefined) ?? []).toContain("package_lineage");
  await expect(agent.getByText(new RegExp(`Package lineage for ${IDs.finishedTag}`))).toBeVisible({ timeout: 15_000 });
  await milestone("agent-lineage-answer");

  await collectWarnings(page);
  await auditDeadEnd(page, "final-state");

  const scorePenalty =
    friction.decisions * 0.09 +
    friction.manualInputs * 0.07 +
    friction.duplicateEntries * 0.6 +
    friction.contextSwitches * 0.12 +
    friction.backtracks * 0.8 +
    friction.deadEnds.length * 2 +
    friction.api5xx.length * 2;
  const usabilityScore = Math.max(0, Math.round((10 - Math.min(10, scorePenalty)) * 10) / 10);
  const evidence = {
    ...friction,
    usabilityScore,
    durableIds: { ...IDs, finishedLotId },
    interpretation: {
      technicalPass: friction.deadEnds.length === 0 && friction.browserErrors.length === 0 && friction.api5xx.length === 0,
      usabilityTarget: 9.5,
      handoffGapCount: friction.handoffGaps.length,
    },
  };

  await testInfo.attach("zero-training-friction.json", {
    body: Buffer.from(JSON.stringify(evidence, null, 2)),
    contentType: "application/json",
  });

  expect(friction.deadEnds, `Dead ends: ${friction.deadEnds.join(" | ")}`).toEqual([]);
  expect(friction.browserErrors, `Browser errors: ${friction.browserErrors.join(" | ")}`).toEqual([]);
  expect(friction.api5xx, `API 5xx responses: ${friction.api5xx.join(" | ")}`).toEqual([]);
  expect(friction.milestones).toEqual([
    "plant-created",
    "plant-flowering",
    "harvest-inventory-created",
    "production-run-planned",
    "source-consumed",
    "production-process-complete",
    "extract-output-created",
    "qa-released",
    "finished-package-created",
    "wholesale-order-created",
    "wholesale-fulfilled",
    "transfer-dispatched",
    "destination-received",
    "recall-lineage-proved",
    "agent-lineage-answer",
  ]);
});
