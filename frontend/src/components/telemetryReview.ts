import { record } from "./cultivationIntelligenceTypes";

export function sourceUnits(metric: string, canonical: string) {
  const alternatives: Record<string, string[]> = { C: ["C", "F"], "mS/cm": ["mS/cm", "uS/cm"], L: ["L", "mL", "US gal", "imperial gal"], s: ["s", "min"], "L/min": ["L/min", "US gal/min"], state: ["state", "bool"] };
  return metric && canonical ? alternatives[canonical] || [canonical] : [];
}
const fields = ["event_id", "source_device_id", "source_channel", "source_metric", "value", "unit", "observed_at"];

// A bounded source preview only. Normalization and attribution remain server decisions.
export function readSourcePreview(content: string, format: string): Record<string, unknown>[] {
  if (!content.trim()) return [];
  if (new TextEncoder().encode(content).length > 1048576) throw new Error("File exceeds 1 MiB.");
  let source: unknown;
  if (format === "json") {
    try { source = JSON.parse(content); } catch { throw new Error("Unable to read JSON. Choose a normalized export containing an array of readings."); }
  } else {
    const lines: string[][] = []; let row: string[] = [], cell = "", quoted = false;
    const input = content.replace(/^\uFEFF/, "");
    for (let i = 0; i < input.length; i++) {
      const char = input[i];
      if (char === '"') { if (quoted && input[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted; }
      else if (!quoted && (char === "," || char === "\n" || char === "\r")) {
        row.push(cell); cell = "";
        if (char !== ",") { if (row.some(value => value !== "")) lines.push(row); row = []; if (char === "\r" && input[i + 1] === "\n") i++; }
      } else cell += char;
      if (lines.length > 501) throw new Error("Choose an export with at most 500 rows.");
    }
    if (quoted) throw new Error("CSV contains an unfinished quoted field.");
    if (cell || row.length) { row.push(cell); lines.push(row); }
    const header = lines.shift() || [];
    if (new Set(header).size !== header.length || fields.some(field => !header.includes(field))) throw new Error("CSV needs the documented source column names, each once.");
    source = lines.map(values => { if (values.length !== header.length) throw new Error("CSV row columns do not match its header."); return Object.fromEntries(header.map((key, i) => [key, values[i]])); });
  }
  if (!Array.isArray(source) || source.length > 500) throw new Error("Choose a normalized export with an array of at most 500 rows.");
  const result = source.map(record);
  if (result.some(row => fields.some(field => !(field in row)))) throw new Error("Each reading needs source identity, device, channel, metric, value, unit and observation time.");
  return result;
}

export function evidenceTimestamp(input: unknown): string {
  const date = typeof input === "number" ? new Date(input * 1000) : typeof input === "string" ? new Date(input) : null;
  return date && Number.isFinite(date.getTime()) ? date.toISOString() : "";
}
export function historicalWindow(summary: unknown) {
  const value = record(summary);
  return { start: evidenceTimestamp(value.start), end: evidenceTimestamp(value.end) };
}
