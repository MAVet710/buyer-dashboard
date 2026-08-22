import type { Session } from "@supabase/supabase-js";
import { useEffect, useState, type PropsWithChildren } from "react";
import { authConfigured, supabase } from "../lib/supabase";
import { LegalGate } from "./LegalGate";

export function AuthGate({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null); const [ready, setReady] = useState(!authConfigured); const [login, setLogin] = useState(""); const [password, setPassword] = useState(""); const [message, setMessage] = useState("");
  useEffect(() => { if (!supabase) return; supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); }); const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next)); return () => data.subscription.unsubscribe(); }, []);
  if (!ready) return <div className="auth-screen">Restoring your secure session…</div>;
  if (!authConfigured) return <>{children}</>;
  if (!session) return <div className="auth-screen"><form className="auth-card" onSubmit={async event => { event.preventDefault(); setMessage(""); const value = login.trim(); const email = value.includes("@") ? value : `${value.toLocaleLowerCase()}@users.doobielogic.io`; const result = await supabase!.auth.signInWithPassword({ email, password }); if (result.error) setMessage(result.error.message); }}><div className="brand"><span>BD</span><strong>Buyer Dash</strong></div><h1>Operations login</h1><p>Sign in to your assigned organization and facility.</p><label>Username or email<input autoComplete="username" value={login} onChange={event => setLogin(event.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} /></label><button className="primary" type="submit">Sign in</button><button className="link-button" type="button" onClick={async () => { const email = login.trim(); if (!email.includes("@")) return setMessage("Legacy usernames keep their existing password. Ask an administrator if it needs to be reset."); const { error } = await supabase!.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/reset-password` }); setMessage(error?.message ?? "Password reset email sent."); }}>Forgot password?</button>{message ? <div className="form-error">{message}</div> : null}</form></div>;
  return <LegalGate>{children}</LegalGate>;
}
