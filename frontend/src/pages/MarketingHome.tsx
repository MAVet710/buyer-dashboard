import {
  ArrowRight,
  BarChart3,
  Boxes,
  CircleCheck,
  ClipboardCheck,
  Factory,
  FileCheck2,
  FlaskConical,
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
    body: "Track what went in, what came out, what it cost, and where the run actually stands. No end-of-week archaeology through notebooks and spreadsheets.",
  },
  {
    icon: Workflow,
    title: "METRC Integration",
    body: "Keep packages, manifests, transfers, and facility context tied to the work instead of treating METRC like a second full-time job.",
  },
  {
    icon: Warehouse,
    title: "Inventory & Receiving",
    body: "Know what is on hand, what is moving, what needs a count, and what is about to become somebody's problem before it gets there.",
  },
  {
    icon: Factory,
    title: "Production & QA",
    body: "Follow material from bulk input through finished goods with production, packaging, QA, yields, and costing connected the whole way.",
  },
  {
    icon: FileCheck2,
    title: "Compliance Evidence & Reporting",
    body: "Keep the receipts: who did what, when they did it, what data backed it up, and what report proves it when somebody comes asking.",
  },
];

const workflow = [
  ["01", "Plug in the operation", "Set up the facilities, people, roles, licenses, and data your team already uses. No ceremonial software rollout required."],
  ["02", "See what is actually going on", "Spot inventory pressure, purchasing needs, active runs, holds, receiving work, and compliance problems before they turn into fire drills."],
  ["03", "Do the work where the data lives", "Receive it, count it, buy it, make it, extract it, investigate it, and report it without bouncing through five different systems."],
  ["04", "Keep the receipts", "Every important move keeps its context, facility, user, source data, and audit trail so you are not rebuilding the story six weeks later."],
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
            <div className="marketing-eyebrow">Cannabis ops without the spreadsheet circus</div>
            <h1>
              Run <span>buying, inventory, extraction, production,</span> and compliance from one place.
            </h1>
            <p>
              DoobieLogic gives cannabis operators one clear view of the work that keeps a licensed facility moving, from purchasing and receiving to production,
              traceability, reporting, and compliance.
            </p>

            <div className="marketing-cta-row">
              <a className="marketing-primary" href={APP_URL}>Open DoobieLogic <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">See what it does</a>
            </div>

            <div className="marketing-proof-line">
              <span><CircleCheck size={16} /> Facility-scoped</span>
              <span><LockKeyhole size={16} /> Role-aware</span>
              <span><ShieldCheck size={16} /> Audit trail intact</span>
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
                  <h3>Morning. Here&apos;s what&apos;s actually going on.</h3>
                  <p>The stuff worth looking at before it becomes your whole afternoon.</p>
                </div>
                <span>Live workspace</span>
              </div>

              <div className="marketing-kpis">
                <article><span>Active Runs</span><strong>14</strong><small>3 need a look</small></article>
                <article><span>Inventory Risk</span><strong>12</strong><small>6 urgent reorders</small></article>
                <article><span>Avg Yield</span><strong>18.7%</strong><small>up 2.1% vs last week</small></article>
                <article><span>Compliance Flags</span><strong>2</strong><small>worth fixing now</small></article>
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
                  <div className="marketing-preview-section-title"><strong>METRC / State Compliance</strong><span>View details →</span></div>
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
                <div><ShieldCheck size={19}/><span><strong>Nothing hiding in the weeds</strong><small>Inventory, production, and compliance are reading from the same operation.</small></span></div>
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
            <h2>Built by people who know a bad count can ruin your whole afternoon.</h2>
            <p>Spreadsheets, POS exports, METRC, whiteboards, chat threads, and that one person who somehow knows everything. DoobieLogic pulls the operation back into one place.</p>
          </div>

          <div className="marketing-feature-grid">
            {featureCards.map(({ icon: Icon, title, body }) => (
              <article className="marketing-feature-card" key={title}>
                <span className="marketing-icon"><Icon size={24}/></span>
                <h3>{title}</h3>
                <p>{body}</p>
                <a href="#workflow">See the flow <ArrowRight size={15}/></a>
              </article>
            ))}
          </div>
        </section>

        <section className="marketing-operations" id="extraction">
          <div className="marketing-operations-copy">
            <div className="marketing-eyebrow">Retail Ops + Production Ops</div>
            <h2>A retail vault and an extraction lab are not the same inventory problem.</h2>
            <p>
              Retail cares about sellable units, turns, receiving, and reorders. Production and cultivation care about bulk material,
              plants, runs, yields, QA, and traceability. DoobieLogic knows the difference and keeps each license in its lane.
            </p>
            <div className="marketing-operation-list">
              <span><Boxes size={18}/> Retail inventory, buying, receiving, and sales</span>
              <span><FlaskConical size={18}/> Extraction runs, yields, inputs, outputs, and costing</span>
              <span><Factory size={18}/> Production, packaging, QA, and Co-Man</span>
              <span><BarChart3 size={18}/> Reports that tell you something useful</span>
            </div>
          </div>

          <div className="marketing-operations-panel">
            <div className="marketing-panel-label">License context matters</div>
            <article className="marketing-license-card retail"><span>Retail</span><strong>Adult-use store</strong><p>Sellable inventory, buying, sales, receiving, counts, compliance, and the stuff your store actually lives in.</p></article>
            <article className="marketing-license-card production"><span>Production</span><strong>Manufacturing / cultivation</strong><p>Bulk inventory, plants, extraction, runs, QA, materials, costing, capacity, and traceability without pretending it is retail.</p></article>
          </div>
        </section>

        <section className="marketing-trust-band" id="compliance">
          <div className="marketing-trust-intro">
            <span className="marketing-trust-shield"><ShieldCheck size={28}/></span>
            <div><h3>Built for cannabis, where “close enough” gets expensive.</h3><p>Keep the operation clean, the records useful, and the compliance story easy to prove.</p></div>
          </div>
          <article><ShieldCheck size={21}/><div><strong>State Compliance</strong><p>Keep regulated work grounded in the rules and procedures that actually apply.</p></div></article>
          <article><Workflow size={21}/><div><strong>Full Traceability</strong><p>Follow products, lots, packages, runs, and facilities without playing detective later.</p></div></article>
          <article><ClipboardCheck size={21}/><div><strong>Audit Ready</strong><p>When somebody asks what happened, have the record instead of a story.</p></div></article>
          <article><LockKeyhole size={21}/><div><strong>Facility Controls</strong><p>People see the facilities and tools they should see. That&apos;s it.</p></div></article>
        </section>

        <section className="marketing-section" id="workflow">
          <div className="marketing-section-heading compact">
            <div className="marketing-eyebrow">How it works</div>
            <h2>From messy data to a clear next move.</h2>
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
            <h2>Good weed deserves better operations.</h2>
            <p>DoobieLogic handles the regulated, detail-heavy stuff that keeps good operators from running blind.</p>
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
