import { CircleHelp, Headphones, Mail } from "lucide-react";
import { HELP_EMAIL, INFO_EMAIL, SUPPORT_EMAIL } from "../lib/brand";

const channels = [
  {
    icon: Mail,
    title: "General questions",
    email: INFO_EMAIL,
    body: "Questions about DoobieLogic, whether it fits your operation, or how to get started.",
  },
  {
    icon: CircleHelp,
    title: "Product help",
    email: HELP_EMAIL,
    body: "Workflow questions, how-to help, and guidance using the platform.",
  },
  {
    icon: Headphones,
    title: "Technical support",
    email: SUPPORT_EMAIL,
    body: "Login problems, errors, unexpected behavior, or anything that is not working the way it should.",
  },
] as const;

export function MarketingContactChannels() {
  return <section className="marketing-contact-channels" aria-labelledby="contact-heading">
    <div className="marketing-contact-heading">
      <div>
        <div className="marketing-contact-eyebrow">Contact DoobieLogic</div>
        <h2 id="contact-heading">Need to reach us?</h2>
        <p>Choose the address that best fits what you need and we&apos;ll get it to the right place.</p>
      </div>
    </div>
    <div className="marketing-contact-grid">
      {channels.map(({ icon: Icon, title, email, body }) => <a className="marketing-contact-card" href={`mailto:${email}`} key={email}>
        <span className="marketing-contact-icon"><Icon size={22}/></span>
        <span className="marketing-contact-copy"><strong>{title}</strong><small>{body}</small><b>{email}</b></span>
      </a>)}
    </div>
  </section>;
}

export function AppSupportButton() {
  return <a className="app-support-button" href={`mailto:${SUPPORT_EMAIL}?subject=DoobieLogic%20Support`} aria-label={`Email ${SUPPORT_EMAIL}`} title={`Email ${SUPPORT_EMAIL}`}>
    <Headphones size={18}/><span>Support</span>
  </a>;
}
