import { useState } from "react";
import { advisoryPrivacyBlocked, getAdvisoryAnalyticsConsent, setAdvisoryAnalyticsConsent } from "../../lib/advisoryAnalytics";

export function AnalyticsConsent() {
  const [allowed, setAllowed] = useState(getAdvisoryAnalyticsConsent);
  const blocked = advisoryPrivacyBlocked();
  return <div className="analytics-consent"><label><input type="checkbox" checked={allowed && !blocked} disabled={blocked} onChange={event => { setAdvisoryAnalyticsConsent(event.target.checked); setAllowed(event.target.checked); }} /> Allow optional usage measurement</label><p>{blocked ? "Your browser privacy preference disables optional measurement." : "Off unless you opt in. Sends page and action categories for aggregate counts, without form contents or user identifiers. You can change this anytime."}</p></div>;
}
export default AnalyticsConsent;
