import { useMemo, useState } from "react";
import { DOOBIE_LOADER_VARIANTS, DoobieLoader, type DoobieLoaderVariant } from "../components/DoobieLoader";

const META: Record<DoobieLoaderVariant, { name: string; use: string }> = {
  "leaf-orbit": { name: "Leaf Orbit", use: "Universal workspace loading" },
  "neural-leaf": { name: "Neural Leaf", use: "Doobie AI thinking and agent work" },
  "trichome-pulse": { name: "Trichome Pulse", use: "Analysis and quality checks" },
  "jar-fill": { name: "Jar Fill", use: "Inventory imports and receiving" },
  "grinder": { name: "Precision Grinder", use: "Data processing and transformations" },
  "preroll-ember": { name: "Ember Draw", use: "Preparing, staging, or publishing" },
  "metrc-scan": { name: "METRC Scan", use: "Traceability and package scanning" },
  "compliance-seal": { name: "Compliance Seal", use: "Validation and compliance review" },
  "cultivation-grow": { name: "Cultivation Grow", use: "Plant and cultivation data" },
  "extraction-drop": { name: "Extraction Drop", use: "Extraction and lab processing" },
  "package-lineage": { name: "Package Lineage", use: "Genealogy and traceability lookup" },
  "inventory-stack": { name: "Inventory Stack", use: "Counts, reconciliation, and audits" },
  "terpene-orbit": { name: "Terpene Orbit", use: "Product intelligence and composition" },
  "report-weave": { name: "Report Weave", use: "Reports, exports, and analytics" },
};

export function DoobieMotionLabPage() {
  const [size, setSize] = useState(96);
  const sizeLabel = useMemo(() => `${size}px`, [size]);

  return (
    <section className="doobie-motion-lab">
      <header className="doobie-motion-lab__header">
        <div>
          <p className="eyebrow">DoobieLogic Motion System</p>
          <h1>Loader Pack</h1>
          <p>Fourteen cannabis-native microanimations designed for the DoobieLogic command-center UI.</p>
        </div>
        <label className="doobie-motion-lab__size">
          <span>Preview size</span>
          <input aria-label="Loader preview size" type="range" min="56" max="144" step="8" value={size} onChange={(event) => setSize(Number(event.target.value))} />
          <strong>{sizeLabel}</strong>
        </label>
      </header>
      <div className="doobie-motion-lab__grid">
        {DOOBIE_LOADER_VARIANTS.map((variant, index) => (
          <article className="doobie-motion-card" key={variant}>
            <div className="doobie-motion-card__number">{String(index + 1).padStart(2, "0")}</div>
            <div className="doobie-motion-card__stage"><DoobieLoader variant={variant} size={size} label={false} /></div>
            <div className="doobie-motion-card__copy">
              <h2>{META[variant].name}</h2>
              <p>{META[variant].use}</p>
              <code>{variant}</code>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
