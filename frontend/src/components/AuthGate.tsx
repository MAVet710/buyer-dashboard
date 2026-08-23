import type { Session } from "@supabase/supabase-js";
import { useEffect, useState, type PropsWithChildren } from "react";
import { authConfigured, supabase } from "../lib/supabase";
import { apiPost, clearTrialSession, trialToken } from "../lib/api";
import { LegalGate } from "./LegalGate";
import { PasswordGate } from "./PasswordGate";

type TrialActivation = { token:string; expires_at:string; organization:{id:string;name:string;slug:string}; facility:{id:string;name:string;code:string}; license:{plan?:string|null;features?:string[]} };

function validStoredTrial(): boolean {
  const token = trialToken(); const expires = Date.parse(sessionStorage.getItem("buyer-dash-trial-expires") ?? "");
  if (!token || !Number.isFinite(expires) || expires <= Date.now()) { clearTrialSession(); return false; }
  return true;
}

export function AuthGate({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!authConfigured);
  const [login, setLogin] = useState(""); const [password, setPassword] = useState(""); const [message, setMessage] = useState(""); const [signingIn, setSigningIn] = useState(false);
  const [trialKey, setTrialKey] = useState(""); const [trialMessage, setTrialMessage] = useState(""); const [trialActive, setTrialActive] = useState(validStoredTrial); const [activatingTrial, setActivatingTrial] = useState(false);
  const [accessMessage, setAccessMessage] = useState(""); const [refreshingAccess, setRefreshingAccess] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { if (data.session) { clearTrialSession(); setTrialActive(false); } setSession(data.session); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => { if (next) { clearTrialSession(); setTrialActive(false); } setSession(next); });
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) return;
    const metadata = session.user.app_metadata ?? {};
    const role = String(metadata.role ?? "").toLowerCase();
    const facilityId = String(metadata.facility_id ?? "").trim();
    if (role !== "dev" && !facilityId) {
      localStorage.removeItem("buyer-dash-organization");
      localStorage.removeItem("buyer-dash-facility");
      sessionStorage.removeItem("buyer-dash-pending-page");
    }
  }, [session]);

  if (!ready) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><p>Restoring your secure session…</p></div></div>;
  if (!authConfigured) return <>{children}</>;
  if (trialActive && !session) return <>{children}</>;
  if (!session) return <div className="auth-screen"><div className="auth-stage"><section className="auth-intro"><div className="brand hero-brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">DoobieLogic operations</div><h1>One workspace.<br/>Every cannabis operation.</h1><p>Retail buying, inventory, compliance, production, extraction, commercial operations and the DEV Sandbox stay behind one secure access context.</p><div className="auth-proof"><span>Retail Ops</span><span>Production Ops</span><span>Commercial Ops</span><span>Data & Compliance</span></div></section><section className="auth-card"><form onSubmit={async event => {
    event.preventDefault(); setMessage(""); setSigningIn(true);
    const value = login.trim(); const email = value.includes("@") ? value.toLocaleLowerCase() : `${value.toLocaleLowerCase()}@users.doobielogic.io`;
    localStorage.removeItem("buyer-dash-organization"); localStorage.removeItem("buyer-dash-facility"); clearTrialSession();
    const result = await supabase!.auth.signInWithPassword({ email, password }); if (result.error) setMessage(result.error.message); setSigningIn(false);
  }}><div className="eyebrow">Secure operations login</div><h2>Welcome back</h2><p>Use your existing username and password.</p><label>Username or email<input autoComplete="username" value={login} onChange={event => setLogin(event.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} /></label><button className="primary" type="submit" disabled={signingIn}>{signingIn ? "Signing in…" : "Sign in"}</button><button className="link-button" type="button" onClick={async () => { const value = login.trim(); if (!value.includes("@")) return setMessage("Legacy usernames keep their existing password. An administrator can reset it from Users & Access."); const { error } = await supabase!.auth.resetPasswordForEmail(value, { redirectTo: `${window.location.origin}/reset-password` }); setMessage(error?.message ?? "Password reset email sent."); }}>Forgot password?</button>{message ? <div className="form-error">{message}</div> : null}</form>
    <details className="trial-entry"><summary>Kicking the tires? Enter a trial key</summary><form onSubmit={async event => { event.preventDefault(); setTrialMessage(""); setActivatingTrial(true); try { const result = await apiPost<TrialActivation>("/api/v1/trial/activate", { trial_key: trialKey.trim() }); sessionStorage.setItem("buyer-dash-trial-token", result.token); sessionStorage.setItem("buyer-dash-trial-expires", result.expires_at); localStorage.setItem("buyer-dash-organization", result.organization.id); localStorage.setItem("buyer-dash-facility", result.facility.id); setTrialActive(true); } catch(error) { setTrialMessage(error instanceof Error ? error.message : "Trial activation failed."); } finally { setActivatingTrial(false); } }}><label>Trial key<input type="password" value={trialKey} onChange={event=>setTrialKey(event.target.value)} /></label><button className="secondary" type="submit" disabled={!trialKey.trim()||activatingTrial}>{activatingTrial?"Activating…":"Activate 24-hour trial"}</button>{trialMessage?<div className="form-error">{trialMessage}</div>:null}</form></details>
  </section></div></div>;

  const metadata = session.user.app_metadata ?? {};
  const sessionRole = String(metadata.role ?? "").toLowerCase();
  const sessionFacilityId = String(metadata.facility_id ?? "").trim();
  if (sessionRole !== "dev" && !sessionFacilityId) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">Access context</div><h2>No facility workspace access</h2><p>Your account is active, but no facility is assigned to it. An organization administrator can assign one or more facilities from User Management.</p><p className="source-caption">This does not grant or guess a facility automatically. Once access is assigned, refresh your secure session here.</p><button className="primary" type="button" disabled={refreshingAccess} onClick={async () => { setAccessMessage(""); setRefreshingAccess(true); const { data, error } = await supabase!.auth.refreshSession(); if (error) setAccessMessage(error.message); else setSession(data.session); setRefreshingAccess(false); }}>{refreshingAccess ? "Refreshing access…" : "Refresh access"}</button><button className="secondary" type="button" onClick={async () => { localStorage.removeItem("buyer-dash-organization"); localStorage.removeItem("buyer-dash-facility"); await supabase!.auth.signOut(); }}>Sign out</button>{accessMessage ? <div className="form-error">{accessMessage}</div> : null}</div></div>;

  return <PasswordGate><LegalGate>{children}</LegalGate></PasswordGate>;
}
