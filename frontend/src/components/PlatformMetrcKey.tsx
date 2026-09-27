import { useState } from "react";
import { apiPost } from "../lib/api";
import { guidedMetrcBase } from "./guidedMetrcTypes";

export function PlatformMetrcKey({ environment, onSaved }: { environment: string; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save(form: HTMLFormElement) {
    let key = String(new FormData(form).get("vendor_key") || "");
    form.reset(); setBusy(true); setMessage("");
    try { await apiPost(guidedMetrcBase + "/platform-vendor", { state: "MA", environment, api_key: key }); setMessage("Platform key saved. Existing verified facility key pairs are not automatically replaced."); onSaved(); }
    catch { setMessage("Platform setup was not confirmed. Check platform permissions and the selected environment."); }
    finally { key = ""; setBusy(false); }
  }
  return <details><summary>Platform administrator setup</summary><p>This is DoobieLogic's integrator credential, not the customer's user API key. Environment: {environment}.</p>
    <form onSubmit={event => { event.preventDefault(); void save(event.currentTarget); }}><label>Platform integrator API key<input name="vendor_key" type="password" minLength={8} maxLength={1024} autoComplete="off" required disabled={busy} /></label><button className="secondary" type="submit" disabled={busy}>Save platform key for this environment</button></form>
    {message && <p role="status">{message}</p>}
  </details>;
}
