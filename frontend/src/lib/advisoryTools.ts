export type ScoreQuestion = { id: string; category: string; text: string };
export const scoreQuestions: ScoreQuestion[] = [
  {
    "id": "inventory-1",
    "category": "Inventory",
    "text": "Stock records are checked against physical counts on a defined schedule."
  },
  {
    "id": "inventory-2",
    "category": "Inventory",
    "text": "Aging stock is reviewed with a named owner and a next action."
  },
  {
    "id": "inventory-3",
    "category": "Inventory",
    "text": "Receiving captures quantities, product identity and discrepancies before stock is released."
  },
  {
    "id": "inventory-4",
    "category": "Inventory",
    "text": "Unavailable, held and sellable stock can be distinguished in reports."
  },
  {
    "id": "inventory-5",
    "category": "Inventory",
    "text": "Inventory adjustments have a reason, supporting evidence and review."
  },
  {
    "id": "purchasing-1",
    "category": "Purchasing",
    "text": "Reorder decisions use a known sales window and current available stock."
  },
  {
    "id": "purchasing-2",
    "category": "Purchasing",
    "text": "Purchasing considers open orders and expected receipt dates."
  },
  {
    "id": "purchasing-3",
    "category": "Purchasing",
    "text": "Category and vendor performance are reviewed before buying."
  },
  {
    "id": "purchasing-4",
    "category": "Purchasing",
    "text": "Stockouts and excess stock inform the next purchasing cycle."
  },
  {
    "id": "purchasing-5",
    "category": "Purchasing",
    "text": "Purchasing responsibilities, spending boundaries and review cadence are clear."
  },
  {
    "id": "processes-1",
    "category": "Processes",
    "text": "Current SOPs describe the work people actually perform."
  },
  {
    "id": "processes-2",
    "category": "Processes",
    "text": "Receiving, transfer and reconciliation exceptions have an escalation path."
  },
  {
    "id": "processes-3",
    "category": "Processes",
    "text": "Operational compliance checks reference the applicable state and license scope."
  },
  {
    "id": "processes-4",
    "category": "Processes",
    "text": "Records needed for internal review are organized and retrievable."
  },
  {
    "id": "processes-5",
    "category": "Processes",
    "text": "Corrective actions have an owner, due date and follow-up."
  },
  {
    "id": "people-production-1",
    "category": "People & production",
    "text": "Each shift has clear responsibilities and handoff records."
  },
  {
    "id": "people-production-2",
    "category": "People & production",
    "text": "Staff are trained on current procedures and changes are communicated."
  },
  {
    "id": "people-production-3",
    "category": "People & production",
    "text": "Production inputs, outputs and losses can be traced to a run or batch."
  },
  {
    "id": "people-production-4",
    "category": "People & production",
    "text": "Production capacity and material availability inform scheduling."
  },
  {
    "id": "people-production-5",
    "category": "People & production",
    "text": "Production or service handoffs identify the next owner and release criteria."
  },
  {
    "id": "technology-1",
    "category": "Technology & controls",
    "text": "Core systems use consistent identifiers for products, locations and records."
  },
  {
    "id": "technology-2",
    "category": "Technology & controls",
    "text": "Reconciliation differences between systems are investigated before adjustment."
  },
  {
    "id": "technology-3",
    "category": "Technology & controls",
    "text": "Access reflects job responsibilities and is reviewed when roles change."
  },
  {
    "id": "technology-4",
    "category": "Technology & controls",
    "text": "Management reports define their source, refresh time and calculation."
  },
  {
    "id": "technology-5",
    "category": "Technology & controls",
    "text": "Important operational decisions can be explained from an audit trail."
  }
];
export type ScoreAnswers = Record<string, number | null>;
export function operationsScore(answers: ScoreAnswers) {
  if (Object.keys(answers).length !== scoreQuestions.length || scoreQuestions.some(q => !(q.id in answers))) throw new Error("Answer every question, including not applicable where appropriate.");
  const groups: Record<string, {sum: number; count: number}> = {};
  let sum = 0, count = 0;
  for (const q of scoreQuestions) {
    const value = answers[q.id];
    if (value !== null && (!Number.isInteger(value) || value < 0 || value > 4)) throw new Error("Choose a valid answer for each question.");
    groups[q.category] ??= {sum: 0, count: 0};
    if (value !== null) { groups[q.category].sum += value; groups[q.category].count++; sum += value; count++; }
  }
  if (count < 15) throw new Error("At least 15 applicable answers are needed for a useful score.");
  return {overall: Math.round(sum / (count * 4) * 100), answered: count, categories: Object.entries(groups).map(([name, g]) => ({name, score: g.count ? Math.round(g.sum / (g.count * 4) * 100) : null, count: g.count}))};
}

export const inventoryColumns = ["SKU", "Product", "Category", "Quantity", "Cost", "Price", "Last Sale Date", "Received Date", "Vendor", "Sales Quantity", "Revenue"] as const;
export type InventoryColumn = typeof inventoryColumns[number];
export type ColumnMapping = Partial<Record<InventoryColumn, string>>;
export const CSV_MAX_BYTES = 2 * 1024 * 1024;
export const CSV_MAX_ROWS = 5000;
export function safeFilename(value: string) { return value.split(/[\\/]/).pop()!.replace(/[^\w. ()-]/g, "_").slice(0, 120); }

/** Bounded RFC4180-style parser. Cells remain text and are never evaluated or exported. */
export function parseInventoryCsv(text: string) {
  if (new TextEncoder().encode(text).length > CSV_MAX_BYTES) throw new Error("Use a CSV smaller than 2 MB.");
  text = text.replace(/^\uFEFF/, "");
  if (text.includes("\0")) throw new Error("This file contains binary data. Export a UTF-8 CSV.");
  const records: string[][] = []; let row: string[] = [], cell = "", quoted = false, closed = false;
  const addCell = () => { row.push(cell.trim()); cell = ""; closed = false; if (row.length > 64) throw new Error("Use at most 64 columns."); };
  const addRow = () => { addCell(); if (row.some(Boolean)) records.push(row); row = []; if (records.length > CSV_MAX_ROWS + 1) throw new Error("Use at most 5,000 inventory rows."); };
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"') { if (text[i+1] === '"') { cell += '"'; i++; } else { quoted = false; closed = true; } }
      else cell += char;
    } else if (char === ',' ) addCell();
    else if (char === '\n' || char === '\r') { if (char === '\r' && text[i+1] === '\n') i++; addRow(); }
    else if (char === '"' && !cell && !closed) quoted = true;
    else if (char === '"' || (closed && char.trim())) throw new Error("Malformed CSV quoting. Export the file again as CSV.");
    else if (!closed) cell += char;
    if (cell.length > 2000) throw new Error("A cell exceeds the 2,000-character limit.");
  }
  if (quoted) throw new Error("The CSV has an unclosed quoted field.");
  if (cell || row.length || closed) addRow();
  const headers = records.shift();
  if (!headers?.length || !records.length) throw new Error("Include a header row and at least one inventory row.");
  if (headers.some(h => !h) || new Set(headers.map(h => h.toLowerCase())).size !== headers.length) throw new Error("Column headers must be nonempty and unique.");
  if (records.some(r => r.length !== headers.length)) throw new Error("Each row must have the same number of columns as the header.");
  const formulaCells = records.flat().filter(v => /^[=+@]|^-\D/.test(v)).length;
  return {headers, rows: records, formulaCells};
}

function number(value: string | undefined): number | null {
  if (!value || !/^\d+(?:\.\d+)?$/.test(value)) return null;
  const n = Number(value); return Number.isFinite(n) && n <= 1e12 ? n : null;
}
function age(value: string | undefined, today: string): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(value + "T00:00:00Z");
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0,10) !== value) return null;
  const days = (Date.parse(today + "T00:00:00Z") - date.getTime()) / 86400000;
  return days >= 0 && Number.isFinite(days) ? Math.floor(days) : null;
}
export type InventoryMetric = {label: string; value: string; explanation: string};
export function inventoryHealth(headers: string[], rows: string[][], mapping: ColumnMapping, salesDays: number, today = new Date().toISOString().slice(0,10)) {
  if (!mapping.Quantity || (!mapping.SKU && !mapping.Product)) throw new Error("Map Quantity and either SKU or Product before analyzing.");
  const mapped = Object.values(mapping).filter(Boolean);
  if (new Set(mapped).size !== mapped.length || mapped.some(h => !headers.includes(h))) throw new Error("Map each source column only once.");
  if (!Number.isInteger(salesDays) || salesDays < 1 || salesDays > 366) throw new Error("Use a sales observation window of 1–366 days.");
  const get = (row: string[], key: InventoryColumn) => mapping[key] ? row[headers.indexOf(mapping[key]!)] : undefined;
  const data = rows.map(row => ({sku: get(row, "SKU") || get(row, "Product"), qty: number(get(row,"Quantity")), cost: number(get(row,"Cost")), price: number(get(row,"Price")), sales: number(get(row,"Sales Quantity")), category: get(row,"Category"), received: age(get(row,"Received Date"),today), lastSale: age(get(row,"Last Sale Date"),today)}));
  if (data.some(d => !d.sku || d.qty === null)) throw new Error("Every row needs a product identifier and a non-negative numeric quantity. Use decimal numbers without currency symbols or thousands separators.");
  const metrics: InventoryMetric[] = []; const warnings: string[] = [];
  const add = (label: string, value: string, explanation: string) => metrics.push({label,value,explanation});
  add("Inventory rows", String(data.length), "Rows may represent multiple lots of the same SKU.");
  const knownCost = data.filter(d=>d.cost!==null);
  if (knownCost.length === data.length) {
    const value = data.reduce((s,d)=>s+d.qty!*d.cost!,0);
    add("Inventory cost value", value.toLocaleString(undefined,{maximumFractionDigits:2}), "Quantity × unit cost. Amounts use the source currency; this is not an accounting valuation.");
    const bySku = new Map<string,number>(); for (const d of data) bySku.set(d.sku!, (bySku.get(d.sku!)||0)+d.qty!*d.cost!);
    if (value > 0) add("Top 5 SKU concentration", (100*[...bySku.values()].sort((a,b)=>b-a).slice(0,5).reduce((a,b)=>a+b,0)/value).toFixed(1)+"%", "Share of inventory cost value across the five largest SKU balances.");
    if (value > 0 && data.every(d=>d.category)) { const totals = new Map<string,number>();for(const d of data) totals.set(d.category!, (totals.get(d.category!)||0)+d.qty!*d.cost!);const top=[...totals].sort((a,b)=>b[1]-a[1])[0];add("Largest category concentration", (100*top[1]/value).toFixed(1)+"%", `${top[0]}: share of inventory cost value.`); }
    else warnings.push("Category concentration needs Category on every row and positive inventory value.");
  } else warnings.push(`Cost value and concentration unavailable: valid unit Cost exists on ${knownCost.length}/${data.length} rows.`);
  const dated = data.filter(d=>d.received!==null);
  if (dated.length) add("Mean received age", Math.round(dated.reduce((s,d)=>s+d.received!,0)/dated.length)+" days", `Unweighted mean of ${dated.length}/${data.length} dated rows. Received date is not harvest or expiry date.`);
  else warnings.push("Inventory age needs Received Date in YYYY-MM-DD format; future and invalid dates are excluded.");
  const sold = data.filter(d=>d.sales!==null);
  if (sold.length) {
    const withRate = sold.filter(d=>d.sales!>0);
    add("Stock cover under 7 days", String(withRate.filter(d=>d.qty!/(d.sales!/salesDays)<7).length), `${withRate.length}/${data.length} rows have positive sales. Quantity ÷ (Sales Quantity ÷ ${salesDays} days). The 7-day screen is illustrative, not a reorder target.`);
    add("Stock cover above 60 days", String(withRate.filter(d=>d.qty!/(d.sales!/salesDays)>60).length), "The 60-day screen flags review candidates, not a universal overstock threshold. All sales quantities must cover the same observation window and use matching stock units.");
    add("Stock with zero period sales", String(sold.filter(d=>d.qty!>0&&d.sales===0).length), `Positive stock and zero recorded units sold during the supplied ${salesDays}-day window. Days on hand is undefined for zero sales.`);
  } else warnings.push("Days on hand needs Sales Quantity and its observation window. Current stock alone cannot establish sales velocity.");
  const last = data.filter(d=>d.lastSale!==null);
  if(last.length) add("No sale in 90+ days", String(last.filter(d=>d.qty!>0&&d.lastSale!>=90).length), `Review candidates among ${last.length}/${data.length} valid Last Sale Date rows. This does not establish that stock is unsellable.`);
  else warnings.push("Slow-mover date review needs Last Sale Date in YYYY-MM-DD format. Missing dates are not treated as zero sales.");
  if(data.every(d=>d.price!==null)) add("Stock at listed price", data.reduce((s,d)=>s+d.qty!*d.price!,0).toLocaleString(undefined,{maximumFractionDigits:2}), "Quantity × listed unit price; not forecast revenue or realizable value.");
  warnings.push("Margins, expiry, lost sales and reorder recommendations are not inferred. Revenue alone does not establish sold-unit costs or profit.");
  return {metrics,warnings};
}
