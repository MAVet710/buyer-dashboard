#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const REGULATOR_ACTION_COUNT = 46;
const PREREQUISITE_CHECK_COUNT = 1;
const INTERNAL_CHECK_COUNT = REGULATOR_ACTION_COUNT + PREREQUISITE_CHECK_COUNT;

const WORKBOOK_SHEETS = [
  "CompanyInformation",
  "Instructions ",
  "Permissions",
  "States",
  "Locations",
  "Strains",
  "Items",
  "Closed Loop Environment ",
  "Closed Loop States PlantBatches",
  "PlantBatches",
  "Plants",
  "Harvest",
  "Packages",
  "CA ONLY Labs",
  "LabResults",
  "Sales",
  "Sales with Patient Look Up",
  "Sales Deliveries (NOT CA)",
  "CA- SalesRetailDeliveries",
  "GET Transfers and Wholesale",
  "Transfer Templates",
  "Transfer External Incoming",
];

const SECRET_TOKENS = [
  "api_key",
  "apikey",
  "vendor_key",
  "user_key",
  "integrator_key",
  "authorization",
  "password",
  "secret",
  "token",
];
const REDACTED_METADATA_KEYS = new Set([
  "secret_workbook_fields",
  "secret_handling",
  "secret_fields_filled",
  "secret_values_recorded",
  "secret",
]);

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(2);
}

function readJson(filename) {
  try {
    return JSON.parse(fs.readFileSync(filename, "utf8"));
  } catch (error) {
    fail(`Could not read ${filename}: ${error.message}`);
  }
}

function normalizeKey(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function credentialLikePaths(value, prefix = "") {
  const findings = [];
  if (Array.isArray(value)) {
    value.forEach((nested, index) => {
      findings.push(...credentialLikePaths(nested, `${prefix}[${index}]`));
    });
    return findings;
  }
  if (value && typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      const next = prefix ? `${prefix}.${key}` : key;
      const normalized = normalizeKey(key);
      if (REDACTED_METADATA_KEYS.has(normalized)) {
        continue;
      }
      if (SECRET_TOKENS.some((token) => normalized.includes(token))) {
        findings.push(next);
      }
      findings.push(...credentialLikePaths(nested, next));
    }
  }
  return findings;
}

function sameArray(left, right) {
  return (
    Array.isArray(left) &&
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

const [reportArg, preserveManifestArg, resultsManifestArg] = process.argv.slice(2);
if (!reportArg || !preserveManifestArg || !resultsManifestArg) {
  fail("Usage: node verify_final.mjs <final_report.json> <workbook.manifest.json> <workbook.results.manifest.json>");
}

const reportPath = path.resolve(reportArg);
const preserveManifestPath = path.resolve(preserveManifestArg);
const resultsManifestPath = path.resolve(resultsManifestArg);
const report = readJson(reportPath);
const manifest = readJson(preserveManifestPath);
const resultsManifest = readJson(resultsManifestPath);

if (report.schema_version !== 1) fail("Unsupported final report schema_version.");
if (report.state !== "MA" || report.environment !== "sandbox") {
  fail("Final report is not scoped to the Massachusetts sandbox.");
}
if (report.applicable_task_count !== REGULATOR_ACTION_COUNT || !Array.isArray(report.tasks) || report.tasks.length !== INTERNAL_CHECK_COUNT) {
  fail("Final report must contain 46 regulator action rows plus the mandatory facilities prerequisite.");
}
const taskNumbers = report.tasks.map((row) => row.number);
if (!sameArray(taskNumbers, Array.from({ length: INTERNAL_CHECK_COUNT }, (_, index) => index + 1))) {
  fail("Final report internal check numbering is incomplete or out of order.");
}
if (report.tasks[0]?.operation_type !== "facilities") {
  fail("Internal check 1 must remain the mandatory GET /facilities/v2 prerequisite.");
}
if (report.tasks.some((row) => row.status !== "passed")) {
  fail("At least one required internal evaluation check is not passed in the local evidence report.");
}
if (report.summary?.passed !== INTERNAL_CHECK_COUNT || report.summary?.failed !== 0 || report.summary?.missing !== 0) {
  fail("Final report summary is inconsistent with all 47 required internal checks passing.");
}
if (report.submission_ready !== true || report.status !== "ready_for_metrc_review") {
  fail("Final report is not marked ready for Metrc review.");
}
if (report.regulator_approval_claimed !== false) {
  fail("Local finalization must not claim regulator approval.");
}
if ((report.missing_company_information ?? []).length !== 0) {
  fail("Required non-secret CompanyInformation fields are still missing.");
}

const reportCredentialPaths = credentialLikePaths(report);
if (reportCredentialPaths.length) {
  fail(`Credential-like fields leaked into final report: ${reportCredentialPaths.slice(0, 5).join(", ")}`);
}

// First manifest proves CompanyInformation was populated without touching task
// result or Metrc Use Only cells.
if (manifest.schema_version !== 1) fail("Unsupported workbook preservation manifest schema_version.");
if (manifest.sheet_count !== 22 || !sameArray(manifest.sheet_names, WORKBOOK_SHEETS)) {
  fail("Workbook preservation manifest does not preserve the exact 22-sheet template structure.");
}
if ((manifest.missing_labels ?? []).length !== 0 || (manifest.missing_values ?? []).length !== 0) {
  fail("Workbook preservation manifest still has missing CompanyInformation labels or values.");
}
if (manifest.secret_values_recorded !== false) {
  fail("Workbook preservation manifest must never record secret values.");
}
if (manifest.task_result_cells_modified !== false || manifest.metrc_use_only_cells_modified !== false) {
  fail("CompanyInformation preservation step modified protected evaluation/result cells.");
}
for (const field of ["Vendor Key Used", "User Key Used"]) {
  if (manifest.secret_fields_filled?.[field] !== true) {
    fail(`${field} was not filled in the local submission workbook.`);
  }
}
const manifestCredentialPaths = credentialLikePaths(manifest);
if (manifestCredentialPaths.length) {
  fail(`Credential-like fields leaked into workbook preservation manifest: ${manifestCredentialPaths.slice(0, 5).join(", ")}`);
}

// Second manifest proves the intentional submission step filled only the visible
// regulator verification/permission cells and still did not touch Metrc Use Only.
if (resultsManifest.schema_version !== 1) fail("Unsupported workbook results manifest schema_version.");
if (resultsManifest.sheet_count !== 22 || !sameArray(resultsManifest.sheet_names, WORKBOOK_SHEETS)) {
  fail("Workbook results manifest does not preserve the exact 22-sheet template structure.");
}
if (resultsManifest.regulator_action_rows_filled !== REGULATOR_ACTION_COUNT || resultsManifest.expected_regulator_action_rows !== REGULATOR_ACTION_COUNT) {
  fail("Workbook results writer did not populate all 46 regulator action verification rows.");
}
if (resultsManifest.task_result_cells_modified !== true) {
  fail("Workbook results writer did not report intentional task-result population.");
}
if (resultsManifest.permissions_table_modified !== true) {
  fail("Workbook results writer did not populate the Permissions request table.");
}
if (resultsManifest.metrc_use_only_cells_modified !== false) {
  fail("Workbook results writer touched Metrc Use Only cells.");
}
if (resultsManifest.secret_values_recorded !== false) {
  fail("Workbook results manifest must never record secret values.");
}
const resultsCredentialPaths = credentialLikePaths(resultsManifest);
if (resultsCredentialPaths.length) {
  fail(`Credential-like fields leaked into workbook results manifest: ${resultsCredentialPaths.slice(0, 5).join(", ")}`);
}

console.log("FINAL VERIFIED: all 47 internal checks passed (46 regulator action rows + 1 facilities/permissions prerequisite), CompanyInformation is complete, the Permissions request table and all 46 visible regulator verification rows are populated, and the 22-sheet workbook structure is preserved.");
console.log("No regulator approval is claimed; the package is ready to submit to Metrc for review.");
