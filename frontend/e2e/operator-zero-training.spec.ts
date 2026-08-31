import { expect, test, type Page } from "@playwright/test";

/**
 * Zero-training operator acceptance gate.
 *
 * This test is intentionally written as a human journey instead of a page-smoke
 * test. It records the amount of operator effort required to move a single
 * Blue Dream lineage from cultivation through wholesale and trace it back.
 *
 * The fixture/seeding layer is expected to provide a vertically licensed demo
 * organization with cultivation, production/manufacturing and wholesale/retail
 * facilities. The test fails on browser crashes, API 5xx responses, dead-end
 * navigation, or if any canonical lifecycle milestone cannot be reached.
 */

type Friction = {
  clicks: number;
  decisions: number;
  manualInputs: number;
  contextSwitches: number;
  backtracks: number;
  deadEnds: string[];
  api4xx: string[];
  api5xx: string[];
  milestones: string[];
};

const friction: Friction = {
  clicks: 0,
  decisions: 0,
  manualInputs: 0,
  contextSwitches: 0,
  backtracks: 0,
  deadEnds: [],
  api4xx: [],
  api5xx: [],
  milestones: [],
};

async function click(page: Page, name: string | RegExp) {
  friction.clicks += 1;
  await page.getByRole("button", { name }).or(page.getByRole("link", { name })).first().click();
}

async function choose(page: Page, label: string | RegExp, option: string | RegExp) {
  friction.decisions += 1;
  friction.clicks += 1;
  const control = page.getByLabel(label).first();
  await control.click();
  if (typeof option === "string") {
    await control.selectOption({ label: option }).catch(async () => control.fill(option));
  } else {
    await page.getByRole("option", { name: option }).first().click();
  }
}

async function fill(page: Page, label: string | RegExp, value: string) {
  friction.manualInputs += 1;
  await page.getByLabel(label).first().fill(value);
}

async function milestone(page: Page, label: string, expected: string | RegExp) {
  await expect(page.getByText(expected).first()).toBeVisible({ timeout: 15_000 });
  friction.milestones.push(label);
}

async function enterWorkspace(page: Page, name: string | RegExp) {
  friction.contextSwitches += 1;
  await click(page, name);
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function attachNetworkFriction(page: Page) {
  page.on("response", response => {
    if (!response.url().includes("/api/")) return;
    const status = response.status();
    const entry = `${status} ${response.request().method()} ${response.url()}`;
    if (status >= 500) friction.api5xx.push(entry);
    else if (status >= 400) friction.api4xx.push(entry);
  });
}

async function auditDeadEnd(page: Page, stage: string) {
  const body = (await page.locator("body").innerText()).toLowerCase();
  const patterns = ["something went wrong", "unexpected error", "page not found", "cannot continue", "service unavailable"];
  const hit = patterns.find(pattern => body.includes(pattern));
  if (hit) friction.deadEnds.push(`${stage}: ${hit}`);
}

test("zero-training operator can take Blue Dream from clone to wholesale receipt and trace it back", async ({ page }, testInfo) => {
  await attachNetworkFriction(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle").catch(() => undefined);

  // 1. Cultivation: create and advance a Blue Dream plant.
  await enterWorkspace(page, /cultivation/i);
  await click(page, /add plant|new plant|create plant/i);
  await fill(page, /strain|cultivar/i, "Blue Dream");
  await choose(page, /stage/i, /clone|vegetative/i);
  await click(page, /save|create/i);
  await milestone(page, "plant-created", /Blue Dream/i);
  await auditDeadEnd(page, "plant-created");

  await click(page, /Blue Dream/i);
  await click(page, /move|change stage|advance/i);
  await choose(page, /stage/i, /flower/i);
  await click(page, /confirm|save|move/i);
  friction.decisions += 1;
  await milestone(page, "plant-flowering", /flower/i);

  // 2. Harvest and material creation.
  await click(page, /harvest/i);
  await fill(page, /wet weight|harvest weight|weight/i, "5000");
  await choose(page, /unit/i, /g|gram/i);
  await click(page, /complete harvest|save harvest|harvest/i);
  await milestone(page, "harvest-created", /harvest|drying|cure/i);
  await auditDeadEnd(page, "harvest");

  // 3. Production: consume source material and create an extraction output.
  await enterWorkspace(page, /production|manufacturing/i);
  await click(page, /new run|create run|start run/i);
  await fill(page, /run name|batch name/i, "Blue Dream Acceptance Run");
  await choose(page, /input|source|material/i, /Blue Dream/i);
  await fill(page, /quantity|input weight|weight/i, "1000");
  await choose(page, /process|run type|method/i, /extract|hydrocarbon|bho|rosin/i);
  await click(page, /start|create run|save/i);
  await milestone(page, "production-run-created", /Blue Dream Acceptance Run/i);

  await click(page, /record output|complete run|finish run/i);
  await fill(page, /output quantity|yield|finished weight/i, "150");
  await fill(page, /output name|product name/i, "Blue Dream Extract");
  await click(page, /save|complete/i);
  await milestone(page, "extract-output-created", /Blue Dream Extract/i);
  await auditDeadEnd(page, "production-output");

  // 4. QA/COA: release the output.
  await enterWorkspace(page, /quality|compliance|lab|coa/i);
  await click(page, /Blue Dream Extract/i);
  await click(page, /add coa|record test|lab result|quality/i);
  await fill(page, /thc/i, "78.4");
  await fill(page, /terp/i, "6.1");
  await choose(page, /result|status/i, /pass|passed|released/i);
  await click(page, /save|release|approve/i);
  await milestone(page, "qa-released", /pass|released|approved/i);

  // 5. Package finished goods.
  await enterWorkspace(page, /packaging|inventory/i);
  await click(page, /new package|package product|create package/i);
  await choose(page, /source|bulk|lot/i, /Blue Dream Extract/i);
  await fill(page, /package name|product name/i, "Blue Dream Vape 1g");
  await fill(page, /unit size|weight per unit/i, "1");
  await fill(page, /units|quantity/i, "100");
  await click(page, /create package|package|save/i);
  await milestone(page, "finished-package-created", /Blue Dream Vape 1g/i);
  await auditDeadEnd(page, "packaging");

  // 6. Wholesale order and outbound transfer.
  await enterWorkspace(page, /wholesale|sales|orders/i);
  await click(page, /new order|create order/i);
  await choose(page, /customer|buyer/i, /.*/);
  await choose(page, /product|item/i, /Blue Dream Vape 1g/i);
  await fill(page, /quantity|units/i, "25");
  await click(page, /submit|create order|save/i);
  await milestone(page, "wholesale-order-created", /order|submitted|approved/i);

  await click(page, /approve|fulfill|pick/i);
  await click(page, /create transfer|manifest|ship/i);
  friction.decisions += 1;
  await milestone(page, "transfer-created", /transfer|manifest|in transit|shipped/i);
  await auditDeadEnd(page, "outbound-transfer");

  // 7. Destination receipt under the destination license/facility.
  await enterWorkspace(page, /receiving|incoming|transfers/i);
  await click(page, /Blue Dream Vape 1g|incoming transfer|manifest/i);
  await click(page, /receive|accept/i);
  await milestone(page, "destination-received", /received|accepted|inventory/i);

  // 8. Recall 360 must reconstruct the same genealogy.
  await enterWorkspace(page, /recall 360|recall/i);
  const recallSearch = page.getByPlaceholder(/search|package|lot|tag/i).first();
  if (await recallSearch.count()) {
    friction.manualInputs += 1;
    await recallSearch.fill("Blue Dream Vape 1g");
  }
  await click(page, /search|trace|open/i);
  await milestone(page, "recall-lineage-visible", /Blue Dream|harvest|source|genealogy|lineage/i);
  await auditDeadEnd(page, "recall-360");

  // 9. Doobie Agent should answer the lineage question from deterministic facts.
  await enterWorkspace(page, /doobie agent|agent/i);
  const prompt = page.getByRole("textbox").last();
  friction.manualInputs += 1;
  await prompt.fill("Where did Blue Dream Vape 1g come from? Trace it back to the original plant/harvest and tell me which production run created it.");
  await click(page, /send|ask/i);
  await milestone(page, "agent-lineage-answer", /Blue Dream|Acceptance Run|harvest|lineage/i);
  await auditDeadEnd(page, "doobie-agent");

  const scorePenalty =
    friction.decisions * 0.5 +
    friction.manualInputs * 0.35 +
    friction.contextSwitches * 0.4 +
    friction.backtracks * 2 +
    friction.deadEnds.length * 5 +
    friction.api5xx.length * 5;
  const usabilityScore = Math.max(0, Math.round((10 - Math.min(10, scorePenalty / 10)) * 10) / 10);

  await testInfo.attach("zero-training-friction.json", {
    body: Buffer.from(JSON.stringify({ ...friction, usabilityScore }, null, 2)),
    contentType: "application/json",
  });

  expect(friction.deadEnds, `Dead ends: ${friction.deadEnds.join(" | ")}`).toEqual([]);
  expect(friction.api5xx, `API 5xx responses: ${friction.api5xx.join(" | ")}`).toEqual([]);
  expect(friction.milestones).toEqual([
    "plant-created",
    "plant-flowering",
    "harvest-created",
    "production-run-created",
    "extract-output-created",
    "qa-released",
    "finished-package-created",
    "wholesale-order-created",
    "transfer-created",
    "destination-received",
    "recall-lineage-visible",
    "agent-lineage-answer",
  ]);
});
