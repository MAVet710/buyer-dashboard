export type IdentifierCaptureSource = "camera" | "keyboard_wedge" | "manual" | "rfid_reader";
export type WeightCaptureSource = "bluetooth_scale" | "manual";
export type WeightUnit = "g" | "kg" | "oz" | "lb";

export type IdentifierCapture = {
  kind: "identifier";
  value: string;
  normalizedValue: string;
  source: IdentifierCaptureSource;
  symbology?: string;
  deviceId?: string;
  capturedAt: string;
};

export type WeightCapture = {
  kind: "weight";
  value: number;
  unit: WeightUnit;
  grams: number;
  source: WeightCaptureSource;
  deviceId?: string;
  stable?: boolean;
  capturedAt: string;
};

export type RfidCapture = {
  kind: "rfid";
  epc: string;
  normalizedEpc: string;
  airProtocol: "RAIN_UHF_EPC_GEN2";
  source: "rfid_reader";
  deviceId?: string;
  rssi?: number;
  antenna?: string;
  capturedAt: string;
};

export type HardwareCapture = IdentifierCapture | WeightCapture | RfidCapture;

function now(): string {
  return new Date().toISOString();
}

export function normalizeIdentifier(value: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return decodeURIComponent(raw).trim().toUpperCase();
  } catch {
    return raw.toUpperCase();
  }
}

export function createIdentifierCapture(
  value: string,
  source: IdentifierCaptureSource,
  options: { symbology?: string; deviceId?: string; capturedAt?: string } = {},
): IdentifierCapture {
  const clean = String(value || "").trim();
  if (!clean) throw new Error("Identifier capture cannot be empty.");
  return {
    kind: "identifier",
    value: clean,
    normalizedValue: normalizeIdentifier(clean),
    source,
    ...(options.symbology ? { symbology: options.symbology } : {}),
    ...(options.deviceId ? { deviceId: options.deviceId } : {}),
    capturedAt: options.capturedAt ?? now(),
  };
}

export function weightToGrams(value: number, unit: WeightUnit): number {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) throw new Error("Captured weight must be a non-negative finite number.");
  if (unit === "g") return amount;
  if (unit === "kg") return amount * 1000;
  if (unit === "oz") return amount * 28.349523125;
  return amount * 453.59237;
}

export function createWeightCapture(
  value: number,
  unit: WeightUnit,
  source: WeightCaptureSource,
  options: { deviceId?: string; stable?: boolean; capturedAt?: string } = {},
): WeightCapture {
  return {
    kind: "weight",
    value: Number(value),
    unit,
    grams: weightToGrams(value, unit),
    source,
    ...(options.deviceId ? { deviceId: options.deviceId } : {}),
    ...(typeof options.stable === "boolean" ? { stable: options.stable } : {}),
    capturedAt: options.capturedAt ?? now(),
  };
}

export function normalizeEpc(value: string): string {
  const raw = String(value || "").trim().replace(/^0x/i, "").replace(/[\s:]/g, "").toUpperCase();
  if (!raw || !/^[0-9A-F]+$/.test(raw) || raw.length % 2 !== 0) {
    throw new Error("RFID EPC must be an even-length hexadecimal value.");
  }
  return raw;
}

export function createRfidCapture(
  epc: string,
  options: { deviceId?: string; rssi?: number; antenna?: string; capturedAt?: string } = {},
): RfidCapture {
  const normalizedEpc = normalizeEpc(epc);
  return {
    kind: "rfid",
    epc: String(epc || "").trim(),
    normalizedEpc,
    airProtocol: "RAIN_UHF_EPC_GEN2",
    source: "rfid_reader",
    ...(options.deviceId ? { deviceId: options.deviceId } : {}),
    ...(Number.isFinite(options.rssi) ? { rssi: Number(options.rssi) } : {}),
    ...(options.antenna ? { antenna: options.antenna } : {}),
    capturedAt: options.capturedAt ?? now(),
  };
}

export function captureMatchesIdentifier(capture: IdentifierCapture, candidates: Array<string | null | undefined>): boolean {
  const needle = capture.normalizedValue;
  return Boolean(needle && candidates.some(candidate => normalizeIdentifier(String(candidate ?? "")) === needle));
}
