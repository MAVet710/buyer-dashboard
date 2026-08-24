import { useMemo } from "react";
import "./package-qr-code.css";

type QrInstance = {
  addData: (value: string, mode?: string) => void;
  make: () => void;
  createSvgTag: (cellSize?: number, margin?: number) => string;
};
type QrFactory = (typeNumber: number, errorCorrectionLevel: string) => QrInstance;

function qrFactory(): QrFactory | undefined {
  return (window as unknown as { qrcode?: QrFactory }).qrcode;
}

export function PackageQrCode({ value }: { value: string }) {
  const clean = String(value || "").trim();
  const svg = useMemo(() => {
    if (!clean) return "";
    const factory = qrFactory();
    if (!factory) return "";
    try {
      const qr = factory(0, "M");
      qr.addData(clean, "Byte");
      qr.make();
      return qr.createSvgTag(3, 1);
    } catch {
      return "";
    }
  }, [clean]);

  if (!clean) return <div className="inventory-label-qr unavailable" aria-label="No external package ID available">No package ID</div>;
  if (!svg) return <div className="inventory-label-qr unavailable" aria-label={`QR unavailable for external package ID ${clean}`}><strong>QR unavailable</strong><span>{clean}</span></div>;
  return <div className="inventory-label-qr" aria-label={`QR code for external package ID ${clean}`} title={`External package ID: ${clean}`} dangerouslySetInnerHTML={{ __html: svg }}/>;
}
