import { describe, expect, it } from "vitest";
import { captureMatchesIdentifier, createIdentifierCapture, createRfidCapture, createWeightCapture, normalizeEpc, weightToGrams } from "./hardwareCapture";
import { decodeWeightMeasurement } from "./bluetoothWeightScale";
import { KeyboardWedgeRfidReader, supportsInventorySweep, supportsSeekAndFind } from "./rfidReaders";

describe("hardware capture normalization", () => {
  it("normalizes camera and scanner identifiers without changing the raw captured value", () => {
    const capture = createIdentifierCapture(" pkg%2D123 ", "camera", { symbology: "qr_code", capturedAt: "2026-08-30T00:00:00.000Z" });
    expect(capture.value).toBe("pkg%2D123");
    expect(capture.normalizedValue).toBe("PKG-123");
    expect(capture.symbology).toBe("qr_code");
    expect(captureMatchesIdentifier(capture, ["other", "pkg-123"])).toBe(true);
  });

  it("normalizes every supported weight unit to grams", () => {
    expect(weightToGrams(1, "kg")).toBe(1000);
    expect(weightToGrams(1, "lb")).toBeCloseTo(453.59237, 6);
    expect(weightToGrams(1, "oz")).toBeCloseTo(28.349523125, 6);
    const capture = createWeightCapture(2.5, "kg", "manual", { capturedAt: "2026-08-30T00:00:00.000Z" });
    expect(capture.grams).toBe(2500);
  });

  it("decodes the Bluetooth SIG Weight Measurement characteristic in SI and imperial units", () => {
    const si = new DataView(new ArrayBuffer(3));
    si.setUint8(0, 0);
    si.setUint16(1, 14000, true); // 70.000 kg at 0.005 kg resolution
    const siCapture = decodeWeightMeasurement(si, "scale-1");
    expect(siCapture.value).toBe(70);
    expect(siCapture.unit).toBe("kg");
    expect(siCapture.grams).toBe(70000);

    const imperial = new DataView(new ArrayBuffer(3));
    imperial.setUint8(0, 0x01);
    imperial.setUint16(1, 15000, true); // 150.00 lb at 0.01 lb resolution
    const imperialCapture = decodeWeightMeasurement(imperial, "scale-2");
    expect(imperialCapture.value).toBe(150);
    expect(imperialCapture.unit).toBe("lb");
    expect(imperialCapture.grams).toBeCloseTo(68038.8555, 3);
  });

  it("normalizes RAIN/UHF EPC values while preserving explicit capabilities", async () => {
    expect(normalizeEpc("0x30 08:33 B2 DD D9 01 40 00 00 00 01")).toBe("300833B2DDD9014000000001");
    const capture = createRfidCapture("300833B2DDD9014000000001", { rssi: -48 });
    expect(capture.airProtocol).toBe("RAIN_UHF_EPC_GEN2");
    expect(capture.rssi).toBe(-48);

    const wedge = new KeyboardWedgeRfidReader();
    expect(supportsInventorySweep(wedge)).toBe(false);
    expect(supportsSeekAndFind(wedge)).toBe(false);
    await wedge.connect();
    expect(wedge.capture("300833B2DDD9014000000001").normalizedEpc).toBe("300833B2DDD9014000000001");
  });
});
