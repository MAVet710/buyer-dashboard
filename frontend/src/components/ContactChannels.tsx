import { CircleHelp, Headphones, Mail } from "lucide-react";
import { HELP_EMAIL, INFO_EMAIL, SUPPORT_EMAIL } from "../lib/brand";

const channels = [
  {
    icon: Mail,
    title: "Curious about DoobieLogic?",
    email: INFO_EMAIL,
    body: "Questions about the platform, whether it fits your operation, or how to get started.",
  },
  {
    icon: CircleHelp,
    title: "Need a hand?",
    email: HELP_EMAIL,
    body: "Workflow questions, how-to stuff, or help figuring out where something lives.",
  },
  {
    icon: Headphones,
    title: "Something acting weird?",
    email: SUPPORT_EMAIL,
    body: "Login trouble, errors, broken behavior, or anything that should be working and isn't.",
  },
] as const;

export function MarketingContactChannels() {
  return <section className="marketing-contact-channels" aria-labelledby="contact-heading">
    <div className="marketing-contact-heading">
      <div>
        <div className="marketing-contact-eyebrow">Talk to us</div>
        <h2 id="contact-heading">Need us? Pick an inbox.</h2>
        <p>Product question, need a hand, or something being stubborn? Hit the address that fits. A real person will see it.</p>
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
