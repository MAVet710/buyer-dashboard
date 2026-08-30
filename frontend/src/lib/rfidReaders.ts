import { createRfidCapture, type RfidCapture } from "./hardwareCapture";

export type RfidReaderCapability = "single_read" | "inventory" | "rssi" | "locate";

export type RfidLocateObservation = RfidCapture & {
  rssi: number;
};

export interface RfidReaderAdapter {
  readonly id: string;
  readonly label: string;
  readonly transport: string;
  readonly capabilities: ReadonlySet<RfidReaderCapability>;
  readonly connected: boolean;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  startInventory?(onTag: (capture: RfidCapture) => void): Promise<void>;
  stopInventory?(): Promise<void>;
  locate?(epc: string, onObservation: (capture: RfidLocateObservation) => void): Promise<void>;
  stopLocate?(): Promise<void>;
}

const readers = new Map<string, () => RfidReaderAdapter>();

export function registerRfidReaderAdapter(id: string, factory: () => RfidReaderAdapter): void {
  const key = String(id || "").trim();
  if (!key) throw new Error("RFID adapter id is required.");
  readers.set(key, factory);
}

export function registeredRfidReaderIds(): string[] {
  return [...readers.keys()].sort();
}

export function createRegisteredRfidReader(id: string): RfidReaderAdapter {
  const factory = readers.get(id);
  if (!factory) throw new Error(`RFID reader adapter ${id} is not registered.`);
  return factory();
}

export function supportsSeekAndFind(reader: Pick<RfidReaderAdapter, "capabilities">): boolean {
  return reader.capabilities.has("locate") && reader.capabilities.has("rssi");
}

export function supportsInventorySweep(reader: Pick<RfidReaderAdapter, "capabilities">): boolean {
  return reader.capabilities.has("inventory");
}

/**
 * Adapter for RAIN/UHF readers configured by their manufacturer to emit EPCs
 * as keyboard input. This is useful for inexpensive validation because HID
 * keyboard-wedge mode is broadly interoperable, but it intentionally does not
 * claim inventory sweeps, RSSI, or Seek & Find support.
 */
export class KeyboardWedgeRfidReader implements RfidReaderAdapter {
  readonly id: string;
  readonly label: string;
  readonly transport = "keyboard_wedge";
  readonly capabilities = new Set<RfidReaderCapability>(["single_read"]);
  connected = false;

  constructor(options: { id?: string; label?: string } = {}) {
    this.id = options.id ?? "keyboard-wedge-rfid";
    this.label = options.label ?? "RFID keyboard-wedge reader";
  }

  async connect(): Promise<void> {
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }

  capture(epc: string): RfidCapture {
    if (!this.connected) throw new Error("Connect the RFID reader before capturing a tag.");
    return createRfidCapture(epc, { deviceId: this.id });
  }
}

// There is no Bluetooth SIG GATT profile for UHF/RAIN RFID reader inventory,
// RSSI, or Locate operations. Vendor/device-family adapters must therefore
// implement this contract using their documented protocol rather than a fake
// universal UUID. A reader may only advertise `locate` when it returns live
// signal-strength observations suitable for Seek & Find.
