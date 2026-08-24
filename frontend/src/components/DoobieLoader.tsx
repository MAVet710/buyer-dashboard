import { useId } from "react";
import "../doobie-loader.css";

export type DoobieLoaderVariant =
  | "leaf-orbit"
  | "neural-leaf"
  | "trichome-pulse"
  | "jar-fill"
  | "grinder"
  | "preroll-ember"
  | "metrc-scan"
  | "compliance-seal"
  | "cultivation-grow"
  | "extraction-drop"
  | "package-lineage"
  | "inventory-stack"
  | "terpene-orbit"
  | "report-weave";

export const DOOBIE_LOADER_VARIANTS: readonly DoobieLoaderVariant[] = [
  "leaf-orbit",
  "neural-leaf",
  "trichome-pulse",
  "jar-fill",
  "grinder",
  "preroll-ember",
  "metrc-scan",
  "compliance-seal",
  "cultivation-grow",
  "extraction-drop",
  "package-lineage",
  "inventory-stack",
  "terpene-orbit",
  "report-weave",
] as const;

const VARIANT_LABELS: Record<DoobieLoaderVariant, string> = {
  "leaf-orbit": "Loading",
  "neural-leaf": "Doobie AI is thinking",
  "trichome-pulse": "Analyzing",
  "jar-fill": "Loading inventory",
  "grinder": "Processing",
  "preroll-ember": "Preparing",
  "metrc-scan": "Scanning METRC data",
  "compliance-seal": "Checking compliance",
  "cultivation-grow": "Loading cultivation data",
  "extraction-drop": "Processing extraction data",
  "package-lineage": "Tracing package lineage",
  "inventory-stack": "Counting inventory",
  "terpene-orbit": "Analyzing product data",
  "report-weave": "Generating report",
};

export interface DoobieLoaderProps {
  variant?: DoobieLoaderVariant;
  size?: number;
  label?: string | false;
  className?: string;
}

function Leaf({ className = "" }: { className?: string }) {
  return (
    <g className={className}>
      <path d="M50 23c-3 8-7 14-14 19 5-1 9-1 13 0-8 6-14 11-19 18 7-2 12-3 17-2-5 6-8 11-10 17 5-3 9-7 13-12 4 5 8 9 13 12-2-6-5-11-10-17 5-1 10 0 17 2-5-7-11-12-19-18 4-1 8-1 13 0-7-5-11-11-14-19-3 8-4 13-4 20-2-7-3-12-3-20-3 5-5 11-6 17-1-6-2-12-2-18Z" />
      <path className="dl-leaf-vein" d="M50 37v34M50 50l-12 10M50 55l12 8M50 45l-8-6M50 47l9-7" />
    </g>
  );
}

function SharedDefs({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}-amber`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ffd08a" />
        <stop offset="0.48" stopColor="#ff9a3c" />
        <stop offset="1" stopColor="#c96116" />
      </linearGradient>
      <linearGradient id={`${id}-silver`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.92" />
        <stop offset="1" stopColor="#ffffff" stopOpacity="0.24" />
      </linearGradient>
      <radialGradient id={`${id}-glow`}>
        <stop offset="0" stopColor="#ffb66e" stopOpacity="0.92" />
        <stop offset="0.45" stopColor="#ff9a3c" stopOpacity="0.35" />
        <stop offset="1" stopColor="#ff9a3c" stopOpacity="0" />
      </radialGradient>
      <filter id={`${id}-soft`} x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="2.6" />
      </filter>
      <filter id={`${id}-micro`} x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="1.1" />
      </filter>
    </defs>
  );
}

function LoaderArt({ variant, id }: { variant: DoobieLoaderVariant; id: string }) {
  const amber = `url(#${id}-amber)`;
  const silver = `url(#${id}-silver)`;
  const glow = `url(#${id}-glow)`;

  switch (variant) {
    case "leaf-orbit":
      return (
        <>
          <circle className="dl-ambient" cx="50" cy="50" r="26" fill={glow} />
          <g className="dl-orbit dl-orbit-slow">
            <circle className="dl-orbit-track" cx="50" cy="50" r="32" />
            <circle className="dl-orbit-dot" cx="50" cy="18" r="3.2" fill={amber} />
          </g>
          <Leaf className="dl-leaf dl-leaf-breathe" />
        </>
      );
    case "neural-leaf":
      return (
        <>
          <circle className="dl-ambient dl-ambient-pulse" cx="50" cy="50" r="28" fill={glow} />
          <Leaf className="dl-leaf dl-neural-leaf" />
          <g className="dl-neural-circuit">
            <path d="M50 41 39 49 34 61M50 47l11 7 6 11M50 54l-8 12M50 57l8 11" />
            {[[39,49],[34,61],[61,54],[67,65],[42,66],[58,68]].map(([cx, cy], index) => (
              <circle key={index} className={`dl-neural-node dl-delay-${index % 3}`} cx={cx} cy={cy} r="2" fill={amber} />
            ))}
          </g>
          <circle className="dl-neural-core" cx="50" cy="48" r="4.5" fill={amber} />
        </>
      );
    case "trichome-pulse":
      return (
        <>
          <circle className="dl-ambient dl-ambient-pulse" cx="50" cy="50" r="25" fill={glow} />
          <g className="dl-trichomes">
            {[[32,58,0],[43,44,1],[57,46,2],[68,59,0],[51,66,1],[36,68,2]].map(([x, y, delay], index) => (
              <g key={index} className={`dl-trichome dl-delay-${delay}`}>
                <path d={`M${x} ${y + 8} C${x - 1} ${y + 4}, ${x - 1} ${y + 2}, ${x} ${y}`} />
                <circle cx={x} cy={y} r="4.3" fill={index % 2 ? silver : amber} />
                <circle cx={x - 1.3} cy={y - 1.3} r="1.1" fill="#fff" opacity=".72" />
              </g>
            ))}
          </g>
        </>
      );
    case "jar-fill":
      return (
        <>
          <rect className="dl-jar-lid" x="33" y="20" width="34" height="9" rx="3" />
          <path className="dl-jar" d="M31 32h38l-2 41a7 7 0 0 1-7 6H40a7 7 0 0 1-7-6Z" />
          <path className="dl-jar-glass" d="M38 36h4v34" />
          <g className="dl-buds">
            {[[42,67,0],[51,70,1],[59,66,2],[47,59,2],[57,57,0],[50,50,1]].map(([x, y, delay], index) => (
              <g key={index} className={`dl-bud dl-delay-${delay}`} transform={`translate(${x} ${y})`}>
                <circle r="5" fill={amber} opacity=".88" />
                <circle cx="-2" cy="-1" r="2.2" fill="#fff" opacity=".18" />
              </g>
            ))}
          </g>
          <path className="dl-jar-highlight" d="M36 31h28" />
        </>
      );
    case "grinder":
      return (
        <>
          <circle className="dl-ambient" cx="50" cy="51" r="28" fill={glow} />
          <g className="dl-grinder-top"><rect x="28" y="27" width="44" height="18" rx="6" fill="none" /><path d="M33 32h34M34 38h32" /></g>
          <g className="dl-grinder-bottom"><path d="M29 49h42v16c0 6-5 10-11 10H40c-6 0-11-4-11-10Z" /><path d="M36 55h28" /></g>
          <g className="dl-grinder-particles"><circle cx="42" cy="50" r="2.2" fill={amber} /><circle cx="50" cy="53" r="1.7" fill={amber} /><circle cx="59" cy="49" r="2" fill={amber} /></g>
        </>
      );
    case "preroll-ember":
      return (
        <>
          <g className="dl-preroll"><path d="M26 58 65 39l9 7-41 20Z" fill="none" /><path d="m65 39 9 7 5-6-8-7Z" className="dl-filter-tip" /></g>
          <circle className="dl-ember-halo" cx="27" cy="58" r="8" fill={glow} />
          <circle className="dl-ember" cx="27" cy="58" r="3.8" fill={amber} />
          <g className="dl-smoke"><path d="M25 49c-6-7 3-10 0-16s5-7 3-13" /><path d="M31 48c6-5-2-8 2-13 3-4-1-7 1-11" /></g>
        </>
      );
    case "metrc-scan":
      return (
        <>
          <rect className="dl-tag" x="28" y="23" width="44" height="54" rx="7" />
          <path className="dl-tag-notch" d="M50 23v8" />
          <circle className="dl-tag-hole" cx="50" cy="31" r="3" />
          <path className="dl-tag-lines" d="M36 44h28M36 51h20M36 58h25M36 65h16" />
          <g className="dl-scan-beam"><rect x="24" y="39" width="52" height="5" rx="2.5" fill={glow} /><path d="M26 41.5h48" /></g>
          <g className="dl-scan-corners"><path d="M23 31v-6h6M77 31v-6h-6M23 69v6h6M77 69v6h-6" /></g>
        </>
      );
    case "compliance-seal":
      return (
        <>
          <circle className="dl-seal-ring" cx="50" cy="50" r="31" />
          <circle className="dl-seal-track" cx="50" cy="50" r="24" />
          <g className="dl-seal-leaf"><Leaf className="dl-leaf" /></g>
          <path className="dl-check" d="M38 51 47 60 64 40" />
          <g className="dl-seal-ticks">{[0,45,90,135,180,225,270,315].map((angle) => <line key={angle} x1="50" y1="14" x2="50" y2="18" transform={`rotate(${angle} 50 50)`} />)}</g>
        </>
      );
    case "cultivation-grow":
      return (
        <>
          <path className="dl-soil" d="M25 72c14-5 36-5 50 0" />
          <path className="dl-stem" d="M50 72V44" />
          <g className="dl-grow-leaf dl-grow-left"><path d="M49 57c-10-12-18-8-19-7 5 9 11 12 19 11Z" fill={amber} /></g>
          <g className="dl-grow-leaf dl-grow-right"><path d="M51 48c10-12 18-8 19-7-5 9-11 12-19 11Z" fill={amber} /></g>
          <g className="dl-grow-crown"><Leaf className="dl-leaf" /></g>
          <circle className="dl-sun" cx="50" cy="24" r="7" fill={glow} /><circle className="dl-sun-core" cx="50" cy="24" r="3" fill={amber} />
        </>
      );
    case "extraction-drop":
      return (
        <>
          <path className="dl-drop-shell" d="M50 20c9 14 20 25 20 39a20 20 0 0 1-40 0c0-14 11-25 20-39Z" />
          <path className="dl-drop-fill" d="M34 59c8 4 24 4 32 0v7c-3 9-9 13-16 13s-13-4-16-13Z" fill={amber} />
          <g className="dl-bubbles"><circle cx="43" cy="59" r="2.5" fill="#fff" opacity=".55" /><circle cx="56" cy="64" r="3" fill="#fff" opacity=".34" /><circle cx="50" cy="53" r="1.8" fill="#fff" opacity=".6" /></g>
          <path className="dl-drop-shine" d="M42 37c-5 7-7 12-7 17" />
        </>
      );
    case "package-lineage":
      return (
        <>
          <g className="dl-lineage-lines"><path d="M26 50h18M56 50h18M50 44V28M50 56v16" /><path d="M44 47 35 34M56 47l9-13M44 53 35 66M56 53l9 13" /></g>
          {[[50,50,0,5.4],[50,25,1,4],[50,75,2,4],[31,31,2,3.7],[69,31,0,3.7],[31,69,1,3.7],[69,69,2,3.7],[23,50,1,3.5],[77,50,0,3.5]].map(([x,y,delay,r], index) => <circle key={index} className={`dl-lineage-node dl-delay-${delay}`} cx={x} cy={y} r={r} fill={index === 0 ? amber : silver} />)}
          <circle className="dl-lineage-pulse" cx="50" cy="50" r="10" fill="none" />
        </>
      );
    case "inventory-stack":
      return (
        <>
          <g className="dl-stack dl-stack-1"><rect x="31" y="58" width="38" height="16" rx="4" /></g>
          <g className="dl-stack dl-stack-2"><rect x="35" y="42" width="30" height="14" rx="4" /></g>
          <g className="dl-stack dl-stack-3"><rect x="39" y="28" width="22" height="12" rx="4" /></g>
          <g className="dl-stack-bud"><Leaf className="dl-leaf" /></g>
          <path className="dl-count-tick" d="M71 37l5 5 8-10" />
        </>
      );
    case "terpene-orbit":
      return (
        <>
          <circle className="dl-terp-core" cx="50" cy="50" r="9" fill={amber} /><circle className="dl-terp-core-glow" cx="50" cy="50" r="18" fill={glow} />
          {[0,60,120].map((angle, index) => <g key={angle} className={`dl-terp-orbit dl-terp-orbit-${index}`} transform={`rotate(${angle} 50 50)`}><ellipse cx="50" cy="50" rx="31" ry="13" /><circle cx="81" cy="50" r="3.4" fill={index % 2 ? silver : amber} /></g>)}
          <circle className="dl-terp-highlight" cx="47" cy="47" r="2" fill="#fff" opacity=".72" />
        </>
      );
    case "report-weave":
      return (
        <>
          <rect className="dl-report-page" x="29" y="20" width="42" height="60" rx="7" /><path className="dl-report-fold" d="M58 20v13h13" />
          <g className="dl-report-lines"><path d="M37 42h25M37 49h18M37 63h25" /></g>
          <g className="dl-report-bars"><rect x="37" y="57" width="5" height="12" rx="2" fill={amber} /><rect x="46" y="53" width="5" height="16" rx="2" fill={amber} /><rect x="55" y="48" width="5" height="21" rx="2" fill={amber} /></g>
          <g className="dl-report-thread"><path d="M24 35c12 4 16 8 25 14 8 6 15 10 27 12" /><circle cx="24" cy="35" r="2.4" fill={amber} /></g>
        </>
      );
  }
}

export function DoobieLoader({ variant = "leaf-orbit", size = 88, label, className = "" }: DoobieLoaderProps) {
  const rawId = useId();
  const id = `doobie-loader-${rawId.replace(/:/g, "")}`;
  const resolvedLabel = label === false ? null : label ?? VARIANT_LABELS[variant];

  return (
    <span className={`doobie-loader doobie-loader--${variant} ${className}`.trim()} role="status" aria-live="polite" aria-label={resolvedLabel ?? VARIANT_LABELS[variant]}>
      <svg className="doobie-loader__art" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        <SharedDefs id={id} />
        <LoaderArt variant={variant} id={id} />
      </svg>
      {resolvedLabel ? <span className="doobie-loader__label">{resolvedLabel}</span> : null}
    </span>
  );
}
