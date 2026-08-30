import { useState } from "react";
import { createIdentifierCapture, type IdentifierCapture } from "../lib/hardwareCapture";
import { CameraScanner } from "./CameraScanner";

export function IdentifierCaptureInput({
  onCapture,
  disabled = false,
  label = "Scan or enter item code",
  placeholder = "Package, lot, UPC, SKU, or barcode",
  camera = true,
}: {
  onCapture: (capture: IdentifierCapture) => void;
  disabled?: boolean;
  label?: string;
  placeholder?: string;
  camera?: boolean;
}) {
  const [value, setValue] = useState("");

  function emit(source: "keyboard_wedge" | "manual") {
    const clean = value.trim();
    if (!clean || disabled) return;
    onCapture(createIdentifierCapture(clean, source));
    setValue("");
  }

  return <section className="hardware-identifier-input">
    {camera ? <CameraScanner disabled={disabled} onCode={()=>{}} onCapture={onCapture}/> : null}
    <details className="streamlit-expander">
      <summary>Bluetooth / USB scanner or typed code</summary>
      <div className="streamlit-expander-body">
        <label>{label}<input value={value} disabled={disabled} autoComplete="off" inputMode="text" placeholder={placeholder} onChange={event=>setValue(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();emit("keyboard_wedge")}}}/></label>
        <div className="heading-actions">
          <button className="primary" type="button" disabled={disabled||!value.trim()} onClick={()=>emit("manual")}>Use code</button>
        </div>
        <p className="source-caption">Press Enter from a keyboard-wedge scanner, type a code manually, or use the camera. All three produce the same normalized identifier event.</p>
      </div>
    </details>
  </section>;
}
