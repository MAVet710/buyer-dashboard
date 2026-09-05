#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const WORKBOOK_SHEETS = [
  "CompanyInformation",
  "Instructions",
  "Permissions",
  "States",
  "Locations",
  "Strains",
  "Items",
  "Closed Loop Environment",
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
      if (SECRET_TOKENS.some((token) => normalized.includes(token))) {
        // Redacted bookkeeping fields are explicitly allowed.
        const allowed = new Set([
          "secret_workbook_fields",
          "secret_handling",
          "secret_fields_filled",
          "secret_values_recorded",
        ]);
        if (!allowed.has(normalized)) findings.push(next);
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

const [reportArg, manifestArg] = process.argv.slice(2);
if (!reportArg || !manifestArg) {
  fail("Usage: node verify_final.mjs <final_report.json> <workbook.manifest.json>");
}

const reportPath = path.resolve(reportArg);
const manifestPath = path.resolve(manifestArg);
const report = readJson(reportPath);
const manifest = readJson(manifestPath);

if (report.schema_version !== 1) fail("Unsupported final report schema_version.");
if (report.state !== "MA" || report.environment !== "sandbox") {
  fail("Final report is not scoped to the Massachusetts sandbox.");
}
if (report.applicable_task_count !== 47 || !Array.isArray(report.tasks) || report.tasks.length !== 47) {
  fail("Final report does not contain all 47 Massachusetts-applicable tasks.");
}
const taskNumbers = report.tasks.map((row) => row.number);
if (!sameArray(taskNumbers, Array.from({ length: 47 }, (_, index) => index + 1))) {
  fail("Final report task numbering is incomplete or out of order.");
}
if (report.tasks.some((row) => row.status !== "passed")) {
  fail("At least one applicable evaluation task is not passed in the local evidence report.");
}
if (report.summary?.passed !== 47 || report.summary?.failed !== 0 || report.summary?.missing !== 0) {
  fail("Final report summary is inconsistent with a 47/47 evidence package.");
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

if (manifest.schema_version !== 1) fail("Unsupported workbook manifest schema_version.");
if (manifest.sheet_count !== 22 || !sameArray(manifest.sheet_names, WORKBOOK_SHEETS)) {
  fail("Workbook manifest does not preserve the exact 22-sheet template structure.");
}
if ((manifest.missing_labels ?? []).length !== 0 || (manifest.missing_values ?? []).length !== 0) {
  fail("Workbook manifest still has missing CompanyInformation labels or values.");
}
if (manifest.secret_values_recorded !== false) {
  fail("Workbook manifest must never record secret values.");
}
if (manifest.task_result_cells_modified !== false || manifest.metrc_use_only_cells_modified !== false) {
  fail("Workbook preservation step modified protected evaluation/result cells.");
}
for (const field of ["Vendor Key Used", "User Key Used"]) {
  if (manifest.secret_fields_filled?.[field] !== true) {
    fail(`${field} was not filled in the local submission workbook.`);
  }
}

const manifestCredentialPaths = credentialLikePaths(manifest);
if (manifestCredentialPaths.length) {
  fail(`Credential-like fields leaked into workbook manifest: ${manifestCredentialPaths.slice(0, 5).join(", ")}`);
}

console.log("FINAL VERIFIED: 47/47 local evidence tasks passed, CompanyInformation is complete, and the 22-sheet workbook structure is preserved.");
console.log("No regulator approval is claimed; the package is ready to submit to Metrc for review.");
