import { createWeightCapture, type WeightCapture } from "./hardwareCapture";

// Bluetooth SIG Weight Scale Service / Weight Measurement characteristic.
// This adapter deliberately supports the published standard only. Vendor-
// specific industrial-scale protocols belong in separate adapters.
export const WEIGHT_SCALE_SERVICE = 0x181d;
export const WEIGHT_MEASUREMENT_CHARACTERISTIC = 0x2a9d;

type EventTargetLike = {
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
};

type CharacteristicLike = EventTargetLike & {
  value?: DataView | null;
  startNotifications: () => Promise<unknown>;
  stopNotifications?: () => Promise<unknown>;
};

type ServiceLike = {
  getCharacteristic: (characteristic: number) => Promise<CharacteristicLike>;
};

type GattServerLike = {
  connected?: boolean;
  getPrimaryService: (service: number) => Promise<ServiceLike>;
  disconnect?: () => void;
};

type BluetoothDeviceLike = {
  id?: string;
  name?: string | null;
  gatt?: {
    connect: () => Promise<GattServerLike>;
    connected?: boolean;
    disconnect?: () => void;
  };
};

type BluetoothLike = {
  requestDevice: (options: { filters: Array<{ services: number[] }>; optionalServices?: number[] }) => Promise<BluetoothDeviceLike>;
};

function bluetooth(): BluetoothLike | undefined {
  return (navigator as Navigator & { bluetooth?: BluetoothLike }).bluetooth;
}

export function supportsStandardBluetoothWeightScale(): boolean {
  return Boolean(typeof navigator !== "undefined" && bluetooth());
}

export function decodeWeightMeasurement(value: DataView, deviceId = ""): WeightCapture {
  if (value.byteLength < 3) throw new Error("Bluetooth weight measurement was incomplete.");
  const flags = value.getUint8(0);
  const imperial = Boolean(flags & 0x01);
  const rawWeight = value.getUint16(1, true);
  // Bluetooth SIG Weight Scale Service: SI resolution is 0.005 kg;
  // imperial resolution is 0.01 lb.
  return imperial
    ? createWeightCapture(rawWeight * 0.01, "lb", "bluetooth_scale", { deviceId })
    : createWeightCapture(rawWeight * 0.005, "kg", "bluetooth_scale", { deviceId });
}

export class BluetoothWeightScaleAdapter {
  private device: BluetoothDeviceLike | null = null;
  private characteristic: CharacteristicLike | null = null;
  private listener: EventListener | null = null;

  get connected(): boolean {
    return Boolean(this.device?.gatt?.connected);
  }

  get deviceId(): string {
    return this.device?.id ?? "";
  }

  get deviceName(): string {
    return this.device?.name?.trim() || "Bluetooth weight scale";
  }

  async connect(onMeasurement: (capture: WeightCapture) => void): Promise<void> {
    const api = bluetooth();
    if (!api) throw new Error("Web Bluetooth is unavailable in this browser. Use manual weight entry or a supported bridge device.");
    await this.disconnect();
    const device = await api.requestDevice({
      filters: [{ services: [WEIGHT_SCALE_SERVICE] }],
      optionalServices: [WEIGHT_SCALE_SERVICE],
    });
    if (!device.gatt) throw new Error("The selected Bluetooth device does not expose a GATT server.");
    const server = await device.gatt.connect();
    const service = await server.getPrimaryService(WEIGHT_SCALE_SERVICE);
    const characteristic = await service.getCharacteristic(WEIGHT_MEASUREMENT_CHARACTERISTIC);
    const listener: EventListener = event => {
      const target = event.target as CharacteristicLike | null;
      if (!target?.value) return;
      onMeasurement(decodeWeightMeasurement(target.value, device.id ?? ""));
    };
    characteristic.addEventListener("characteristicvaluechanged", listener);
    await characteristic.startNotifications();
    this.device = device;
    this.characteristic = characteristic;
    this.listener = listener;
  }

  async disconnect(): Promise<void> {
    if (this.characteristic && this.listener) {
      this.characteristic.removeEventListener("characteristicvaluechanged", this.listener);
      try {
        await this.characteristic.stopNotifications?.();
      } catch {
        // A device that already disconnected needs no further cleanup.
      }
    }
    try {
      this.device?.gatt?.disconnect?.();
    } finally {
      this.characteristic = null;
      this.listener = null;
      this.device = null;
    }
  }
}
