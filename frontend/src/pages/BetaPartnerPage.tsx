import { useState, type FormEvent } from "react";
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
  Store,
  Warehouse,
} from "lucide-react";
import { apiPublicPost } from "../lib/api";
import { BRAND_IMAGE_URL } from "../lib/brand";
import { trackMarketingEvent } from "../lib/marketingAnalytics";

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
    body: "Bring compliance checks closer to the work itself with tools designed around cannabis labels, records, inventory, and human-approved regulatory controls.",
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
    label: "WHOLESALE + PORTAL",
    icon: Store,
    title: "Wholesale & Customer Portal",
    body: "Publish a branded wholesale storefront, let licensed customers submit order requests, approve them into the same commercial order engine, allocate production inventory, work fulfillment, and keep manifest readiness tied to the shipment.",
  },
  {
    number: "07",
    label: "DOOBIE AGENT",
    icon: Bot,
    title: "Operational Intelligence",
    body: "Doobie Agent works across DoobieLogic to surface what needs attention and what should happen next. It connects purchasing, inventory, compliance, production, extraction, wholesale, and reporting data to explain exceptions and prepare governed actions for employee review.",
  },
  {
    number: "08",
    label: "REPORTING",
    icon: BarChart3,
    title: "Reports That Matter",
    body: "Move from raw exports to information operators can actually use, share, and act on across purchasing, inventory, compliance, production, extraction, and wholesale.",
  },
] as const;

export function BetaPartnerPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setSubmitted(false);
    setError("");

    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await apiPublicPost<{ accepted: boolean }>("/api/v1/beta/apply", {
        name: String(data.get("name") ?? ""),
        email: String(data.get("email") ?? ""),
        company: String(data.get("company") ?? ""),
        role: String(data.get("role") ?? ""),
        operation: String(data.get("operation") ?? ""),
        facilities: String(data.get("facilities") ?? ""),
        primary_workflow: String(data.get("primary_workflow") ?? ""),
        stack: String(data.get("stack") ?? ""),
        state: String(data.get("state") ?? ""),
        timeline: String(data.get("timeline") ?? ""),
        pain: String(data.get("pain") ?? ""),
        must_have: String(data.get("must_have") ?? ""),
        consent: data.get("consent") === "on",
        website: String(data.get("website") ?? ""),
      });
      form.reset();
      setSubmitted(true);
      trackMarketingEvent("beta_apply", { placement: "beta" });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "We could not submit your application. Please try again.");
    } finally {
      setSubmitting(false);
    }
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
            <a href="#program">Founding Program</a>
            <a href="#data">Your Data</a>
          </div>
          <a className="beta-nav-primary" href="#apply">Apply for Founding Beta</a>
        </nav>
      </header>

      <main>
        <section className="beta-hero">
          <div className="beta-hero-copy">
            <div className="marketing-eyebrow">DoobieLogic Founding Operator Beta</div>
            <h1>Put DoobieLogic against real work. <span>Help prove what works.</span></h1>
            <p>
              We’re selecting licensed cannabis operators to run agreed workflows inside DoobieLogic with guided implementation, direct support, and no subscription fee during the approved beta period. In return, we measure the before-and-after and collect structured feedback.
            </p>
            <div className="beta-hero-actions">
              <a className="marketing-primary" href="#apply">Apply for Founding Operator Beta <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">See the pilot process</a>
            </div>
            <div className="beta-proof-line">
              <span><CircleCheck size={15} /> Guided implementation</span>
              <span><CircleCheck size={15} /> No subscription fee during beta</span>
              <span><CircleCheck size={15} /> No positive testimonial required</span>
            </div>
          </div>

          <aside className="beta-partner-card">
            <span className="beta-open-badge"><i /> Applications Open</span>
            <h2>Founding Operator Beta</h2>
            <p>A limited operator cohort designed to prove DoobieLogic against real workflows, with hands-on setup and measurable outcomes.</p>
            <div className="beta-price">$0 <small>/ approved beta period</small></div>
            <div className="beta-card-divider" />
            {[
              "Workflow mapping and guided implementation",
              "Import and migration help for agreed workflows",
              "Direct line to the product team",
              "30 / 60 / 90-day outcome reviews",
            ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /> <span>{item}</span></div>)}
          </aside>
        </section>

        <section className="beta-section" id="platform">
          <div className="beta-section-inner">
            <div className="beta-section-heading">
              <div className="marketing-eyebrow">One operational platform</div>
              <h2>Built inside cannabis operations. Not outside looking in.</h2>
              <p>Buyer Dash has grown into DoobieLogic: a connected operations platform designed around the problems buyers, inventory teams, compliance managers, production teams, extraction teams, sales teams, and operators deal with every day.</p>
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
              <div className="marketing-eyebrow">Founding Operator Program</div>
              <h2>The trade is real usage, not praise.</h2>
              <p>Selected operators get hands-on implementation and a defined pilot. In return, we establish a baseline, run agreed workflows, measure the outcome, and use structured feedback to improve the product.</p>
            </div>
            <div className="beta-exchange-grid">
              <article className="beta-exchange-card highlight">
                <div className="marketing-eyebrow">You receive</div>
                <h3>Guided DoobieLogic Pilot</h3>
                {[
                  "No subscription fee during your approved beta period",
                  "Workflow mapping and guided implementation",
                  "Import and migration support for agreed workflows",
                  "Direct product-team access and priority beta support",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
              <article className="beta-exchange-card">
                <div className="marketing-eyebrow">We ask</div>
                <h3>Real Usage & Measured Feedback</h3>
                {[
                  "Use the platform in agreed real-world workflows",
                  "Establish a baseline before the pilot goes live",
                  "Allow agreed workflow outcomes to be measured at 30 / 60 / 90 days",
                  "Report friction and missing functionality. A positive testimonial is never required",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
            </div>

            <div className="beta-data-card" id="data">
              <ShieldCheck size={30} />
              <div>
                <h3>Your data stays yours. Outcome proof stays permissioned.</h3>
                <p>Founding operators help us understand how DoobieLogic performs in real cannabis operations. We measure only agreed workflow outcomes, and any testimonial or case study requires separate approval. Participation never requires a positive public statement.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="beta-section" id="apply">
          <div className="beta-apply-layout beta-section-inner">
            <div className="beta-apply-copy">
              <div className="marketing-eyebrow">Apply to join</div>
              <h2>We want operators willing to measure the before and after.</h2>
              <p>Retail. Cultivation. Manufacturing. Extraction. Wholesale. Vertically integrated. We want licensed operators with a real workflow they want to improve and a team willing to test it seriously.</p>
              <div className="beta-steps">
                <span><b>1</b> Apply and tell us which workflow hurts.</span>
                <span><b>2</b> We review fit for the current beta cohort.</span>
                <span><b>3</b> We map the workflow and establish a baseline.</span>
                <span><b>4</b> Your team runs the guided live pilot.</span>
                <span><b>5</b> We review outcomes at 30 / 60 / 90 days.</span>
              </div>
            </div>

            <form className="beta-form" onSubmit={handleSubmit}>
              <div className="beta-form-heading">
                <div><h3>Founding Operator Application</h3><p>Tell us what you run today, what workflow you want to improve, and when you want to start.</p></div>
                <span>NO BETA SUBSCRIPTION FEE</span>
              </div>
              <div className="beta-form-grid">
                <label>Full name<input name="name" autoComplete="name" required placeholder="Your name" /></label>
                <label>Work email<input name="email" type="email" autoComplete="email" required placeholder="you@company.com" /></label>
                <label>Company<input name="company" autoComplete="organization" required placeholder="Cannabis business" /></label>
                <label>Your role<input name="role" required placeholder="Buyer, GM, Compliance..." /></label>
                <label>Operation type<select name="operation" required defaultValue=""><option value="" disabled>Select one</option><option>Retail</option><option>Cultivation</option><option>Manufacturing / Production</option><option>Extraction</option><option>Wholesale / Distribution</option><option>Vertically Integrated</option><option>Other</option></select></label>
                <label>Facilities / licenses<select name="facilities" required defaultValue=""><option value="" disabled>Select range</option><option>1</option><option>2–3</option><option>4–10</option><option>11+</option></select></label>
                <label>Primary pilot workflow<select name="primary_workflow" required defaultValue=""><option value="" disabled>Select the first workflow to prove</option><option>Inventory & Receiving</option><option>Extraction & Production</option><option>Purchasing</option><option>Wholesale & Fulfillment</option><option>Compliance & Metrc</option><option>Multi-workflow / Vertically Integrated</option></select></label>
                <label>Primary POS / ERP<input name="stack" placeholder="Dutchie, Treez, spreadsheets..." /></label>
                <label>State<input name="state" required placeholder="MA" /></label>
                <label>Desired start<select name="timeline" required defaultValue=""><option value="" disabled>Select timeframe</option><option>As soon as possible</option><option>Within 30 days</option><option>Within 60–90 days</option><option>Exploring for later</option></select></label>
                <label className="full">What&apos;s the biggest operational problem you want DoobieLogic to solve?<textarea name="pain" required minLength={10} placeholder="Tell us where your team loses the most time, money, or visibility..." /></label>
                <label className="full">What would make DoobieLogic indispensable to your operation?<textarea name="must_have" placeholder="The feature or outcome you would never want to work without..." /></label>
                <label className="beta-honeypot" aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
              </div>
              <label className="beta-consent"><input name="consent" type="checkbox" required /><span>I understand beta participation includes structured feedback and agreed before-and-after workflow measurement under the Beta Participation & Data Use Agreement. Any testimonial or case study requires separate approval.</span></label>
              <button className="beta-submit" type="submit" disabled={submitting}>{submitting ? "Submitting..." : <>Submit Founding Operator Application <ArrowRight size={18} /></>}</button>
              {error && <div className="beta-error" role="alert">{error}</div>}
              {submitted && <div className="beta-success" role="status"><strong>Founding Operator application received.</strong><span>We’ll review fit and follow up using the email you provided. If selected, the first step is a workflow-baseline and implementation-fit call, not a generic sales demo.</span></div>}
            </form>
          </div>
        </section>
      </main>

      <footer className="beta-footer">
        <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div>
        <span>Built for licensed cannabis operators.</span>
        <span>Powered by Good Weed and Data</span>
      </footer>
    </div>
  );
}
