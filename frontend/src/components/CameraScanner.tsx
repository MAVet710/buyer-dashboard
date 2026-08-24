import { useCallback, useEffect, useRef, useState } from "react";
import "./camera-scanner.css";

type DetectedBarcode = { rawValue?: string };
type BarcodeDetectorInstance = { detect: (source: HTMLVideoElement) => Promise<DetectedBarcode[]> };
type BarcodeDetectorConstructor = new (options?: { formats?: string[] }) => BarcodeDetectorInstance;

type Props = {
  disabled?: boolean;
  onCode: (code: string) => void;
};

const FORMATS = ["qr_code", "code_128", "code_39", "ean_13", "upc_a"];
const RESCAN_GUARD_MS = 8000;

function detectorConstructor(): BarcodeDetectorConstructor | undefined {
  return (window as unknown as { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;
}

export function CameraScanner({ disabled = false, onCode }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const lastScanRef = useRef<{ code: string; at: number } | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Camera is off");

  const stop = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setActive(false);
    setStatus("Camera is off");
  }, []);

  useEffect(() => stop, [stop]);

  useEffect(() => {
    if (!active || !videoRef.current) return;
    const Detector = detectorConstructor();
    if (!Detector) {
      setError("The camera opened, but the QR/barcode decoder did not load. Refresh the page and try again, or use the scanner/typed-code field below.");
      return;
    }

    let cancelled = false;
    let detector: BarcodeDetectorInstance;
    try {
      detector = new Detector({ formats: FORMATS });
    } catch {
      try {
        detector = new Detector({ formats: ["qr_code"] });
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "The QR/barcode decoder could not start.");
        return;
      }
    }

    const schedule = (delay = 250) => {
      if (!cancelled) timerRef.current = window.setTimeout(scan, delay);
    };
    const scan = async () => {
      if (cancelled) return;
      if (disabled || !videoRef.current || videoRef.current.readyState < 2) {
        schedule();
        return;
      }
      try {
        const found = await detector.detect(videoRef.current);
        const code = String(found[0]?.rawValue ?? "").trim();
        if (code) {
          const now = Date.now();
          const previous = lastScanRef.current;
          if (!previous || previous.code !== code || now - previous.at > RESCAN_GUARD_MS) {
            lastScanRef.current = { code, at: now };
            setError("");
            setStatus(`Scanned ${code}`);
            onCode(code);
          }
        }
      } catch (exc) {
        // A bad frame is normal while a camera is moving. Keep the scanner alive.
        if (exc instanceof Error && /permission|notallowed|security/i.test(exc.message)) setError(exc.message);
      }
      schedule(350);
    };

    setStatus("Camera ready — point it at a QR code or barcode");
    scan();
    return () => {
      cancelled = true;
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [active, disabled, onCode]);

  async function start() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser cannot open a camera. Use a Bluetooth/USB scanner or the typed-code field below.");
      return;
    }
    if (!detectorConstructor()) {
      setError("The QR/barcode decoder is still loading. Refresh the page if this continues, or use the scanner/typed-code field below.");
      return;
    }
    try {
      stop();
      setStatus("Opening rear camera…");
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      streamRef.current = media;
      if (videoRef.current) {
        videoRef.current.srcObject = media;
        await videoRef.current.play();
      }
      setActive(true);
      setStatus("Camera ready — point it at a QR code or barcode");
    } catch (exc) {
      setStatus("Camera is off");
      setError(exc instanceof Error ? exc.message : "Camera access is unavailable.");
    }
  }

  return <section className={`camera-scanner-card ${active ? "is-active" : ""}`} aria-label="Camera inventory scanner">
    <div className="camera-scanner-heading">
      <div>
        <span className="camera-scanner-kicker">Live inventory scanner</span>
        <strong>{active ? "Camera active" : "Use this phone’s camera"}</strong>
      </div>
      <span className={`camera-scanner-status ${active ? "is-live" : ""}`}>{active ? "LIVE" : "READY"}</span>
    </div>

    <div className={`camera-scanner-viewport ${active ? "is-active" : ""}`}>
      <video ref={videoRef} muted playsInline aria-label="Rear camera preview" />
      {active ? <div className="camera-scan-frame" aria-hidden="true"><i/><i/><i/><i/></div> : <div className="camera-scanner-placeholder"><span>QR</span><p>Scan package IDs, UPCs, SKUs, lots, and supported barcodes without leaving the audit.</p></div>}
    </div>

    <div className="camera-scanner-actions">
      {!active ? <button className="primary" type="button" onClick={start}>Open camera scanner</button> : <button className="secondary" type="button" onClick={stop}>Stop camera</button>}
      <span>{disabled ? "Checking scanned item…" : status}</span>
    </div>
    {error ? <div className="warning-banner">{error}</div> : null}
  </section>;
}
