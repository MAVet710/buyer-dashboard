import { expect, test, type Locator, type Page, type Response } from "@playwright/test";

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
  pageErrors: string[];
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

const freshFriction = (): Friction => ({
  clicks: 0,
  decisions: 0,
  manualInputs: 0,
  duplicateEntries: 0,
  contextSwitches: 0,
  backtracks: 0,
  warnings: [],
  handoffGaps: [],
  deadEnds: [],
  pageErrors: [],
  api4xx: [],
  api5xx: [],
  milestones: [],
});
const friction = freshFriction();

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
async function operatorSelect(locator: Locator, labelOrPattern: string | RegExp) {
  friction.clicks += 1;
  friction.decisions += 1;
  if (typeof labelOrPattern === "string") {
    await locator.selectOption({ label: labelOrPattern }).catch(async () => locator.selectOption(labelOrPattern));
    return;
  }
  const labels = await locator.locator("option").allTextContents();
  const match = labels.find(label => labelOrPattern.test(label));
  if (!match) throw new Error(`No option matched ${labelOrPattern}. Options: ${labels.join(" | ")}`);
  await locator.selectOption({ label: match });
}
async function operatorCheck(locator: Locator) {
  friction.clicks += 1;
  friction.decisions += 1;
  await locator.check();
}
async function operatorRow(locator: Locator) {
  friction.clicks += 1;
  await locator.click();
}
async function mark(label: string) {
  friction.milestones.push(label);
}

async function gotoWorkspace(page: Page, path: string) {
  friction.contextSwitches += 1;
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function bootstrapSourceContext(page: Page, organizationId: string, sourceFacilityId: string) {
  // Establish a real browser origin first. localStorage on about:blank is forbidden.
  await page.goto("/");
  await page.evaluate(({ organizationId, sourceFacilityId }) => {
    localStorage.setItem("buyer-dash-theme", "dark");
    localStorage.setItem("buyer-dash-organization", organizationId);
    localStorage.setItem("buyer-dash-facility", sourceFacilityId);
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  }, { organizationId, sourceFacilityId });
  await page.reload();
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function switchOperation(page: Page, operation: "Production Ops" | "Retail Ops") {
  friction.contextSwitches += 1;
  await operatorSelect(page.getByLabel("Operation"), operation);
  await expect(page.getByLabel("Operation")).toHaveValue(operation, { timeout: 15_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function switchFacility(page: Page, facilityName: string) {
  friction.contextSwitches += 1;
  const selector = page.getByLabel("Facility");
  await operatorSelect(selector, facilityName);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByLabel("Facility").locator("option:checked")).toHaveText(facilityName, { timeout: 15_000 });
}

function attachRuntimeFriction(page: Page) {
  page.on("pageerror", error => friction.pageErrors.push(error.message));
  page.on("response", response => {
    if (!response.url().includes("/api/")) return;
    const status = response.status();
    const entry = `${status} ${response.request().method()} ${response.url()}`;
    if (status >= 500) friction.api5xx.push(entry);
    else if (status >= 400) friction.api4xx.push(entry);
  });
}

async function collectWarnings(page: Page) {
  const values = await page.locator(".warning-banner:visible").allTextContents();
  for (const value of values.map(row => row.trim()).filter(Boolean)) {
    if (!friction.warnings.includes(value)) friction.warnings.push(value);
  }
}

async function auditDeadEnd(page: Page, stage: string) {
  const body = (await page.locator("body").innerText()).toLowerCase();
  const patterns = ["something went wrong", "unexpected error", "page not found", "cannot continue", "service unavailable"];
  const hit = patterns.find(pattern => body.includes(pattern));
  if (hit) friction.deadEnds.push(`${stage}: ${hit}`);
}

async function awaitJson(responsePromise: Promise<Response>) {
  const response = await responsePromise;
  expect(response.ok(), `${response.status()} ${response.request().method()} ${response.url()}`).toBeTruthy();
  return response.json() as Promise<Record<string, unknown>>;
}

async function completeStage(page: Page, options: { heading: string; input?: string; output?: string; optional?: boolean }) {
  await expect(page.getByRole("heading", { name: options.heading }).first()).toBeVisible({ timeout: 15_000 });
  if (options.optional) {
    await operatorClick(page.getByRole("button", { name: "Skip optional step" }));
  } else {
    if (options.input != null) await operatorFill(page.getByLabel("Stage input (g)"), options.input);
    if (options.output != null) await operatorFill(page.getByLabel("Scale output (g)"), options.output);
    await operatorClick(page.getByRole("button", { name: "Complete step & continue" }));
  }
  await page.waitForTimeout(150);
}

test("zero-training operator takes Blue Dream from plant to received wholesale package and proves lineage", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  const organizationId = requiredEnv("ALPHA_ORGANIZATION_ID");
  const sourceFacilityId = requiredEnv("ALPHA_FACILITY_ID");
  requiredEnv("ALPHA_DESTINATION_FACILITY_ID");
  Object.assign(friction, freshFriction());
  attachRuntimeFriction(page);

  await bootstrapSourceContext(page, organizationId, sourceFacilityId);

  // 1. CULTIVATION — create Blue Dream and advance it to flower.
  await gotoWorkspace(page, "/production/inventory");
  await expect(page.getByRole("heading", { name: "Production Inventory" })).toBeVisible();
  await operatorClick(page.getByRole("button", { name: "Plants" }));
  await operatorClick(page.getByRole("button", { name: "Add one plant" }));
  await operatorFill(page.getByLabel("Plant tag"), IDs.plant);
  await operatorFill(page.getByLabel("Strain"), "Blue Dream");
  await operatorSelect(page.getByLabel("Phase"), "Clone");
  await operatorFill(page.getByLabel("Room"), "ZT-VEG-A");
  await operatorFill(page.getByLabel("Estimated harvest"), "2026-10-15");
  await operatorFill(page.getByLabel("Notes"), "Zero-training operator acceptance plant.");
  await operatorClick(page.getByRole("button", { name: "Save plant" }));
  await expect(page.getByRole("row").filter({ hasText: IDs.plant })).toBeVisible({ timeout: 15_000 });
  await mark("plant-created");

  await operatorRow(page.getByRole("row").filter({ hasText: IDs.plant }));
  const plant360 = page.getByRole("dialog", { name: "Plant 360" });
  await expect(plant360).toBeVisible();
  await operatorSelect(plant360.getByLabel("Next phase"), "Vegetative");
  await operatorFill(plant360.getByLabel("Room"), "ZT-VEG-A");
  await operatorFill(plant360.getByLabel("Reason"), "Clone established and ready for vegetative growth.");
  await operatorClick(plant360.getByRole("button", { name: "Record change" }));
  await expect(plant360.getByLabel("Next phase")).toHaveValue("flowering", { timeout: 15_000 });
  await operatorFill(plant360.getByLabel("Room"), "ZT-FLOWER-A");
  await operatorFill(plant360.getByLabel("Reason"), "Vegetative target reached; move to flower.");
  await operatorClick(plant360.getByRole("button", { name: "Record change" }));
  await expect(plant360.getByText(/Flowering/i).first()).toBeVisible({ timeout: 15_000 });
  await mark("plant-flowering");
  await operatorClick(plant360.getByRole("button", { name: "Close window" }));

  // 2. HARVEST — create durable harvest and physical inventory.
  await operatorClick(page.getByRole("button", { name: "Plan harvest" }));
  const harvestBuilder = page.getByRole("dialog").filter({ hasText: "Plan harvest" });
  await operatorFill(harvestBuilder.getByLabel("Harvest code"), IDs.harvest);
  await operatorFill(harvestBuilder.getByLabel("Notes"), "Zero-training Blue Dream harvest.");
  await operatorRow(harvestBuilder.getByRole("row").filter({ hasText: IDs.plant }));
  await operatorClick(harvestBuilder.getByRole("button", { name: "Create harvest" }));

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

  const allocation = harvest360.locator("section.inventory-panel").filter({ hasText: "Allocate physical harvest output" });
  await expect(allocation).toBeVisible({ timeout: 15_000 });
  const harvestRow = allocation.locator("tbody tr").first();
  await operatorSelect(harvestRow.locator("select").nth(0), /Blue Dream Harvest Material/);
  await operatorFill(harvestRow.getByPlaceholder("GP-0830-FLOWER"), IDs.harvestLot);
  await operatorSelect(harvestRow.locator("select").nth(1), "Biomass");
  await operatorSelect(harvestRow.locator("select").nth(2), "Dry basis");
  await operatorFill(harvestRow.getByLabel("Harvest output quantity"), "1000");
  await operatorFill(harvestRow.getByPlaceholder("DRY-ROOM-1"), "ZT-DRY-A");
  await operatorSelect(harvestRow.locator("select").nth(3), "Available");
  await operatorClick(allocation.getByRole("button", { name: "Preview allocation" }));
  await expect(allocation.getByText("Exact harvest allocation preview")).toBeVisible({ timeout: 15_000 });
  await operatorClick(allocation.getByRole("button", { name: "Post exact allocation" }));
  await expect(allocation.getByText(/1 harvest output lot posted to Production Inventory/i)).toBeVisible({ timeout: 15_000 });
  await operatorClick(harvest360.getByRole("button", { name: "Complete harvest" }));
  await mark("harvest-inventory-created");
  await collectWarnings(page);
  await operatorClick(harvest360.getByRole("button", { name: "Close window" }));

  // 3. EXTRACTION — reserve, consume and work the real Hash Rosin workflow.
  await gotoWorkspace(page, "/production/extraction");
  await operatorClick(page.getByRole("button", { name: "New run" }));
  await operatorSelect(page.getByLabel("Process / target"), "Solventless · Hash Rosin");
  await operatorSelect(page.getByLabel("Source material"), new RegExp(IDs.harvestLot));
  await operatorFill(page.getByLabel("Amount to reserve"), "250");
  await operatorFill(page.getByLabel("Run ID"), IDs.run);
  await operatorClick(page.getByRole("button", { name: "Plan run & reserve" }));
  await expect(page.getByRole("heading", { name: IDs.run })).toBeVisible({ timeout: 15_000 });
  await mark("production-run-planned");

  await operatorCheck(page.getByLabel(/Source package\/material verified/));
  await operatorCheck(page.getByLabel(/Required equipment\/work area ready/));
  await operatorCheck(page.getByLabel(/Required SOP\/batch documentation ready/));
  await operatorClick(page.getByRole("button", { name: "Start run & consume reserved material" }));
  await expect(page.getByText(/current stage:/i).first()).toBeVisible({ timeout: 15_000 });
  await mark("source-consumed");

  await completeStage(page, { heading: "Intake / Staging" });
  await completeStage(page, { heading: "Preparation / Bagging", optional: true });
  await completeStage(page, { heading: "Press", input: "250", output: "160" });
  await completeStage(page, { heading: "Collection", input: "160", output: "150" });
  await completeStage(page, { heading: "Curing / Jar Tech", optional: true });
  await completeStage(page, { heading: "Formulation", optional: true });
  await completeStage(page, { heading: "Filling / Packaging" });
  await completeStage(page, { heading: "Final Output" });
  await expect(page.getByText("This run is at the QA / COA gate.")).toBeVisible({ timeout: 15_000 });
  await mark("production-process-complete");

  await operatorClick(page.getByRole("button", { name: "Open Run 360" }));
  const advanced = page.getByRole("dialog", { name: "Advanced Extraction Run 360" });
  await expect(advanced).toBeVisible({ timeout: 15_000 });
  await operatorFill(advanced.getByLabel("Search runs"), IDs.run);
  await operatorRow(advanced.getByRole("row").filter({ hasText: IDs.run }));
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
  await mark("extract-output-created");

  await operatorClick(run360.getByText("Record QA event"));
  await operatorSelect(run360.getByLabel("QA event"), "coa_attached");
  await operatorSelect(run360.getByLabel("Result"), "passed");
  await operatorFill(run360.getByLabel("COA / lab document reference"), "ZT-COA-BD-001");
  await operatorFill(run360.getByLabel("QA note"), "Acceptance COA passed and reviewed.");
  await operatorClick(run360.getByRole("button", { name: "Record QA" }));
  await expect(run360.getByText("QA event recorded.")).toBeVisible({ timeout: 15_000 });
  await operatorClick(run360.getByRole("button", { name: "Release run + output inventory" }));
  await expect(run360.getByText("Run and output inventory released.")).toBeVisible({ timeout: 15_000 });
  await mark("qa-released");
  await collectWarnings(page);

  // 4. PACKAGE STUDIO — package released extract into finished units.
  await gotoWorkspace(page, "/production/package-studio");
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
  const commitResponse = page.waitForResponse(response => response.url().includes("/api/v1/package-studio/commit") && response.request().method() === "POST");
  await operatorClick(page.getByRole("button", { name: "Commit Pack Down" }));
  const commit = await awaitJson(commitResponse);
  const finishedLotId = String((commit.output_lot_ids as unknown[] | undefined)?.[0] ?? "");
  expect(finishedLotId).not.toBe("");
  await mark("finished-package-created");

  // 5. WHOLESALE — draft, confirm, allocate and fulfill.
  await gotoWorkspace(page, "/wholesale/orders");
  await operatorClick(page.getByRole("button", { name: "New Order" }));
  await operatorSelect(page.getByLabel("Order type"), "Sales");
  await operatorSelect(page.getByLabel("Customer"), /.*/);
  await operatorFill(page.getByLabel("Order number"), IDs.order);
  const orderLine = page.locator("tbody tr").filter({ has: page.locator("select") }).first();
  await operatorSelect(orderLine.locator("select").first(), /Blue Dream Vape 1g/);
  const orderNumbers = orderLine.locator('input[type="number"]');
  await operatorFill(orderNumbers.nth(0), "10");
  await operatorFill(orderNumbers.nth(1), "18");
  const orderResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/commercial/orders") && response.request().method() === "POST");
  await operatorClick(page.getByRole("button", { name: "Create draft order" }));
  await awaitJson(orderResponse);
  await mark("wholesale-order-created");

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
  await mark("wholesale-fulfilled");

  friction.duplicateEntries += 1;
  friction.handoffGaps.push("Wholesale fulfillment does not automatically stage the physical package into cross-license transfer; the operator selects the package again and enters a separate manifest reference.");

  // 6. CROSS-LICENSE TRANSFER — dispatch package from source license.
  await gotoWorkspace(page, "/production/inventory/transfers");
  await operatorCheck(page.getByRole("checkbox", { name: `Select ${IDs.finishedTag}` }));
  await operatorSelect(page.getByLabel("Destination facility"), "Zero Training Destination Dispensary");
  await operatorFill(page.getByLabel("Manifest / transfer #"), IDs.manifest);
  const dispatch = page.locator("section.inventory-panel").filter({ hasText: "Dispatch packages to another license" });
  await operatorFill(dispatch.locator("tbody tr").filter({ hasText: "Blue Dream Vape 1g" }).locator('input[type="number"]'), "10");
  await operatorCheck(page.getByLabel(/I confirm the required state-system\/Metrc transfer and manifest have already been created/));
  await operatorClick(page.getByRole("button", { name: "Post transfer out" }));
  await expect(page.getByText(new RegExp(`Transfer ${IDs.manifest} dispatched`))).toBeVisible({ timeout: 15_000 });
  await mark("transfer-dispatched");
  await collectWarnings(page);

  // 7. DESTINATION — use the actual top-bar context selectors, then receive.
  await switchOperation(page, "Retail Ops");
  await switchFacility(page, "Zero Training Destination Dispensary");
  await gotoWorkspace(page, "/inventory/transfers");
  const inbound = page.locator("section.inventory-panel").filter({ hasText: "Transfers arriving at this license" });
  await expect(inbound.getByText(IDs.manifest)).toBeVisible({ timeout: 15_000 });
  await operatorClick(inbound.getByRole("button", { name: "Receive package" }));
  await operatorFill(page.getByLabel("Destination package ID"), IDs.destinationTag);
  await operatorFill(page.getByLabel("Destination lot / batch"), IDs.destinationLot);
  await operatorFill(page.getByLabel("Room / location"), "ZT-RECEIVING");
  await operatorCheck(page.getByLabel(/I confirm this package was accepted\/received in the required state system/));
  await operatorClick(page.getByRole("button", { name: "Post transfer in" }));
  await expect(page.getByText(new RegExp(`Transfer ${IDs.manifest} receipt posted`))).toBeVisible({ timeout: 15_000 });
  await mark("destination-received");
  await collectWarnings(page);

  // 8. RETURN TO SOURCE — Package 360 + Recall 360 must prove genealogy.
  await switchFacility(page, "Zero Training Vertical Facility");
  await switchOperation(page, "Production Ops");
  await gotoWorkspace(page, "/production/inventory");
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
  await mark("recall-lineage-proved");

  // 9. DOOBIE AGENT — deterministic lineage must agree with Recall 360.
  await operatorClick(page.getByRole("button", { name: "Open Doobie Agent" }));
  const agent = page.getByRole("dialog", { name: "Doobie Agent" });
  await operatorFill(agent.locator("#workspace-agent-question"), `Trace the lineage for package ${IDs.finishedTag}.`);
  const agentResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/ai-agents/run") && response.request().method() === "POST");
  await operatorClick(agent.getByRole("button", { name: "Run agent" }));
  const agentRun = await awaitJson(agentResponse);
  expect((agentRun.tool_calls as unknown[] | undefined) ?? []).toContain("package_lineage");
  await expect(agent.getByText(new RegExp(`Package lineage for ${IDs.finishedTag}`))).toBeVisible({ timeout: 15_000 });
  await mark("agent-lineage-answer");

  await collectWarnings(page);
  await auditDeadEnd(page, "final");

  const penalty =
    friction.decisions * 0.09 +
    friction.manualInputs * 0.07 +
    friction.duplicateEntries * 0.6 +
    friction.contextSwitches * 0.12 +
    friction.backtracks * 0.8 +
    friction.deadEnds.length * 2 +
    friction.api5xx.length * 2;
  const usabilityScore = Math.max(0, Math.round((10 - Math.min(10, penalty)) * 10) / 10);
  const evidence = {
    ...friction,
    usabilityScore,
    durableIds: { ...IDs, finishedLotId },
    targetScore: 9.5,
  };

  await testInfo.attach("zero-training-friction.json", {
    body: Buffer.from(JSON.stringify(evidence, null, 2)),
    contentType: "application/json",
  });

  expect(friction.deadEnds, `Dead ends: ${friction.deadEnds.join(" | ")}`).toEqual([]);
  expect(friction.pageErrors, `Page errors: ${friction.pageErrors.join(" | ")}`).toEqual([]);
  expect(friction.api5xx, `API 5xx: ${friction.api5xx.join(" | ")}`).toEqual([]);
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
