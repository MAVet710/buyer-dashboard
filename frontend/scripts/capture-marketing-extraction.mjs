import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const marketingDir = path.join(frontend, "public", "marketing");
const videoDir = path.join(frontend, "test-results", "marketing-extraction-video");
const framesDir = path.join(videoDir, "frames");
const baseURL = process.env.CAPTURE_URL || "http://127.0.0.1:4188";
const ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
await fs.mkdir(marketingDir, { recursive: true });
await fs.rm(videoDir, { recursive: true, force: true });
await fs.mkdir(framesDir, { recursive: true });

const workflow = {
  key: "bho_cured",
  label: "Hydrocarbon cured-resin workflow",
  method: "Hydrocarbon",
  stages: [
    { key: "intake", label: "Material prep", output_fields: ["prepared_input"] },
    { key: "primary_extraction", label: "Primary extraction", output_fields: ["crude_output"] },
    { key: "winterization", label: "Winterization", output_fields: ["winterized_output"] },
    { key: "filtration", label: "Filtration", output_fields: ["filtered_output"] },
    { key: "distillation", label: "Distillation", output_fields: ["distillate_output"] },
    { key: "final_output", label: "Final output", output_fields: ["final_output"] },
  ],
};

const run = {
  id: "live",
  batch_number: "EX-0924-01",
  method: "Hydrocarbon",
  workflow_key: workflow.key,
  current_stage_key: "winterization",
  status: "active",
  release_status: "pending",
  product_family: "Cured resin",
  strain: "Blue Dream",
  toll_processing: false,
  compliance_provider: "metrc",
  license_number: "DEMO-001",
  operator: "Demo Operator",
  notes: "Synthetic marketing demonstration run.",
  updated_at: "2026-09-24T15:24:00Z",
  intermediate_product_type: "Winterized crude",
  final_product_type: "Cured resin concentrate",
  final_output_g: 1760,
  metrc_input_package_id: "1A4-DEMO-INPUT-001",
  metrc_intermediate_package_id: "1A4-DEMO-WIP-001",
  metrc_final_package_id: "1A4-DEMO-OUTPUT-001",
};

const events = [
  { id: "e1", stage_key: "intake", event_type: "completed", input_weight_g: 3000, output_weight_g: 2965, loss_weight_g: 35, loss_reason: "Trim and handling", operator: "Demo Operator", notes: "Material prepared and verified.", occurred_at: "2026-09-24T12:05:00Z" },
  { id: "e2", stage_key: "primary_extraction", event_type: "completed", input_weight_g: 2965, output_weight_g: 1920, loss_weight_g: 1045, loss_reason: "Process reduction", operator: "Demo Operator", notes: "Primary extraction complete.", occurred_at: "2026-09-24T13:18:00Z" },
  { id: "e3", stage_key: "winterization", event_type: "measurement", input_weight_g: 1920, output_weight_g: 1760, loss_weight_g: 160, loss_reason: "Wax and lipid removal", operator: "Demo Operator", notes: "Winterization measurement recorded.", occurred_at: "2026-09-24T14:46:00Z" },
];

const detail = {
  run,
  workflow,
  inputs: [{ id: "input-1", lot_id: "lot-1", role: "primary_input", reserved_quantity: 3000, consumed_quantity: 3000, unit: "g", input_cost_usd: 780, status: "consumed" }],
  outputs: [{ id: "output-1", product_id: "product-1", lot_id: "out-lot-1", position: 1, output_label: "Winterized crude", quantity: 1760, unit: "g", status: "quarantine", coa_status: "pending", compliance_package_id: "1A4-DEMO-WIP-001", output_cost_usd: 1280 }],
  events,
  qa_events: [{ id: "qa-1", output_id: "output-1", event_type: "sample_submitted", result: "pending", coa_reference: "DEMO-COA-0924", deviation_code: "", notes: "QA sample submitted.", actor: "Demo QA", occurred_at: "2026-09-24T15:02:00Z" }],
  cost_events: [
    { id: "c1", category: "material", amount_usd: 780, quantity: 3000, unit: "g", unit_rate_usd: 0.26, source_type: "inventory", actor: "system", notes: "Source material", occurred_at: "2026-09-24T12:00:00Z" },
    { id: "c2", category: "labor", amount_usd: 220, quantity: 4, unit: "hour", unit_rate_usd: 55, source_type: "operator", actor: "Demo Operator", notes: "Run labor", occurred_at: "2026-09-24T14:30:00Z" },
  ],
  traceability: [{ id: "t1", provider: "metrc", operation_type: "input_package_link", status: "verified", external_reference: "1A4-DEMO-INPUT-001", error_message: "", requested_by: "Demo Operator", requested_at: "2026-09-24T12:01:00Z" }],
  mass_balance: { consumed_input: 3000, recorded_output: 1760, yield_pct: 58.67 },
  cogs: { material: 780, labor: 220, packaging: 80, processing: 200, total: 1280, cost_per_output_unit: 0.7273 },
  toll_job: null,
};

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
page.on("pageerror", error => console.error("pageerror", error.message));
await page.addInitScript(() => {
  localStorage.setItem("buyer-dash-theme", "dark");
  localStorage.setItem("buyer-dash-organization", "demo-org");
  localStorage.setItem("buyer-dash-facility", "demo-facility");
  localStorage.setItem("buyer-dash-operation", "Production Ops");
  localStorage.setItem("buyer-dash-data-mode", "Uploads");
});

await page.route("**/api/v1/**", async route => {
  const request = route.request();
  const pathname = new URL(request.url()).pathname;
  const capabilities = { retail: false, production: true, cultivation: false, commercial: false };
  const account = {
    user: { id: "demo-user", display_name: "Demo Operator", email: "demo@doobielogic.test", role: "operator", must_change_password: false },
    organization: { id: "demo-org", name: "DoobieLogic Demo Processing", slug: "demo-processing" },
    facility_id: "demo-facility",
    capabilities,
    facilities: [{ id: "demo-facility", name: "Demo Processing", code: "DEMO", capabilities }],
  };

  if (request.method() !== "GET") {
    await route.fulfill({ status: 200, json: { ok: true } });
    return;
  }
  if (pathname === "/api/v1/account/context") {
    return route.fulfill({ status: 200, json: account });
  }
  if (pathname === "/api/v1/account/access-options") {
    return route.fulfill({ status: 200, json: { organizations: [{ ...account.organization, facilities: account.facilities }], organization_id: "demo-org", facility_id: "demo-facility" } });
  }
  if (pathname === "/api/v1/search") {
    return route.fulfill({ status: 200, json: { results: [] } });
  }
  if (pathname === "/api/v1/extraction/runs") {
    return route.fulfill({ status: 200, json: [run] });
  }
  if (pathname === "/api/v1/extraction/runs/live") {
    return route.fulfill({ status: 200, json: detail });
  }
  if (pathname === "/api/v1/extraction-parity/overview") {
    return route.fulfill({
      status: 200,
      json: {
        runs: [{ id: "live", input_weight_g: 3000, final_output_g: 1760, yield_pct: 58.67, cogs_usd: 1280, cost_per_output_unit: 0.7273, traceability_count: 1, release_status: "pending", qa_hold: false }],
        workflows: [workflow],
        summary: {},
        alerts: [],
        toll_jobs: [],
      },
    });
  }
  if (pathname.endsWith("/extraction/lots")) {
    return route.fulfill({ status: 200, json: [{ lot_id: "lot-1", product_name: "Blue Dream Cured Biomass", lot_code: "BD-0924-A", compliance_package_id: "1A4-DEMO-INPUT-001", available: 0, unit: "g" }] });
  }
  if (pathname.endsWith("/extraction/products")) {
    return route.fulfill({ status: 200, json: [{ id: "product-1", name: "Cured Resin Concentrate", sku: "CR-DEMO-001", item_type: "Concentrate", base_unit: "g" }] });
  }
  if (pathname.endsWith("/extraction/workflows")) {
    return route.fulfill({ status: 200, json: [workflow] });
  }
  if (pathname.endsWith("/extraction-inventory/lots")) {
    return route.fulfill({ status: 200, json: [] });
  }
  return route.fulfill({ status: 200, json: [] });
});
await page.goto(`${baseURL}/production/extraction?extractionView=runs&extractionRun=live`, {
  waitUntil: "networkidle",
});
const workspace = page.locator(".extraction-operator-workspace");
const runHeading = workspace.getByRole("heading", { name: "EX-0924-01", exact: true });
await runHeading.waitFor();
await runHeading.evaluate(element => element.scrollIntoView({ block: "center" }));
await page.waitForTimeout(350);

const frames = [];
async function captureFrame(label, duration) {
  const fileName = `frame-${String(frames.length).padStart(2, "0")}-${label}.png`;
  await page.screenshot({
    path: path.join(framesDir, fileName),
    animations: "disabled",
  });
  frames.push({ fileName, duration });
}

await captureFrame("floor", 1.8);
await fs.copyFile(
  path.join(framesDir, frames[0].fileName),
  path.join(marketingDir, "extraction-workspace-poster.png"),
);

await workspace.getByRole("button", { name: "Open Run 360", exact: true }).click();
const dialog = page.getByRole("dialog", { name: "EX-0924-01", exact: true });
await dialog.waitFor();
await page.waitForTimeout(250);
await captureFrame("overview", 1.5);

for (const [tab, label, duration] of [
  ["Inputs", "inputs", 1.3],
  ["Process", "process", 1.7],
  ["Outputs + QA", "outputs-qa", 1.5],
  ["Traceability", "traceability", 1.5],
]) {
  await dialog.getByRole("button", { name: tab, exact: true }).click();
  await page.waitForTimeout(200);
  await captureFrame(label, duration);
}

await dialog.getByRole("button", { name: "Overview", exact: true }).click();
await page.waitForTimeout(200);
await captureFrame("overview-finish", 1.2);

await page.close();
await context.close();
await browser.close();

const timeline = frames
  .flatMap(frame => [`file '${frame.fileName}'`, `duration ${frame.duration}`])
  .concat(`file '${frames.at(-1).fileName}'`)
  .join("\n");
const timelinePath = path.join(framesDir, "timeline.txt");
await fs.writeFile(timelinePath, timeline, "utf8");

function encodeVideo(args, label) {
  const result = spawnSync(ffmpeg, args, {
    cwd: framesDir,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(`${label} encode failed. ${result.stderr || result.stdout || "Unknown ffmpeg error"}`);
  }
}

const webmPath = path.join(marketingDir, "extraction-workspace.webm");
const mp4Path = path.join(marketingDir, "extraction-workspace.mp4");
const inputArgs = ["-y", "-f", "concat", "-safe", "0", "-i", timelinePath, "-vf", "fps=15,format=yuv420p", "-an"];

encodeVideo(
  [...inputArgs, "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-deadline", "good", "-cpu-used", "3", webmPath],
  "WebM",
);
encodeVideo(
  [...inputArgs, "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-movflags", "+faststart", mp4Path],
  "MP4",
);

const [webmStat, mp4Stat] = await Promise.all([fs.stat(webmPath), fs.stat(mp4Path)]);
await fs.rm(videoDir, { recursive: true, force: true });
console.log(
  `Captured extraction marketing preview: WebM ${Math.round(webmStat.size / 1024)} KB, MP4 ${Math.round(mp4Stat.size / 1024)} KB`,
);
