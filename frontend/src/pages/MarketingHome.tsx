import {
  ArrowRight,
  BarChart3,
  Boxes,
  CircleCheck,
  ClipboardCheck,
  Factory,
  FileCheck2,
  FlaskConical,
  Gauge,
  LockKeyhole,
  PackageCheck,
  ShieldCheck,
  ShoppingCart,
  Warehouse,
  Workflow,
} from "lucide-react";
import { APP_URL, BRAND_IMAGE_URL } from "../lib/brand";

const modules = [
  [ShoppingCart, "Buying"],
  [Warehouse, "Inventory"],
  [PackageCheck, "Receiving"],
  [ClipboardCheck, "Audits"],
  [FlaskConical, "Extraction"],
  [Factory, "Production"],
  [Workflow, "METRC"],
  [ShieldCheck, "Compliance"],
] as const;

const featureCards = [
  {
    icon: FlaskConical,
    title: "Extraction Command Center",
    body: "Plan, execute, and monitor extraction runs with inputs, outputs, yields, costs, stages, and operator notes in one workspace.",
  },
  {
    icon: Workflow,
    title: "METRC Integration",
    body: "Keep packages, manifests, transfers, and operational records aligned with state traceability workflows and facility context.",
  },
  {
    icon: Warehouse,
    title: "Inventory & Receiving",
    body: "Track lot-level inventory, receiving, focused counts, package IDs, and facility-specific stock without spreadsheet drift.",
  },
  {
    icon: Factory,
    title: "Production & QA",
    body: "Manage production, packaging, materials, outputs, quality checks, and costing from source material through finished goods.",
  },
  {
    icon: FileCheck2,
    title: "Compliance Evidence & Reporting",
    body: "Preserve source context, user actions, audit evidence, reports, and operational history so the work stays inspection-ready.",
  },
];

const workflow = [
  ["01", "Connect the operation", "Start with facilities, users, roles, licenses, and the operational data your team already works from."],
  ["02", "See what needs attention", "Surface inventory pressure, purchasing needs, active runs, holds, receiving work, and compliance exceptions."],
  ["03", "Act from the same workspace", "Receive, count, buy, produce, extract, investigate, report, and document without bouncing between disconnected systems."],
  ["04", "Keep the audit trail", "Preserve source context, operational history, permissions, facility boundaries, and the evidence behind every decision."],
];

export function MarketingHome() {
  return (
    <div className="marketing-page">
      <header className="marketing-nav-wrap">
        <nav className="marketing-nav" aria-label="Public navigation">
          <a className="marketing-brand" href="#top" aria-label="DoobieLogic home">
            <img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" />
            <span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span>
          </a>

          <div className="marketing-nav-links">
            <a href="#platform">Platform</a>
            <a href="#extraction">Extraction</a>
            <a href="#compliance">Compliance</a>
            <a href="#workflow">How it works</a>
          </div>

          <div className="marketing-nav-actions">
            <a className="marketing-nav-login" href={APP_URL}>Log In</a>
            <a className="marketing-nav-primary" href={APP_URL}>Open DoobieLogic</a>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="marketing-hero">
          <div className="marketing-hero-copy">
            <div className="marketing-eyebrow">Cannabis operations intelligence + compliance</div>
            <h1>
              One operating system for <span>buying, inventory, extraction, production,</span> and METRC-ready compliance.
            </h1>
            <p>
              DoobieLogic connects purchasing, receiving, inventory, audits, production, extraction,
              QA, reporting, and compliance in one secure workspace built for cannabis operators.
            </p>

            <div className="marketing-cta-row">
              <a className="marketing-primary" href={APP_URL}>Open DoobieLogic <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">Explore the platform</a>
            </div>

            <div className="marketing-proof-line">
              <span><CircleCheck size={16} /> Facility-aware</span>
              <span><LockKeyhole size={16} /> Permission-aware</span>
              <span><ShieldCheck size={16} /> Audit-ready</span>
            </div>
          </div>

          <div className="marketing-product-frame" aria-label="DoobieLogic operations dashboard preview">
            <aside className="marketing-product-sidebar">
              <div className="marketing-mini-brand">
                <img src={BRAND_IMAGE_URL} alt="" />
                <span className="marketing-mini-wordmark"><strong>Doobie</strong><em>Logic</em></span>
              </div>
              {['Home','Inventory','Purchasing','Extraction','Production','Compliance','METRC','Reports'].map((item, index) => (
                <div key={item} className={`marketing-product-nav-item ${index === 0 ? "active" : ""}`}>{item}</div>
              ))}
              <div className="marketing-user-card">
                <span>DL</span>
                <div><strong>Operations Admin</strong><small>Sandbox Facility</small></div>
              </div>
            </aside>

            <div className="marketing-product-content">
              <div className="marketing-preview-heading">
                <div>
                  <small>OPERATIONS HOME</small>
                  <h3>Good morning, Operations Team.</h3>
                  <p>Here&apos;s what needs attention across your operation.</p>
                </div>
                <span>Live workspace</span>
              </div>

              <div className="marketing-kpis">
                <article><span>Active Runs</span><strong>14</strong><small>3 require attention</small></article>
                <article><span>Inventory Risk</span><strong>12</strong><small>6 urgent reorders</small></article>
                <article><span>Avg Yield</span><strong>18.7%</strong><small>up 2.1% vs last week</small></article>
                <article><span>Compliance Flags</span><strong>2</strong><small>review required</small></article>
              </div>

              <div className="marketing-preview-grid">
                <section>
                  <div className="marketing-preview-section-title"><strong>Extraction Command Center</strong><span>View all runs →</span></div>
                  <div className="marketing-table-head"><span>Run ID</span><span>Product</span><span>Stage</span><span>Status</span></div>
                  {[
                    ['EXT-118','Live Resin','Purging','In Progress'],
                    ['PR-2048','Infused Pre-Rolls','Packaging','In Progress'],
                    ['EXT-117','Live Resin','Pressing','Completed'],
                    ['EXT-116','Distillate','Distillation','Completed'],
                  ].map(([id, product, stage, status]) => (
                    <div className="marketing-preview-row" key={id}>
                      <span>{id}</span><span>{product}</span><small>{stage}</small><em className={status === 'Completed' ? 'done' : ''}>{status}</em>
                    </div>
                  ))}
                </section>

                <section>
                  <div className="marketing-preview-section-title"><strong>METRC Sync / State Compliance</strong><span>View details →</span></div>
                  {[
                    ['Manifest matching','Synced'],
                    ['Package traceability','Synced'],
                    ['Batch transfers','Synced'],
                    ['Audit trail','Up to date'],
                    ['Compliance status','Pass'],
                  ].map(([label, state]) => (
                    <div className="marketing-status-row" key={label}><span>{label}</span><b>{state} <CircleCheck size={12}/></b></div>
                  ))}
                </section>
              </div>

              <div className="marketing-sync-bar">
                <div><ShieldCheck size={19}/><span><strong>All systems in sync</strong><small>Inventory, production, and compliance data are connected and audit-ready.</small></span></div>
                <div className="marketing-sync-stat"><strong>98.6%</strong><small>Compliance score</small></div>
                <div className="marketing-sync-stat"><strong>1</strong><small>Open action</small></div>
                <div className="marketing-sync-stat"><strong>2 mins</strong><small>Last sync</small></div>
              </div>
            </div>
          </div>
        </section>

        <section className="marketing-module-strip" aria-label="DoobieLogic workspaces">
          {modules.map(([Icon, label]) => <span key={label}><Icon size={18}/>{label}</span>)}
        </section>

        <section className="marketing-section marketing-feature-section" id="platform">
          <div className="marketing-section-heading">
            <div className="marketing-eyebrow">The platform</div>
            <h2>Built around the work operators actually have to finish.</h2>
            <p>One connected layer for the operational handoffs that usually live across spreadsheets, POS exports, seed-to-sale systems, notes, and tribal knowledge.</p>
          </div>

          <div className="marketing-feature-grid">
            {featureCards.map(({ icon: Icon, title, body }) => (
              <article className="marketing-feature-card" key={title}>
                <span className="marketing-icon"><Icon size={24}/></span>
                <h3>{title}</h3>
                <p>{body}</p>
                <a href="#workflow">Learn more <ArrowRight size={15}/></a>
              </article>
            ))}
          </div>
        </section>

        <section className="marketing-operations" id="extraction">
          <div className="marketing-operations-copy">
            <div className="marketing-eyebrow">Retail Ops + Production Ops</div>
            <h2>Different licenses. Different inventory. One operating language.</h2>
            <p>
              Retail teams need sellable inventory, purchasing, receiving, sales intelligence, and store-level controls.
              Production and cultivation teams need bulk cannabis, plants, materials, extraction, production runs, QA, and their own license context.
            </p>
            <div className="marketing-operation-list">
              <span><Boxes size={18}/> Retail inventory and buying workflows</span>
              <span><FlaskConical size={18}/> Extraction runs, yields, inputs, outputs, and costing</span>
              <span><Factory size={18}/> Production, packaging, QA, and Co-Man</span>
              <span><BarChart3 size={18}/> Operational and executive reporting</span>
            </div>
          </div>

          <div className="marketing-operations-panel">
            <div className="marketing-panel-label">Facility context</div>
            <article className="marketing-license-card retail"><span>Retail</span><strong>Adult-use store</strong><p>Sellable inventory, purchasing, sales, receiving, focused counts, compliance, and reporting.</p></article>
            <article className="marketing-license-card production"><span>Production</span><strong>Manufacturing / cultivation</strong><p>Bulk inventory, plants, extraction, production runs, QA, materials, costing, capacity, and traceability.</p></article>
          </div>
        </section>

        <section className="marketing-trust-band" id="compliance">
          <div className="marketing-trust-intro">
            <span className="marketing-trust-shield"><ShieldCheck size={28}/></span>
            <div><h3>Built for regulated operators</h3><p>Run cleaner operations, reduce risk, and preserve the evidence behind the work.</p></div>
          </div>
          <article><ShieldCheck size={21}/><div><strong>State Compliance</strong><p>Workflows designed around regulated cannabis operations and evolving requirements.</p></div></article>
          <article><Workflow size={21}/><div><strong>Full Traceability</strong><p>Track product, package, lot, run, and facility context across the operation.</p></div></article>
          <article><ClipboardCheck size={21}/><div><strong>Audit Ready</strong><p>Maintain a usable trail of actions, records, source context, and reports.</p></div></article>
          <article><LockKeyhole size={21}/><div><strong>Facility Controls</strong><p>Role-based access and facility boundaries keep operational data separated.</p></div></article>
        </section>

        <section className="marketing-section" id="workflow">
          <div className="marketing-section-heading compact">
            <div className="marketing-eyebrow">How it works</div>
            <h2>From source data to the next operational decision.</h2>
          </div>
          <div className="marketing-workflow-grid">
            {workflow.map(([number,title,body]) => (
              <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p></article>
            ))}
          </div>
        </section>

        <section className="marketing-final-cta">
          <div>
            <div className="marketing-eyebrow">DoobieLogic</div>
            <h2>One secure operating system for the work that cannot afford to get lost.</h2>
            <p>Open the secured DoobieLogic workspace for buying, inventory, receiving, production, extraction, reporting, and compliance.</p>
          </div>
          <a className="marketing-primary" href={APP_URL}>Open DoobieLogic <ArrowRight size={18}/></a>
        </section>
      </main>

      <footer className="marketing-footer">
        <div className="marketing-footer-brand">
          <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div>
          <small>Cannabis Operations Intelligence</small>
        </div>
        <div className="marketing-footer-links"><a href="#platform">Platform</a><a href="#extraction">Extraction</a><a href="#compliance">Compliance</a><a href={APP_URL}>Log in</a></div>
        <div className="marketing-footer-motto"><strong>Semper Paratus</strong><span>•</span><span>Powered by Good Weed and Data</span></div>
        <small className="marketing-copyright">© {new Date().getFullYear()} DoobieLogic</small>
      </footer>
    </div>
  );
}
