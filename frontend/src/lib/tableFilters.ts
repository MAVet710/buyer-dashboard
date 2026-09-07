export type TableSortDirection = "asc" | "desc";
export type TableSort = { column: string; direction: TableSortDirection } | null;

export type ValuesTableFilter = { type: "values"; values: string[] };
export type TextTableFilter = { type: "text"; mode: "contains" | "equals"; value: string };
export type NumberTableFilter = {
  type: "number";
  mode: "eq" | "gt" | "gte" | "lt" | "lte" | "between";
  value: number;
  max?: number;
};
export type DateTableFilter = {
  type: "date";
  mode: "on" | "before" | "after" | "between";
  value: string;
  max?: string;
};
export type TableFilter = ValuesTableFilter | TextTableFilter | NumberTableFilter | DateTableFilter;
export type TableFilters = Record<string, TableFilter>;
export type TableValueGetter<Row> = (row: Row, column: string) => unknown;

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export function tableValueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  const text = String(value).trim();
  return text || "—";
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (value === null || value === undefined || value === "") return null;
  const cleaned = String(value).replace(/[$,%]/g, "").replace(/,/g, "").trim();
  if (!cleaned || cleaned === "—") return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateValue(value: unknown): number | null {
  if (value instanceof Date) return Number.isFinite(value.getTime()) ? value.getTime() : null;
  if (value === null || value === undefined || value === "") return null;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function matchesFilter(value: unknown, filter: TableFilter): boolean {
  if (filter.type === "values") {
    if (!filter.values.length) return false;
    const expected = new Set(filter.values.map(item => item.toLocaleLowerCase()));
    return expected.has(tableValueText(value).toLocaleLowerCase());
  }
  if (filter.type === "text") {
    const needle = filter.value.trim().toLocaleLowerCase();
    if (!needle) return true;
    const haystack = tableValueText(value).toLocaleLowerCase();
    return filter.mode === "equals" ? haystack === needle : haystack.includes(needle);
  }
  if (filter.type === "number") {
    const current = numberValue(value);
    if (current === null) return false;
    if (filter.mode === "eq") return current === filter.value;
    if (filter.mode === "gt") return current > filter.value;
    if (filter.mode === "gte") return current >= filter.value;
    if (filter.mode === "lt") return current < filter.value;
    if (filter.mode === "lte") return current <= filter.value;
    return current >= Math.min(filter.value, filter.max ?? filter.value) && current <= Math.max(filter.value, filter.max ?? filter.value);
  }
  const current = dateValue(value);
  const start = dateValue(filter.value);
  if (current === null || start === null) return false;
  if (filter.mode === "on") {
    const day = new Date(current).toISOString().slice(0, 10);
    return day === new Date(start).toISOString().slice(0, 10);
  }
  if (filter.mode === "before") return current < start;
  if (filter.mode === "after") return current > start;
  const end = dateValue(filter.max);
  if (end === null) return current >= start;
  return current >= Math.min(start, end) && current <= Math.max(start, end);
}

function compareValues(left: unknown, right: unknown): number {
  const leftBlank = left === null || left === undefined || tableValueText(left) === "—";
  const rightBlank = right === null || right === undefined || tableValueText(right) === "—";
  if (leftBlank && rightBlank) return 0;
  if (leftBlank) return 1;
  if (rightBlank) return -1;
  const leftNumber = numberValue(left);
  const rightNumber = numberValue(right);
  if (leftNumber !== null && rightNumber !== null) return leftNumber - rightNumber;
  return collator.compare(tableValueText(left), tableValueText(right));
}

export function applyTableFiltersAndSort<Row>(
  rows: readonly Row[],
  filters: TableFilters,
  sort: TableSort,
  getter: TableValueGetter<Row>,
): Row[] {
  const entries = Object.entries(filters);
  const filtered = entries.length
    ? rows.filter(row => entries.every(([column, filter]) => matchesFilter(getter(row, column), filter)))
    : [...rows];
  if (!sort) return filtered;
  return filtered
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const compared = compareValues(getter(a.row, sort.column), getter(b.row, sort.column));
      if (compared === 0) return a.index - b.index;
      return sort.direction === "asc" ? compared : -compared;
    })
    .map(item => item.row);
}

export function distinctTableValues<Row>(
  rows: readonly Row[],
  column: string,
  getter: TableValueGetter<Row>,
): string[] {
  const values = new Map<string, string>();
  for (const row of rows) {
    const text = tableValueText(getter(row, column));
    const key = text.toLocaleLowerCase();
    if (!values.has(key)) values.set(key, text);
  }
  return [...values.values()].sort((a, b) => {
    if (a === "—") return 1;
    if (b === "—") return -1;
    return collator.compare(a, b);
  });
}

export function hasActiveTableFilters(filters: TableFilters): boolean {
  return Object.keys(filters).length > 0;
}
