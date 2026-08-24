import { CircleHelp, Headphones, Mail } from "lucide-react";
import { HELP_EMAIL, INFO_EMAIL, SUPPORT_EMAIL } from "../lib/brand";

const channels = [
  {
    icon: Mail,
    title: "General & product info",
    email: INFO_EMAIL,
    body: "Questions about DoobieLogic, the platform, or getting started.",
  },
  {
    icon: CircleHelp,
    title: "Help",
    email: HELP_EMAIL,
    body: "How-to questions, workflow guidance, and product help.",
  },
  {
    icon: Headphones,
    title: "Support",
    email: SUPPORT_EMAIL,
    body: "Account access, technical issues, and operational support.",
  },
] as const;

export function MarketingContactChannels() {
  return <section className="marketing-contact-channels" aria-labelledby="contact-heading">
    <div className="marketing-contact-heading">
      <div>
        <div className="marketing-contact-eyebrow">Contact DoobieLogic</div>
        <h2 id="contact-heading">Get to the right inbox without hunting for an address.</h2>
        <p>Choose the channel that best matches what you need. All three addresses are monitored through the DoobieLogic Spacemail workspace.</p>
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
