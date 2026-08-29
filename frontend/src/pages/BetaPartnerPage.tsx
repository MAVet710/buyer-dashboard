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

const pillars = [
  {
    number: "01",
    label: "BUYING",
    icon: ShoppingCart,
    title: "Purchasing",
    body: "See what actually needs to be bought, what can wait, how vendors are performing, and what inventory is about to become tomorrow's emergency.",
  },
  {
    number: "02",
    label: "INVENTORY",
    icon: Warehouse,
    title: "Inventory & Receiving",
    body: "Receive, count, audit, reconcile, and follow inventory across facilities without losing the trail between the physical product and the systems tracking it.",
  },
  {
    number: "03",
    label: "COMPLIANCE",
    icon: ClipboardCheck,
    title: "Compliance Workflows",
    body: "Keep labels, records, inventory actions, approvals, and evidence close to the work. The goal is fewer 'how did this happen?' meetings.",
  },
  {
    number: "04",
    label: "PRODUCTION",
    icon: Factory,
    title: "Production Planning",
    body: "Plan manufacturing and cultivation work, manage bulk inventory, schedule what runs next, and see when materials, machines, labor, or deadlines are about to collide.",
  },
  {
    number: "05",
    label: "EXTRACTION",
    icon: FlaskConical,
    title: "Extraction",
    body: "Track source material, run status, yields, recovery, potency, cost, outputs, and downstream handoffs without reconstructing the run after the fact.",
  },
  {
    number: "06",
    label: "WHOLESALE + PORTAL",
    icon: Store,
    title: "Wholesale & Customer Portal",
    body: "Put a branded wholesale menu in front of licensed buyers, control pricing and sales units, approve orders, allocate inventory, and move the order into fulfillment without typing it twice.",
  },
  {
    number: "07",
    label: "DOOBIE AGENT",
    icon: Bot,
    title: "Doobie Agent",
    body: "Ask what needs attention across the facility and get answers grounded in your operation. Doobie can surface issues and prepare the next step; people still control regulated actions.",
  },
  {
    number: "08",
    label: "REPORTING",
    icon: BarChart3,
    title: "Reporting",
    body: "Turn the data you already have into reports your team can understand, share, and use without another hour of spreadsheet cleanup first.",
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
        stack: String(data.get("stack") ?? ""),
        state: String(data.get("state") ?? ""),
        pain: String(data.get("pain") ?? ""),
        must_have: String(data.get("must_have") ?? ""),
        consent: data.get("consent") === "on",
        website: String(data.get("website") ?? ""),
      });
      form.reset();
      setSubmitted(true);
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
            <h1>Help us build cannabis software <span>people actually want to use.</span></h1>
            <p>
              We&apos;re building DoobieLogic for the people doing the work: buyers, inventory teams, production crews, extractors, compliance managers, sales teams, and operators. The beta is where we find out what works in the real world and what still needs to get out of your way.
            </p>
            <div className="beta-hero-actions">
              <a className="marketing-primary" href="#apply">Apply for Free Beta Access <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">See what you&apos;ll test</a>
            </div>
            <div className="beta-proof-line">
              <span><CircleCheck size={15} /> No beta subscription fee</span>
              <span><CircleCheck size={15} /> Built with operator feedback</span>
              <span><CircleCheck size={15} /> Your data stays yours</span>
            </div>
          </div>

          <aside className="beta-partner-card">
            <span className="beta-open-badge"><i /> Applications Open</span>
            <h2>Become a Beta Partner</h2>
            <p>Use DoobieLogic in real workflows, tell us what saves time, tell us what gets in the way, and help us make the platform better before wider release.</p>
            <div className="beta-price">$0 <small>/ beta access</small></div>
            <div className="beta-card-divider" />
            {[
              "Early access to approved DoobieLogic modules",
              "Direct feedback channel with development",
              "A say in workflow and product priorities",
              "Priority onboarding and beta support",
            ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /> <span>{item}</span></div>)}
          </aside>
        </section>

        <section className="beta-section" id="platform">
          <div className="beta-section-inner">
            <div className="beta-section-heading">
              <div className="marketing-eyebrow">What you&apos;ll be testing</div>
              <h2>One operation. Fewer places to go hunting for the answer.</h2>
              <p>DoobieLogic connects the work cannabis teams already do across purchasing, inventory, compliance, production, extraction, wholesale, and reporting. We&apos;re not trying to make a dispensary behave like a manufacturing floor or a cultivation team behave like retail. Different licenses have different problems.</p>
            </div>
            <div className="beta-pillar-grid">
              {pillars.map(({ number, label, icon: Icon, title, body }) => (
                <article className={`beta-pillar-card ${label === "DOOBIE AGENT" ? "agent" : ""}`} key={number}>
                  <div className="beta-pillar-top"><span>{number} / {label}</span><Icon size={22} /></div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  {label === "DOOBIE AGENT" && <strong className="beta-agent-line">Less digging through reports. More knowing where to look next.</strong>}
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="beta-section" id="program">
          <div className="beta-section-inner">
            <div className="beta-section-heading">
              <div className="marketing-eyebrow">The deal</div>
              <h2>You get the software. We ask you not to be polite about it.</h2>
              <p>Selected beta partners get meaningful access to DoobieLogic at no subscription cost during the approved beta period. In return, we want real use and useful feedback. If a workflow is great, tell us. If it makes you want to throw the laptop, definitely tell us.</p>
            </div>
            <div className="beta-exchange-grid">
              <article className="beta-exchange-card highlight">
                <div className="marketing-eyebrow">You receive</div>
                <h3>DoobieLogic Beta Access</h3>
                {[
                  "Free access during your approved beta period",
                  "Early access to new workflows and tools",
                  "Direct feedback channel with development",
                  "A real voice in what gets improved next",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
              <article className="beta-exchange-card">
                <div className="marketing-eyebrow">We ask</div>
                <h3>Real Testing & Feedback</h3>
                {[
                  "Use the platform in agreed testing workflows",
                  "Tell us where the software creates friction or misses the point",
                  "Share approved usage, diagnostic, or operational test data that helps us improve it",
                  "Join occasional structured feedback sessions",
                ].map((item) => <div className="beta-check-row" key={item}><CircleCheck size={17} /><span>{item}</span></div>)}
              </article>
            </div>

            <div className="beta-data-card" id="data">
              <ShieldCheck size={30} />
              <div>
                <h3>Your data stays yours. We&apos;re here to learn from the workflow, not own your business.</h3>
                <p>Beta partners help us understand how DoobieLogic behaves inside real cannabis operations. Approved usage and diagnostic information helps us find bugs, confusing workflows, and missing functionality. Your operational data remains yours, and access stays governed by the beta agreement.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="beta-section" id="apply">
          <div className="beta-apply-layout beta-section-inner">
            <div className="beta-apply-copy">
              <div className="marketing-eyebrow">Apply to join</div>
              <h2>We&apos;re looking for operators, not professional beta testers.</h2>
              <p>Retail. Cultivation. Manufacturing. Extraction. Wholesale. Vertically integrated. If you know the work, know where the headaches are, and will tell us when something doesn&apos;t make sense, we want to hear from you.</p>
              <div className="beta-steps">
                <span><b>1</b> Tell us about your operation.</span>
                <span><b>2</b> We review fit for the current beta phase.</span>
                <span><b>3</b> Approved partners receive onboarding access.</span>
                <span><b>4</b> You use it, break it, question it, and help improve it.</span>
              </div>
            </div>

            <form className="beta-form" onSubmit={handleSubmit}>
              <div className="beta-form-heading">
                <div><h3>Beta Partner Application</h3><p>Give us enough context to understand your operation and where DoobieLogic could earn its keep.</p></div>
                <span>FREE TO APPLY</span>
              </div>
              <div className="beta-form-grid">
                <label>Full name<input name="name" autoComplete="name" required placeholder="Your name" /></label>
                <label>Work email<input name="email" type="email" autoComplete="email" required placeholder="you@company.com" /></label>
                <label>Company<input name="company" autoComplete="organization" required placeholder="Cannabis business" /></label>
                <label>Your role<input name="role" required placeholder="Buyer, GM, Compliance..." /></label>
                <label>Operation type<select name="operation" required defaultValue=""><option value="" disabled>Select one</option><option>Retail</option><option>Cultivation</option><option>Manufacturing / Production</option><option>Extraction</option><option>Wholesale / Distribution</option><option>Vertically Integrated</option><option>Other</option></select></label>
                <label>Facilities / licenses<select name="facilities" required defaultValue=""><option value="" disabled>Select range</option><option>1</option><option>2–3</option><option>4–10</option><option>11+</option></select></label>
                <label>Primary POS / ERP<input name="stack" placeholder="Dutchie, Treez, spreadsheets..." /></label>
                <label>State<input name="state" required placeholder="MA" /></label>
                <label className="full">What operational problem wastes the most time right now?<textarea name="pain" required minLength={10} placeholder="Inventory, production planning, compliance, wholesale, reporting... tell us where it hurts." /></label>
                <label className="full">What would make DoobieLogic something your team would not want to give up?<textarea name="must_have" placeholder="A workflow, result, or capability that would make the platform genuinely useful..." /></label>
                <label className="beta-honeypot" aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
              </div>
              <label className="beta-consent"><input name="consent" type="checkbox" required /><span>I understand beta participation includes structured feedback and the sharing of approved usage, diagnostic, or operational test data under the Beta Participation & Data Use Agreement.</span></label>
              <button className="beta-submit" type="submit" disabled={submitting}>{submitting ? "Submitting..." : <>Submit Beta Application <ArrowRight size={18} /></>}</button>
              {error && <div className="beta-error" role="alert">{error}</div>}
              {submitted && <div className="beta-success" role="status"><strong>Application received.</strong><span>Thanks for putting your hand up. We&apos;ll review the fit and follow up using the email you provided.</span></div>}
            </form>
          </div>
        </section>
      </main>

      <footer className="beta-footer">
        <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div>
        <span>Cannabis operations software built around the work.</span>
        <span>Powered by Good Weed and Data</span>
      </footer>
    </div>
  );
}
