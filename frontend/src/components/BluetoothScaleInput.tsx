import { useEffect, useRef, useState } from "react";
import { BluetoothWeightScaleAdapter, supportsStandardBluetoothWeightScale } from "../lib/bluetoothWeightScale";
import type { WeightCapture } from "../lib/hardwareCapture";

export function BluetoothScaleInput({ onWeight, disabled = false }: { onWeight: (capture: WeightCapture) => void; disabled?: boolean }) {
  const adapter = useRef(new BluetoothWeightScaleAdapter());
  const [connected, setConnected] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [latest, setLatest] = useState<WeightCapture | null>(null);
  const [error, setError] = useState("");
  const supported = supportsStandardBluetoothWeightScale();

  useEffect(() => () => { void adapter.current.disconnect(); }, []);

  async function connect() {
    setError("");
    try {
      await adapter.current.connect(capture => {
        setLatest(capture);
        onWeight(capture);
      });
      setConnected(true);
      setDeviceName(adapter.current.deviceName);
    } catch (exc) {
      setConnected(false);
      setError(exc instanceof Error ? exc.message : "The Bluetooth scale could not connect.");
    }
  }

  async function disconnect() {
    await adapter.current.disconnect();
    setConnected(false);
    setDeviceName("");
  }

  return <section className="inventory-panel hardware-scale-input" aria-label="Bluetooth weight scale">
    <div className="section-heading"><div><div className="eyebrow">WEIGHT CAPTURE</div><h4>Bluetooth scale</h4><p className="source-caption">Uses the Bluetooth SIG Weight Scale Service when the browser and scale both support it. Vendor-specific protocols are not guessed.</p></div><span className="read-only-chip">Capture only</span></div>
    {!supported ? <div className="info-banner">Standard Web Bluetooth scale access is unavailable in this browser. Manual weight entry remains available.</div> : null}
    <div className="heading-actions">
      {!connected ? <button className="secondary" type="button" disabled={disabled || !supported} onClick={connect}>Connect standard scale</button> : <button className="secondary" type="button" onClick={disconnect}>Disconnect scale</button>}
      {connected ? <span className="access-badge">{deviceName || "Scale connected"}</span> : null}
    </div>
    {latest ? <div className="success-banner">Captured <strong>{latest.value.toLocaleString(undefined,{maximumFractionDigits:3})} {latest.unit}</strong> · {latest.grams.toLocaleString(undefined,{maximumFractionDigits:2})} g normalized.</div> : null}
    {error ? <div className="warning-banner">{error}</div> : null}
  </section>;
}
