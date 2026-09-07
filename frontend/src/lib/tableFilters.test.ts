import { describe, expect, it } from "vitest";
import { applyTableFiltersAndSort, distinctTableValues, tableValueText, type TableFilters } from "./tableFilters";

type Row = { name: string; status: string; available: number | null; received: string | null };
const rows: Row[] = [
  { name: "GMO Flower", status: "Available", available: 12, received: "2026-09-01" },
  { name: "Blue Dream", status: "Hold", available: 0, received: "2026-08-20" },
  { name: "gmo Pre-Roll", status: "Available", available: 4, received: "2026-09-05" },
  { name: "Mystery", status: "", available: null, received: null },
];
const getter = (row: Row, column: string) => ({
  Name: row.name,
  Status: row.status,
  Available: row.available,
  Received: row.received,
}[column]);

describe("table filter engine", () => {
  it("combines multiple column filters with AND semantics", () => {
    const filters: TableFilters = {
      Status: { type: "values", values: ["Available"] },
      Available: { type: "number", mode: "gt", value: 5 },
    };
    expect(applyTableFiltersAndSort(rows, filters, null, getter).map(row => row.name)).toEqual(["GMO Flower"]);
  });

  it("treats an empty categorical selection as matching no rows", () => {
    expect(applyTableFiltersAndSort(rows, { Status: { type: "values", values: [] } }, null, getter)).toEqual([]);
  });

  it("supports case-insensitive text contains and equals", () => {
    expect(applyTableFiltersAndSort(rows, { Name: { type: "text", mode: "contains", value: "GMO" } }, null, getter).map(row => row.name)).toEqual(["GMO Flower", "gmo Pre-Roll"]);
    expect(applyTableFiltersAndSort(rows, { Name: { type: "text", mode: "equals", value: "blue dream" } }, null, getter).map(row => row.name)).toEqual(["Blue Dream"]);
  });

  it("supports numeric between and greater-than filters", () => {
    expect(applyTableFiltersAndSort(rows, { Available: { type: "number", mode: "between", value: 3, max: 10 } }, null, getter).map(row => row.available)).toEqual([4]);
    expect(applyTableFiltersAndSort(rows, { Available: { type: "number", mode: "gt", value: 0 } }, null, getter).map(row => row.available)).toEqual([12, 4]);
  });

  it("supports date before and between filters", () => {
    expect(applyTableFiltersAndSort(rows, { Received: { type: "date", mode: "before", value: "2026-09-01" } }, null, getter).map(row => row.name)).toEqual(["Blue Dream"]);
    expect(applyTableFiltersAndSort(rows, { Received: { type: "date", mode: "between", value: "2026-09-01", max: "2026-09-05" } }, null, getter).map(row => row.name)).toEqual(["GMO Flower", "gmo Pre-Roll"]);
  });

  it("sorts numeric and human text values while keeping blanks last", () => {
    expect(applyTableFiltersAndSort(rows, {}, { column: "Available", direction: "desc" }, getter).map(row => row.available)).toEqual([12, 4, 0, null]);
    expect(applyTableFiltersAndSort(rows, {}, { column: "Name", direction: "asc" }, getter).map(row => row.name)).toEqual(["Blue Dream", "GMO Flower", "gmo Pre-Roll", "Mystery"]);
  });

  it("returns unique display values and normalizes blank values", () => {
    expect(distinctTableValues(rows, "Status", getter)).toEqual(["Available", "Hold", "—"]);
    expect(tableValueText(" ")).toBe("—");
  });
});
