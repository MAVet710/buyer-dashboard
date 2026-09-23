import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight } from "lucide-react";
import { apiPublicGet, apiPublicPost } from "../../lib/api";
import { getAdvisoryAttribution } from "../../lib/advisoryAnalytics";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";
import "../../advisory-forms.css";

const serviceOptions = [
  ["not-sure", "Help me choose"], ["operational-diagnostic", "Operational Diagnostic"],
  ["inventory-profit-audit", "Inventory & Profit Audit"], ["fractional-purchasing", "Fractional Purchasing"],
  ["compliance-operational-audit", "Compliance & Operational Audit"], ["sop-workflow-development", "SOP & Workflow Development"],
  ["metrc-technology", "Metrc & Cannabis Technology"], ["production-extraction", "Production & Extraction Operations"],
] as const;

export function ConsultingLeadForm({service = "not-sure", sourceTool, toolInputs}: {service?: string; sourceTool?: "operations-score" | "inventory-health-check"; toolInputs?: Record<string, number | null>}) {
  const [busy,setBusy] = useState(false), [error,setError] = useState(""), [reference,setReference] = useState("");
  const [booking,setBooking] = useState<string | null>(null);
  const started = useRef(false), pending = useRef(false), feedback = useRef<HTMLDivElement>(null), submissionId = useRef(crypto.randomUUID()), lastPayload = useRef("");
  useEffect(()=>{ if(error || reference) feedback.current?.focus(); },[error,reference]);
  useEffect(()=>{
    let active=true;
    void apiPublicGet<{available:boolean;url:string|null}>("/api/v1/advisory/booking").then(result=>{
      if (!active || !result.available || !result.url) return;
      try { const url=new URL(result.url); if(url.protocol==="https:" && !url.username && !url.password) setBooking(url.href); } catch { /* No fabricated availability. */ }
    }).catch(()=>undefined);
    return()=>{active=false;};
  },[]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if(pending.current) return;
    pending.current=true;setBusy(true);setError("");setReference("");
    const form=event.currentTarget, data=new FormData(form);
    const text=(name:string)=>String(data.get(name)||"").trim();
    try {
      const payload={
        name:text("name"),email:text("email"),phone:text("phone"),company:text("company"),role:text("role"),state:text("state"),operation:text("operation"),locations:Number(text("locations")),challenge:text("challenge"),service:text("service"),message:text("message"),consent:data.get("consent")==="on",website:text("website"),
        attribution:getAdvisoryAttribution(),...(sourceTool?{source_tool:sourceTool}:{}),...(toolInputs?{tool_inputs:toolInputs}:{}),
      };
      const serialized=JSON.stringify(payload);
      if(lastPayload.current && lastPayload.current!==serialized) submissionId.current=crypto.randomUUID();
      lastPayload.current=serialized;
      const result=await apiPublicPost<{accepted:boolean;reference?:string}>("/api/v1/advisory/leads",{...payload,submission_id:submissionId.current});
      if(!result.accepted || !result.reference) throw new Error("We could not confirm receipt. Your answers are still here; please try again.");
      setReference(result.reference);form.reset();submissionId.current=crypto.randomUUID();lastPayload.current="";
      trackMarketingEvent("consultation_form_submitted",{placement:"consultation",item:payload.service});
    } catch(err) {setError(err instanceof Error && !/Storefront/.test(err.message)?err.message:"We could not confirm receipt. Your answers are still here. Please try again or contact info@doobielogic.io.");}
    finally {pending.current=false;setBusy(false);}
  }
  return <section id="consultation" className="mh-section mh-container ad-consultation" aria-labelledby="consultation-heading">
    <div className="mh-section-top"><div><span className="mh-eyebrow">Start with a conversation</span><h2 id="consultation-heading">Book a free<br/>20-minute consultation.</h2></div><p>Tell us where the work gets difficult. We’ll review your request and coordinate a time. An inquiry does not reserve a calendar slot or commit you to a paid engagement.</p></div>
    {booking && <p><a className="mh-text-link" href={booking} target="_blank" rel="noreferrer" onClick={()=>trackMarketingEvent("consultation_cta_clicked",{placement:"consultation",item:service})}>Open the booking calendar <ArrowUpRight size={16}/></a></p>}
    <form className="ad-form" aria-busy={busy} onSubmit={submit} onFocusCapture={()=>{if(!started.current){started.current=true;trackMarketingEvent("consultation_form_started",{placement:"consultation",item:service});}}}>
      <p>Fields are required unless marked optional. Please don’t include credentials, customer details, or regulated records.</p>
      <fieldset disabled={busy}><legend>Your operation</legend><div className="ad-fields">
        <label>Name<input name="name" autoComplete="name" required minLength={2} maxLength={120}/></label>
        <label>Email<input name="email" type="email" autoComplete="email" required maxLength={254}/></label>
        <label>Phone <span>(optional)</span><input name="phone" type="tel" autoComplete="tel" maxLength={40}/></label>
        <label>Company<input name="company" autoComplete="organization" required minLength={2} maxLength={160}/></label>
        <label>Role<input name="role" autoComplete="organization-title" required minLength={2} maxLength={120}/></label>
        <label>State / jurisdiction<input name="state" required minLength={2} maxLength={80}/></label>
        <label>Business type<select name="operation" required defaultValue=""><option value="" disabled>Select business type</option>{["Retail","Cultivation","Manufacturing","Extraction","Vertically integrated","Multi-site operator","Cannabis technology / SaaS","Other"].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>Number of locations<input name="locations" type="number" min={1} max={10000} step={1} required defaultValue={1}/></label>
        <label className="ad-full">Service interested in<select name="service" defaultValue={service} required>{serviceOptions.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
        <label className="ad-full">Primary challenge<textarea name="challenge" minLength={10} maxLength={2000} required rows={3}/></label>
        <label className="ad-full">Anything else we should know? <span>(optional)</span><textarea name="message" maxLength={4000} rows={3}/></label>
        <label className="ad-honeypot" aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" maxLength={200}/></label>
      </div>
      <label className="ad-consent"><input type="checkbox" name="consent" required/><span>I agree that DoobieLogic may store these details{sourceTool === "operations-score" ? " and my assessment answers" : ""}, including referral information, to review this inquiry and contact me about consulting. This does not subscribe me to marketing emails.</span></label>
      <button className="mh-button" type="submit" disabled={busy}>{busy?"Sending request…":"Request my free consultation"}<ArrowUpRight size={17}/></button></fieldset>
      {(error||reference)&&<div ref={feedback} tabIndex={-1} className="ad-feedback" role={error?"alert":"status"}>{error?<><strong>We could not confirm your request.</strong><p>{error}</p></>:<><strong>Your consultation request is saved.</strong><p>We’ll follow up using the email you provided to agree on a time. Reference: {reference}</p></>}</div>}
      <p className="ad-note">Your inventory file stays in your browser. Contact <a href="mailto:info@doobielogic.io">info@doobielogic.io</a> with questions about your inquiry or to request deletion.</p>
    </form>
  </section>;
}
