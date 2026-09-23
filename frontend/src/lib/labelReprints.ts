export function validLabelRange(originalQuantity: number, copies: number, firstLabel: number): boolean {
  return Number.isInteger(originalQuantity) && originalQuantity > 0
    && Number.isInteger(copies) && copies >= 1 && copies <= 500
    && Number.isInteger(firstLabel) && firstLabel >= 1
    && firstLabel + copies - 1 <= originalQuantity;
}

export function labelIndices(originalQuantity: number, copies: number, firstLabel: number): number[] {
  if (!validLabelRange(originalQuantity, copies, firstLabel)) return [];
  return Array.from({ length: copies }, (_, index) => firstLabel - 1 + index);
}

export function labelReprintBlock(status: string): string {
  if (status === "archived") return "This label run is archived. Its saved label and history remain available, but archived runs are read-only and cannot be reprinted.";
  if (!["tagged", "printed", "applied", "released", "fulfilled"].includes(status)) return "Assign the finished package tag before printing this saved label run.";
  return "";
}
