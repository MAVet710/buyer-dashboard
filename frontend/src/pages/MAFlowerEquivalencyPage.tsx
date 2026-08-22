import { useState } from "react";
import { apiPost } from "../lib/api";

type Result = { per_unit: number; package_total: number; per_unit_display: string; package_total_display: string; flower_weight_per_joint?: number | null; infusion_equivalency_per_joint?: number | null };
type Mode = "concentrate_vape" | "edible" | "infused_preroll";

export function MAFlowerEquivalencyPage() {
  const [mode, setMode] = useState<Mode>("concentrate_vape");
  const [quantity, setQuantity] = useState(1);
  const [grams, setGrams] = useState(1);
  const [thc, setThc] = useState(100);
  const [finished, setFinished] = useState(1);
  const [infusion, setInfusion] = useState(.1);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const calculate = async () => {
    setError("");
    try {
      setResult(await apiPost<Result>("/api/v1/parity-tools/ma-flower-equivalency", {
        mode, quantity,
        grams: mode === "concentrate_vape" ? grams : null,
        active_thc_mg: mode === "edible" ? thc : null,
        finished_grams_per_joint: mode === "infused_preroll" ? finished : null,
        infusion_grams_per_joint: mode === "infused_preroll" ? infusion : null,
      }));
    } catch (err) { setError(err instanceof Error ? err.message : "Calculation failed."); }
  };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Retail Operations</div><h1>MA Flower Equivalency</h1><p>Same Buyer Dash calculator, moved to the durable web workspace. Intermediate values remain full precision and round only for display.</p></div></div>
    <section className="inventory-panel form-panel">
      <div className="form-grid">
        <label>Product type<select value={mode} onChange={event => { setMode(event.target.value as Mode); setResult(null); }}><option value="concentrate_vape">Concentrate / Vape</option><option value="edible">Edible / Beverage</option><option value="infused_preroll">Infused Pre-Roll</option></select></label>
        <label>Package quantity<input type="number" min="1" step="1" value={quantity} onChange={event => setQuantity(Math.max(1, Number(event.target.value) || 1))} /></label>
        {mode === "concentrate_vape" ? <label>Grams per unit<input type="number" min="0" step="0.001" value={grams} onChange={event => setGrams(Number(event.target.value))} /></label> : null}
        {mode === "edible" ? <label>Active THC mg per unit<input type="number" min="0" step="0.1" value={thc} onChange={event => setThc(Number(event.target.value))} /></label> : null}
        {mode === "infused_preroll" ? <><label>Finished grams per joint<input type="number" min="0" step="0.001" value={finished} onChange={event => setFinished(Number(event.target.value))} /></label><label>Infusion grams per joint<input type="number" min="0" step="0.001" value={infusion} onChange={event => setInfusion(Number(event.target.value))} /></label></> : null}
      </div>
      <div className="form-actions"><button className="primary" onClick={calculate}>Calculate equivalency</button></div>
      {error ? <div className="form-error">{error}</div> : null}
    </section>
    {result ? <div className="metric-grid four"><div className="metric"><span>Per unit</span><strong>{result.per_unit_display} g</strong><small>Flower equivalency</small></div><div className="metric"><span>Package total</span><strong>{result.package_total_display} g</strong><small>{quantity} unit{quantity === 1 ? "" : "s"}</small></div>{result.flower_weight_per_joint != null ? <div className="metric"><span>Flower per joint</span><strong>{result.flower_weight_per_joint.toFixed(4)} g</strong><small>Finished minus infusion</small></div> : null}{result.infusion_equivalency_per_joint != null ? <div className="metric"><span>Infusion equivalent</span><strong>{result.infusion_equivalency_per_joint.toFixed(4)} g</strong><small>Per joint</small></div> : null}</div> : null}
    <section className="inventory-panel"><h3>Calculator basis</h3><p className="muted">Concentrate/vape uses grams × 5.6. Edible/beverage uses active THC mg × 0.056. Infused pre-roll combines flower weight with the concentrate-equivalent infusion amount. Verify current Massachusetts requirements before using the result operationally.</p></section>
  </div>;
}
