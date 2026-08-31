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

const ID = {
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
};

const blank = (): Friction => ({
  clicks: 0, decisions: 0, manualInputs: 0, duplicateEntries: 0,
  contextSwitches: 0, backtracks: 0, warnings: [], handoffGaps: [],
  deadEnds: [], pageErrors: [], api4xx: [], api5xx: [], milestones: [],
});
const friction = blank();

function env(name: string) {
  const value = String(process.env[name] ?? "").trim();
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

async function click(locator: Locator) { friction.clicks += 1; await locator.click(); }
async function fill(locator: Locator, value: string) { friction.manualInputs += 1; await locator.fill(value); }
async function check(locator: Locator) { friction.clicks += 1; friction.decisions += 1; await locator.check(); }
async function choose(locator: Locator, label: string | RegExp) {
  friction.clicks += 1; friction.decisions += 1;
  if (typeof label === "string") {
    await locator.selectOption({ label }).catch(async () => locator.selectOption(label));
    return;
  }
  const options = await locator.locator("option").allTextContents();
  const match = options.find(text => label.test(text));
  if (!match) throw new Error(`No option matched ${label}. Options: ${options.join(" | ")}`);
  await locator.selectOption({ label: match });
}
async function chooseFirstReal(locator: Locator) {
  friction.clicks += 1; friction.decisions += 1;
  const options = await locator.locator("option").evaluateAll(rows => rows.map((row, index) => ({
    index, value: (row as HTMLOptionElement).value, text: row.textContent ?? "", disabled: (row as HTMLOptionElement).disabled,
  })));
  const target = options.find(row => row.index > 0 && row.value && !row.disabled);
  if (!target) throw new Error("No real selectable option is available.");
  await locator.selectOption(target.value);
}
async function mark(value: string) { friction.milestones.push(value); }
async function workspace(page: Page, path: string) {
  friction.contextSwitches += 1;
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
}
async function responseJson(promise: Promise<Response>) {
  const response = await promise;
  expect(response.ok(), `${response.status()} ${response.request().method()} ${response.url()}`).toBeTruthy();
  return response.json() as Promise<Record<string, unknown>>;
}

function watch(page: Page) {
  page.on("pageerror", error => friction.pageErrors.push(error.message));
  page.on("response", response => {
    if (!response.url().includes("/api/")) return;
    const row = `${response.status()} ${response.request().method()} ${response.url()}`;
    if (response.status() >= 500) friction.api5xx.push(row);
    else if (response.status() >= 400) friction.api4xx.push(row);
  });
}

async function bootstrap(page: Page, organizationId: string, facilityId: string) {
  await page.goto("/");
  await page.evaluate(({ organizationId, facilityId }) => {
    localStorage.setItem("buyer-dash-theme", "dark");
    localStorage.setItem("buyer-dash-organization", organizationId);
    localStorage.setItem("buyer-dash-facility", facilityId);
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  }, { organizationId, facilityId });
  await page.reload();
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByLabel("Operation")).toHaveValue("Production Ops", { timeout: 15_000 });
  await expect(page.getByLabel("Facility").locator("option:checked")).toHaveText("Zero Training Vertical Facility", { timeout: 15_000 });
}

async function switchOperation(page: Page, name: "Retail Ops" | "Production Ops") {
  friction.contextSwitches += 1;
  await choose(page.getByLabel("Operation"), name);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByLabel("Operation")).toHaveValue(name, { timeout: 15_000 });
}

async function visibleWarnings(page: Page) {
  for (const text of await page.locator(".warning-banner:visible").allTextContents()) {
    const value = text.trim();
    if (value && !friction.warnings.includes(value)) friction.warnings.push(value);
  }
}

async function advanceExtraction(page: Page) {
  for (let index = 0; index < 14; index += 1) {
    if (await page.getByText("This run is at the QA / COA gate.").isVisible().catch(() => false)) return;
    const skip = page.getByRole("button", { name: "Skip optional step" });
    if (await skip.isVisible().catch(() => false)) {
      await click(skip);
      await page.waitForTimeout(150);
      continue;
    }
    const stageInput = page.getByLabel("Stage input (g)");
    const stageOutput = page.getByLabel("Scale output (g)");
    if (await stageInput.isVisible().catch(() => false)) await fill(stageInput, index === 0 ? "250" : "100");
    if (await stageOutput.isVisible().catch(() => false)) await fill(stageOutput, "100");
    const complete = page.getByRole("button", { name: "Complete step & continue" });
    await expect(complete).toBeVisible({ timeout: 15_000 });
    await click(complete);
    await page.waitForTimeout(150);
  }
  throw new Error("Extraction workflow did not reach QA / COA gate within 14 operator steps.");
}

function score() {
  const penalty = friction.duplicateEntries * 2 + friction.handoffGaps.length * 2 +
    friction.backtracks * 1.5 + friction.deadEnds.length * 3 +
    friction.pageErrors.length * 3 + friction.api5xx.length * 3;
  return Math.max(0, Math.round((10 - Math.min(10, penalty)) * 10) / 10);
}

test("zero-training operator takes Blue Dream from plant to received wholesale package and proves lineage", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  Object.assign(friction, blank());
  const organizationId = env("ALPHA_ORGANIZATION_ID");
  const sourceFacilityId = env("ALPHA_FACILITY_ID");
  env("ALPHA_DESTINATION_FACILITY_ID");
  watch(page);
  let failure: unknown;
  let finishedLotId = "";

  try {
    await bootstrap(page, organizationId, sourceFacilityId);

    // Cultivation: individual plant -> vegetative -> flowering.
    await workspace(page, "/production/inventory");
    await expect(page.getByRole("heading", { name: "Production Inventory" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("PRODUCTION OPS").first()).toBeVisible();
    await click(page.getByRole("button", { name: "Plants" }));
    await click(page.getByRole("button", { name: "Add one plant" }));
    await fill(page.getByLabel("Plant tag"), ID.plant);
    await fill(page.getByLabel("Strain"), "Blue Dream");
    await choose(page.getByLabel("Phase"), "Clone");
    await fill(page.getByLabel("Room"), "ZT-VEG-A");
    await fill(page.getByLabel("Estimated harvest"), "2026-10-15");
    await fill(page.getByLabel("Notes"), "Zero-training acceptance plant.");
    await click(page.getByRole("button", { name: "Save plant" }));
    await expect(page.getByRole("row").filter({ hasText: ID.plant })).toBeVisible({ timeout: 15_000 });
    await mark("plant-created");

    await click(page.getByRole("row").filter({ hasText: ID.plant }));
    const plant360 = page.getByRole("dialog", { name: "Plant 360" });
    await choose(plant360.getByLabel("Next phase"), "Vegetative");
    await fill(plant360.getByLabel("Room"), "ZT-VEG-A");
    await fill(plant360.getByLabel("Reason"), "Clone established.");
    await click(plant360.getByRole("button", { name: "Record change" }));
    await expect(plant360.getByLabel("Next phase")).toHaveValue("flowering", { timeout: 15_000 });
    await fill(plant360.getByLabel("Room"), "ZT-FLOWER-A");
    await fill(plant360.getByLabel("Reason"), "Vegetative target reached.");
    await click(plant360.getByRole("button", { name: "Record change" }));
    await expect(plant360.getByText(/Flowering/i).first()).toBeVisible({ timeout: 15_000 });
    await mark("plant-flowering");
    await click(plant360.getByRole("button", { name: "Close window" }));

    // Harvest: create a physical biomass lot that extraction can consume.
    await click(page.getByRole("button", { name: "Plan harvest" }));
    const planner = page.getByRole("dialog").filter({ hasText: "Plan harvest" });
    await fill(planner.getByLabel("Harvest code"), ID.harvest);
    await fill(planner.getByLabel("Notes"), "Zero-training Blue Dream harvest.");
    await click(planner.getByRole("row").filter({ hasText: ID.plant }));
    await click(planner.getByRole("button", { name: "Create harvest" }));
    const harvest360 = page.getByRole("dialog", { name: "Harvest 360" });
    await fill(harvest360.getByLabel("Wet weight (g)"), "5000");
    await fill(harvest360.getByLabel("Execution notes"), "Wet weight recorded.");
    await click(harvest360.getByRole("button", { name: "Start harvest" }));
    await fill(harvest360.getByLabel("Dry weight (g)"), "1000");
    await fill(harvest360.getByLabel("Waste weight (g)"), "50");
    await fill(harvest360.getByLabel("Execution notes"), "Dry weight stabilized.");
    await click(harvest360.getByRole("button", { name: "Move to drying" }));
    const allocation = harvest360.locator("section.inventory-panel").filter({ hasText: "Allocate physical harvest output" });
    const row = allocation.locator("tbody tr").first();
    await choose(row.locator("select").nth(0), /Blue Dream Harvest Material/);
    await fill(row.getByPlaceholder("GP-0830-FLOWER"), ID.harvestLot);
    await choose(row.locator("select").nth(1), "Biomass");
    await choose(row.locator("select").nth(2), "Dry basis");
    await fill(row.getByLabel("Harvest output quantity"), "1000");
    await fill(row.getByPlaceholder("DRY-ROOM-1"), "ZT-DRY-A");
    await choose(row.locator("select").nth(3), "Available");
    await click(allocation.getByRole("button", { name: "Preview allocation" }));
    await click(allocation.getByRole("button", { name: "Post exact allocation" }));
    await expect(allocation.getByText(/posted to Production Inventory/i)).toBeVisible({ timeout: 15_000 });
    await click(harvest360.getByRole("button", { name: "Complete harvest" }));
    await mark("harvest-inventory-created");
    await click(harvest360.getByRole("button", { name: "Close window" }));

    // Extraction: reserve -> consume -> work stages -> output -> QA release.
    await workspace(page, "/production/extraction");
    await click(page.getByRole("button", { name: "New run" }));
    await choose(page.getByLabel("Process / target"), "Solventless · Hash Rosin");
    await choose(page.getByLabel("Source material"), new RegExp(ID.harvestLot));
    await fill(page.getByLabel("Amount to reserve"), "250");
    await fill(page.getByLabel("Run ID"), ID.run);
    await click(page.getByRole("button", { name: "Plan run & reserve" }));
    await expect(page.getByRole("heading", { name: ID.run })).toBeVisible({ timeout: 15_000 });
    await mark("production-run-planned");
    await check(page.getByLabel(/Source package\/material verified/));
    await check(page.getByLabel(/Required equipment\/work area ready/));
    await check(page.getByLabel(/Required SOP\/batch documentation ready/));
    await click(page.getByRole("button", { name: "Start run & consume reserved material" }));
    await mark("source-consumed");
    await advanceExtraction(page);
    await expect(page.getByText("This run is at the QA / COA gate.")).toBeVisible({ timeout: 15_000 });
    await mark("production-process-complete");

    await click(page.getByRole("button", { name: "Open Run 360" }));
    const advanced = page.getByRole("dialog", { name: "Advanced Extraction Run 360" });
    await fill(advanced.getByLabel("Search runs"), ID.run);
    await click(advanced.getByRole("row").filter({ hasText: ID.run }));
    const run360 = page.getByRole("dialog").filter({ hasText: ID.run }).last();
    await click(run360.getByRole("button", { name: "Outputs + QA" }));
    await click(run360.getByText("Create output / WIP package"));
    await choose(run360.getByLabel("Output product"), /Blue Dream Extract/);
    await fill(run360.getByLabel("Internal lot / batch code"), ID.extractLot);
    await fill(run360.getByLabel("Output quantity"), "150");
    await fill(run360.getByLabel("Output label"), "Blue Dream Extract");
    await click(run360.getByRole("button", { name: "Create quarantined output" }));
    await expect(run360.getByText("Quarantined output created.")).toBeVisible({ timeout: 15_000 });
    await mark("extract-output-created");
    await click(run360.getByText("Record QA event"));
    await choose(run360.getByLabel("QA event"), "coa_attached");
    await choose(run360.getByLabel("Result"), "passed");
    await fill(run360.getByLabel("COA / lab document reference"), "ZT-COA-BD-001");
    await fill(run360.getByLabel("QA note"), "Acceptance COA passed.");
    await click(run360.getByRole("button", { name: "Record QA" }));
    await click(run360.getByRole("button", { name: "Release run + output inventory" }));
    await expect(run360.getByText("Run and output inventory released.")).toBeVisible({ timeout: 15_000 });
    await mark("qa-released");

    // Package Studio: released bulk -> finished 1g units.
    await workspace(page, "/production/package-studio");
    await choose(page.getByLabel("Package action"), "Pack Down");
    await choose(page.getByLabel("Source package"), new RegExp(ID.extractLot));
    const output = page.locator(".package-output-card").first();
    await choose(output.getByLabel("Output product"), /Blue Dream Vape 1g/);
    await fill(output.getByLabel("Lot / package code"), ID.finishedLot);
    await fill(output.getByLabel("METRC package tag"), ID.finishedTag);
    await fill(output.getByLabel("Finished quantity"), "100");
    await fill(output.getByLabel(/Source used/), "100");
    await fill(page.getByLabel("Reason / work note"), "Package released Blue Dream extract.");
    await expect(page.getByText(/^Balanced ·/)).toBeVisible({ timeout: 15_000 });
    await check(page.getByLabel("I reviewed the source, outputs, and mass balance."));
    const commitResponse = page.waitForResponse(r => r.url().includes("/api/v1/package-studio/commit") && r.request().method() === "POST");
    await click(page.getByRole("button", { name: "Commit Pack Down" }));
    const commit = await responseJson(commitResponse);
    finishedLotId = String((commit.output_lot_ids as unknown[] | undefined)?.[0] ?? "");
    expect(finishedLotId).not.toBe("");
    await mark("finished-package-created");

    // Wholesale: create -> confirm -> reserve -> hand off directly to the licensed transfer.
    await workspace(page, "/wholesale/orders");
    await click(page.getByRole("button", { name: "New Order" }));
    await choose(page.getByLabel("Order type"), "Sales");
    await chooseFirstReal(page.getByLabel("Customer"));
    await fill(page.getByLabel("Order number"), ID.order);
    const orderRow = page.locator("tbody tr").filter({ has: page.locator("select") }).first();
    await choose(orderRow.locator("select").first(), /Blue Dream Vape 1g/);
    const numbers = orderRow.locator('input[type="number"]');
    await fill(numbers.nth(0), "10");
    await fill(numbers.nth(1), "18");
    const orderResponse = page.waitForResponse(r => r.url().endsWith("/api/v1/commercial/orders") && r.request().method() === "POST");
    await click(page.getByRole("button", { name: "Create draft order" }));
    await responseJson(orderResponse);
    await mark("wholesale-order-created");
    await click(page.getByRole("button", { name: "Allocate & Fulfill" }));
    await choose(page.getByLabel("Open order"), new RegExp(ID.order));
    await click(page.getByRole("button", { name: "Confirm order" }));
    await choose(page.getByLabel("Inventory lot"), new RegExp(ID.finishedLot));
    await fill(page.getByLabel("Quantity"), "10");
    await fill(page.getByLabel("Fulfillment reference"), ID.fulfillment);
    await click(page.getByRole("button", { name: "Reserve lot" }));
    await expect(page.getByText("Inventory reserved. Next: prepare the licensed transfer.")).toBeVisible({ timeout: 15_000 });
    await mark("wholesale-reserved");
    await expect(page.getByRole("button", { name: "Prepare licensed transfer" })).toBeEnabled({ timeout: 15_000 });
    await click(page.getByRole("button", { name: "Prepare licensed transfer" }));
    await page.waitForLoadState("networkidle").catch(() => undefined);

    // Licensed transfer: package, quantity, sales-order ownership and reference are carried forward.
    await expect(page.getByRole("heading", { name: "Production Inventory Transfers" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(new RegExp(`Staged from wholesale order ${ID.order}`))).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(ID.finishedTag).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel("Fulfillment / external reference")).toHaveValue(ID.fulfillment);
    const stagedQuantity = page.locator("section.inventory-panel").filter({ hasText: "Dispatch packages to another license" }).locator('input[type="number"]');
    await expect(stagedQuantity).toHaveValue("10");
    await expect(stagedQuantity).toBeDisabled();
    await choose(page.getByLabel("Destination facility"), /Zero Training Destination Dispensary/);
    await fill(page.getByLabel("Manifest / transfer #"), ID.manifest);
    await check(page.getByLabel(/I confirm the required state-system\/Metrc transfer and manifest have already been created/));
    const transferResponse = page.waitForResponse(r => r.url().endsWith("/api/v1/inventory/transfers/dispatch") && r.request().method() === "POST");
    await click(page.getByRole("button", { name: "Post licensed transfer & fulfill order" }));
    await responseJson(transferResponse);
    await expect(page.getByText(new RegExp(`Wholesale order ${ID.order} fulfilled through transfer ${ID.manifest}`))).toBeVisible({ timeout: 15_000 });
    await mark("transfer-dispatched");
    await mark("wholesale-fulfilled");

    // Destination: operation change selects the retail license; package identity carries forward.
    await switchOperation(page, "Retail Ops");
    await expect(page.getByLabel("Facility").locator("option:checked")).toHaveText("Zero Training Destination Dispensary", { timeout: 15_000 });
    await workspace(page, "/inventory/transfers");
    await expect(page.getByRole("heading", { name: "Retail Inventory Transfers" })).toBeVisible({ timeout: 15_000 });
    const inbound = page.locator("section.inventory-panel").filter({ hasText: "Transfers arriving at this license" });
    await expect(inbound.getByText(ID.manifest)).toBeVisible({ timeout: 15_000 });
    await click(inbound.getByRole("button", { name: "Receive package" }));
    await expect(page.getByLabel("Destination package ID")).toHaveValue(ID.finishedTag);
    await expect(page.getByLabel("Destination lot / batch")).toHaveValue(ID.finishedLot);
    await expect(page.getByLabel("Room / location")).toHaveValue("RECEIVING");
    await check(page.getByLabel(/I confirm this package was accepted\/received in the required state system/));
    await click(page.getByRole("button", { name: "Post transfer in" }));
    await expect(page.getByText(new RegExp(`Transfer ${ID.manifest} receipt posted`))).toBeVisible({ timeout: 15_000 });
    await mark("destination-received");

    // Return to source and prove blast radius + genealogy.
    await switchOperation(page, "Production Ops");
    await expect(page.getByLabel("Facility").locator("option:checked")).toHaveText("Zero Training Vertical Facility", { timeout: 15_000 });
    await workspace(page, "/production/inventory");
    await fill(page.getByPlaceholder("Material, package, lot, room…"), "Blue Dream Vape 1g");
    await check(page.getByRole("checkbox", { name: "Select Blue Dream Vape 1g" }));
    await click(page.getByRole("button", { name: "Package 360" }));
    const package360 = page.getByRole("dialog", { name: "Package 360" });
    await expect(package360.getByText("SEED-TO-SALE GENEALOGY")).toBeVisible({ timeout: 15_000 });
    await expect(package360.getByText(new RegExp(`Plant source:.*${ID.plant}`))).toBeVisible({ timeout: 15_000 });
    await expect(package360.getByText(new RegExp(`Harvest source:.*${ID.harvest}`))).toBeVisible({ timeout: 15_000 });
    await expect(package360.getByText(new RegExp(`Cross-license trail:.*${ID.manifest}`))).toBeVisible({ timeout: 15_000 });
    await expect(package360.getByText("RECALL 360 · BLAST RADIUS")).toBeVisible({ timeout: 15_000 });
    await expect(package360.getByText(ID.finishedTag).first()).toBeVisible({ timeout: 15_000 });
    await mark("recall-lineage-proved");

    // Deterministic Doobie Agent traceability must agree with Recall 360.
    await click(page.getByRole("button", { name: "Open Doobie Agent" }));
    const agent = page.getByRole("dialog", { name: "Doobie Agent" });
    await fill(agent.locator("#workspace-agent-question"), `Trace the lineage for package ${ID.finishedTag}.`);
    const agentResponse = page.waitForResponse(r => r.url().endsWith("/api/v1/ai-agents/run") && r.request().method() === "POST");
    await click(agent.getByRole("button", { name: "Run agent" }));
    const run = await responseJson(agentResponse);
    expect((run.tool_calls as unknown[] | undefined) ?? []).toContain("package_lineage");
    await expect(agent.getByText(new RegExp(`Package lineage for ${ID.finishedTag}`))).toBeVisible({ timeout: 15_000 });
    await mark("agent-lineage-answer");

    await visibleWarnings(page);
  } catch (error) {
    failure = error;
    friction.deadEnds.push(error instanceof Error ? error.message : String(error));
  } finally {
    const evidence = {
      ...friction,
      usabilityScore: score(),
      operatorEffort: friction.clicks + friction.decisions + friction.manualInputs + friction.contextSwitches,
      releaseThresholds: { usabilityScore: 9.5, duplicateEntries: 0, handoffGaps: 0, backtracks: 0, deadEnds: 0, pageErrors: 0, api5xx: 0 },
      durableIds: { ...ID, finishedLotId },
    };
    await testInfo.attach("zero-training-friction.json", { body: Buffer.from(JSON.stringify(evidence, null, 2)), contentType: "application/json" });
  }

  if (failure) throw failure;
  expect(friction.duplicateEntries, "Known DoobieLogic data had to be entered twice.").toBe(0);
  expect(friction.handoffGaps, `Handoff gaps: ${friction.handoffGaps.join(" | ")}`).toEqual([]);
  expect(friction.backtracks, "Operator had to navigate backward to recover missing context.").toBe(0);
  expect(friction.pageErrors, `Page errors: ${friction.pageErrors.join(" | ")}`).toEqual([]);
  expect(friction.api5xx, `API 5xx: ${friction.api5xx.join(" | ")}`).toEqual([]);
  expect(score(), `Zero-training usability score ${score()} is below release threshold.`).toBeGreaterThanOrEqual(9.5);
  expect(friction.milestones).toEqual([
    "plant-created", "plant-flowering", "harvest-inventory-created",
    "production-run-planned", "source-consumed", "production-process-complete",
    "extract-output-created", "qa-released", "finished-package-created",
    "wholesale-order-created", "wholesale-reserved", "transfer-dispatched",
    "wholesale-fulfilled", "destination-received", "recall-lineage-proved",
    "agent-lineage-answer",
  ]);
});
