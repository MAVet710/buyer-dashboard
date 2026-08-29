import { type ReactNode, useState } from "react";
import "../public-storefront-age-gate.css";

const AGE_GATE_KEY = "doobielogic:public-storefront:21-plus";

function initialStatus(): "unknown" | "confirmed" | "denied" {
  try {
    const stored = window.localStorage.getItem(AGE_GATE_KEY);
    if (stored === "confirmed") return "confirmed";
    if (window.sessionStorage.getItem(`${AGE_GATE_KEY}:denied`) === "1") return "denied";
  } catch {
    // Storage is an enhancement only; the visitor can still confirm this visit.
  }
  return "unknown";
}

export function PublicStorefrontAgeGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"unknown" | "confirmed" | "denied">(initialStatus);

  const confirm = () => {
    try {
      window.localStorage.setItem(AGE_GATE_KEY, "confirmed");
      window.sessionStorage.removeItem(`${AGE_GATE_KEY}:denied`);
    } catch {
      // Keep the confirmation in component state when storage is unavailable.
    }
    setStatus("confirmed");
  };

  const deny = () => {
    try {
      window.localStorage.removeItem(AGE_GATE_KEY);
      window.sessionStorage.setItem(`${AGE_GATE_KEY}:denied`, "1");
    } catch {
      // Keep the denial in component state when storage is unavailable.
    }
    setStatus("denied");
  };

  if (status === "confirmed") return <>{children}</>;

  return (
    <main className="public-age-gate" aria-labelledby="public-age-gate-title">
      <section className="public-age-gate-card">
        <div className="public-age-gate-mark" aria-hidden="true">21+</div>
        <div className="eyebrow">WHOLESALE ACCESS</div>
        <h1 id="public-age-gate-title">Age verification required</h1>
        {status === "denied" ? (
          <>
            <p>This wholesale storefront is restricted to visitors who are 21 years of age or older.</p>
            <p className="public-age-gate-note">Access remains blocked for this browser session.</p>
          </>
        ) : (
          <>
            <p>You must be 21 years of age or older to enter this cannabis wholesale storefront.</p>
            <div className="public-age-gate-actions">
              <button type="button" className="primary" onClick={confirm}>I am 21 or older</button>
              <button type="button" className="secondary" onClick={deny}>I am under 21</button>
            </div>
            <p className="public-age-gate-note">Age confirmation does not replace cannabis-license verification or supplier approval for wholesale orders.</p>
          </>
        )}
      </section>
    </main>
  );
}
