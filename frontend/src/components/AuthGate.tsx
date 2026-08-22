import type { Session } from "@supabase/supabase-js";
import { useEffect, useState, type PropsWithChildren } from "react";
import { authConfigured, supabase } from "../lib/supabase";
import { LegalGate } from "./LegalGate";
import { PasswordGate } from "./PasswordGate";

export function AuthGate({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!authConfigured);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  if (!ready) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>BD</span><strong>Buyer Dash</strong></div><p>Restoring your secure session…</p></div></div>;
  if (!authConfigured) return <>{children}</>;
  if (!session) return <div className="auth-screen"><div className="auth-stage"><section className="auth-intro"><div className="brand hero-brand"><span>BD</span><strong>Buyer Dash</strong></div><div className="eyebrow">DoobieLogic operations</div><h1>One workspace.<br/>Every cannabis operation.</h1><p>Retail buying, inventory, production, extraction, compliance, commercial operations and the DEV Sandbox stay behind the same access context you built in Buyer Dash.</p><div className="auth-proof"><span>Retail Ops</span><span>Production Ops</span><span>Commercial Ops</span><span>Data & Compliance</span></div></section><form className="auth-card" onSubmit={async event => {
    event.preventDefault(); setMessage(""); setSigningIn(true);
    const value = login.trim();
    const email = value.includes("@") ? value.casefold?.() ?? value.toLocaleLowerCase() : `${value.toLocaleLowerCase()}@users.doobielogic.io`;
    const result = await supabase!.auth.signInWithPassword({ email, password });
    if (result.error) setMessage(result.error.message);
    setSigningIn(false);
  }}><div className="eyebrow">Secure operations login</div><h2>Welcome back</h2><p>Use the same Buyer Dash username and password you already had.</p><label>Username or email<input autoComplete="username" value={login} onChange={event => setLogin(event.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} /></label><button className="primary" type="submit" disabled={signingIn}>{signingIn ? "Signing in…" : "Sign in"}</button><button className="link-button" type="button" onClick={async () => { const value = login.trim(); if (!value.includes("@")) return setMessage("Legacy usernames keep their existing password. An administrator can reset it from Users & Access."); const { error } = await supabase!.auth.resetPasswordForEmail(value, { redirectTo: `${window.location.origin}/reset-password` }); setMessage(error?.message ?? "Password reset email sent."); }}>Forgot password?</button>{message ? <div className="form-error">{message}</div> : null}</form></div></div>;
  return <PasswordGate><LegalGate>{children}</LegalGate></PasswordGate>;
}
