import { FormEvent, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Bot,
  CircleCheck,
  ClipboardCheck,
  Factory,
  FlaskConical,
  ShieldCheck,
  ShoppingCart,
  Warehouse,
} from "lucide-react";
import { BRAND_IMAGE_URL } from "../lib/brand";

const pillars = [
  {
    number: "01",
    label: "BUYING",
    icon: ShoppingCart,
    title: "Purchasing Intelligence",
    body: "Understand inventory needs, build smarter orders, track vendor performance, and make purchasing decisions with real operational context.",
  },
  {
    number: "02",
    label: "INVENTORY",
    icon: Warehouse,
    title: "Inventory & Receiving",
    body: "Receive, audit, reconcile, and understand inventory across facilities without losing the trail between physical stock and source systems.",
  },
  {
    number: "03",
    label: "COMPLIANCE",
    icon: ClipboardCheck,
    title: "Compliance Workflows",
    body: "Bring compliance checks closer to the work itself with tools designed around cannabis labels, records, inventory, and operational controls.",
  },
  {
    number: "04",
    label: "PRODUCTION",
    icon: Factory,
    title: "Production Operations",
    body: "Plan manufacturing and cultivation workflows, manage production inventory, work queues, bulk cannabis products, and facility-specific operations.",
  },
  {
    number: "05",
    label: "EXTRACTION",
    icon: FlaskConical,
    title: "Extraction Operations",
    body: "Plan and track extraction runs from source material through finished output. Monitor yields, recovery, potency, run performance, material movement, and downstream handoffs.",
  },
  {
    number: "06",
    label: "DOOBIE AGENT",
    icon: Bot,
    title: "Operational Intelligence",
    body: "Doobie Agent works across DoobieLogic to surface what needs attention and what should happen next. It connects purchasing, inventory, compliance, production, extraction, and reporting data to explain exceptions, answer operational questions, surface risks, and provide recommendations grounded in what is actually happening inside the business.",
  },
  {
    number: "07",
    label: "REPORTING",
    icon: BarChart3,
    title: "Reports That Matter",
    body: "Move from raw exports to information operators can actually use, share, and act on across purchasing, inventory, compliance, production, and extraction.",
  },
] as const;

export function BetaPartnerPage() {
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  return (
    <div className="beta-page">
      <header className="beta-nav-wrap">
        <nav className="beta-nav" aria-label="Beta program navigation">
          <a className="marketing-brand" href="/" aria-label="DoobieLogic home">
            <img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" />
            <span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span>
          </a>
          <div className="beta-nav-links">
            <a href="#platform">Platform</a>
            <a href="#program">Beta Program</a>
            <a href="#data">Your Data</a>
          </div>
          <a className="beta-nav-primary" href="#apply">Apply for Beta</a>
        </nav>
      </header>

      <main>
        <section className="beta-hero">
          <div className="beta-hero-copy">
            <div className="marketing-eyebrow">DoobieLogic Beta Partner Program</div>
            <h1>Help build the operating system <span>cannabis deserves.</span></h1>
            <p>
              DoobieLogic brings purchasing, inventory, receiving, compliance, production, extraction, and operational intelligence into one platform built for the people actually running cannabis businesses.
            </p>
            <div className="beta-hero-actions">
              <a className="marketing-primary" href="#apply">Apply for Free Beta Access <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">See what you&apos;ll test</a>
            </div>
            <div className="beta-proof-line">
              <span><CircleCheck size={15} /> No beta subscription fee</span>
              <span><CircleCheck size={15} /> Built with real operators</span>
              <span><CircleCheck size={15} /> Your data stays yours</span>
            </div>
          </div>

          <aside className="beta-partner-card">
            <span className="beta-open-badge"><i /> Applications Open</span>
            <h2>Become a Beta Partner</h2>
            <p>Get early access to DoobieLogic while helping us validate how the platform performs inside real cannabis operations.</p>
            <div className="beta-price">$0 <small>/ beta access</small></div>
            <div className="beta-card-divider" />
            {[
              "Early access to approved DoobieLogic modules",
              "Direct line to the development team",
              "Influence product priorities and workflows",
              "Priority onboarding and beta support",
            ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /> <span>{item}</span></div>)}
          </aside>
        </section>

        <section className="beta-section" id="platform">
          <div className="beta-section-inner">
            <div className="beta-section-heading">
              <div className="marketing-eyebrow">One operational platform</div>
              <h2>Built inside cannabis operations. Not outside looking in.</h2>
              <p>Buyer Dash has grown into DoobieLogic: a connected operations platform designed around the problems buyers, inventory teams, compliance managers, production teams, extraction teams, and operators deal with every day.</p>
            </div>
            <div className="beta-pillar-grid">
              {pillars.map(({ number, label, icon: Icon, title, body }) => (
                <article className={`beta-pillar-card ${label === "DOOBIE AGENT" ? "agent" : ""}`} key={number}>
                  <div className="beta-pillar-top"><span>{number} / {label}</span><Icon size={22} /></div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  {label === "DOOBIE AGENT" && <strong className="beta-agent-line">Less searching through reports. More knowing what needs to happen next.</strong>}
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="beta-section" id="program">
          <div className="beta-section-inner">
            <div className="beta-section-heading">
              <div className="marketing-eyebrow">The partnership</div>
              <h2>Free access isn&apos;t the catch. Participation is the trade.</h2>
              <p>The beta program is a genuine partnership. We give selected operators meaningful access to the platform. In return, we ask them to help us make it better.</p>
            </div>
            <div className="beta-exchange-grid">
              <article className="beta-exchange-card highlight">
                <div className="marketing-eyebrow">You receive</div>
                <h3>DoobieLogic Beta Access</h3>
                {[
                  "Free access during your approved beta period",
                  "Early access to new workflows and tools",
                  "Direct feedback channel with development",
                  "A voice in what DoobieLogic becomes",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
              <article className="beta-exchange-card">
                <div className="marketing-eyebrow">We ask</div>
                <h3>Real Testing & Feedback</h3>
                {[
                  "Use the platform in agreed testing workflows",
                  "Report problems, friction, and missing functionality",
                  "Share approved usage, diagnostic, or operational test data that helps improve the product",
                  "Participate in occasional structured feedback",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
            </div>

            <div className="beta-data-card" id="data">
              <ShieldCheck size={30} />
              <div>
                <h3>Your data stays yours. Your experience helps shape DoobieLogic.</h3>
                <p>Beta partners help us understand how the platform performs in real cannabis operations. The information you choose to share helps us find problems, improve workflows, and build better tools. We use it to make DoobieLogic better, not to make your business our business.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="beta-section" id="apply">
          <div className="beta-apply-layout beta-section-inner">
            <div className="beta-apply-copy">
              <div className="marketing-eyebrow">Apply to join</div>
              <h2>We want operators who will push the platform.</h2>
              <p>Retail. Cultivation. Manufacturing. Extraction. Vertically integrated. We want partners who understand the work and aren&apos;t afraid to tell us what isn&apos;t good enough yet.</p>
              <div className="beta-steps">
                <span><b>1</b> Tell us about your operation.</span>
                <span><b>2</b> We review fit for the current beta phase.</span>
                <span><b>3</b> Approved partners receive onboarding access.</span>
                <span><b>4</b> You help shape what ships next.</span>
              </div>
            </div>

            <form className="beta-form" onSubmit={handleSubmit}>
              <div className="beta-form-heading">
                <div><h3>Beta Partner Application</h3><p>Tell us enough to understand where DoobieLogic could help.</p></div>
                <span>FREE TO APPLY</span>
              </div>
              <div className="beta-form-grid">
                <label>Full name<input name="name" autoComplete="name" required placeholder="Your name" /></label>
                <label>Work email<input name="email" type="email" autoComplete="email" required placeholder="you@company.com" /></label>
                <label>Company<input name="company" autoComplete="organization" required placeholder="Cannabis business" /></label>
                <label>Your role<input name="role" required placeholder="Buyer, GM, Compliance..." /></label>
                <label>Operation type<select name="operation" required defaultValue=""><option value="" disabled>Select one</option><option>Retail</option><option>Cultivation</option><option>Manufacturing / Production</option><option>Extraction</option><option>Vertically Integrated</option><option>Other</option></select></label>
                <label>Facilities / licenses<select name="facilities" required defaultValue=""><option value="" disabled>Select range</option><option>1</option><option>2–3</option><option>4–10</option><option>11+</option></select></label>
                <label>Primary POS / ERP<input name="stack" placeholder="Dutchie, Treez, spreadsheets..." /></label>
                <label>State<input name="state" required placeholder="MA" /></label>
                <label className="full">What&apos;s the biggest operational problem you want DoobieLogic to solve?<textarea name="pain" required placeholder="Tell us where your team loses the most time, money, or visibility..." /></label>
                <label className="full">What would make DoobieLogic indispensable to your operation?<textarea name="mustHave" placeholder="The feature or outcome you would never want to work without..." /></label>
              </div>
              <label className="beta-consent"><input type="checkbox" required /><span>I understand beta participation includes structured feedback and the sharing of approved usage, diagnostic, or operational test data under the Beta Participation & Data Use Agreement.</span></label>
              <button className="beta-submit" type="submit">Submit Beta Application <ArrowRight size={18} /></button>
              {submitted && <div className="beta-success" role="status"><strong>Application captured.</strong><span>This preview flow is ready for the production submission endpoint to be connected.</span></div>}
            </form>
          </div>
        </section>
      </main>

      <footer className="beta-footer">
        <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div>
        <span>Commercial-ready cannabis intelligence system.</span>
        <span>Powered by Good Weed and Data</span>
      </footer>
    </div>
  );
}
