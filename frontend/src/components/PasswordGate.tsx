import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { apiGet, apiPost } from "../lib/api";
import { supabase } from "../lib/supabase";

type AccountContext = { user: { display_name: string; email: string; role: string; must_change_password: boolean } };

export function PasswordGate({ children }: PropsWithChildren) {
  const client = useQueryClient();
  const context = useQuery({ queryKey: ["account-context", "password-gate"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  if (context.isLoading) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>BD</span><strong>Buyer Dash</strong></div><p>Restoring your secure workspace…</p></div></div>;
  if (context.isError) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>BD</span><strong>Buyer Dash</strong></div><h1>Access context unavailable</h1><p>{context.error.message}</p><button className="secondary" onClick={() => supabase?.auth.signOut()}>Sign out</button></div></div>;
  if (!context.data?.user.must_change_password) return <>{children}</>;

  return <div className="auth-screen"><form className="auth-card password-card" onSubmit={async event => {
    event.preventDefault();
    setMessage("");
    if (password.length < 12) return setMessage("Your new password must contain at least 12 characters.");
    if (password !== confirm) return setMessage("The passwords do not match.");
    setSaving(true);
    const result = await supabase!.auth.updateUser({ password });
    if (result.error) { setSaving(false); return setMessage(result.error.message); }
    try {
      await apiPost("/api/v1/account/password-changed", {});
      await client.invalidateQueries();
      await context.refetch();
      setPassword(""); setConfirm("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Password changed, but Buyer Dash could not finish the account update.");
    } finally { setSaving(false); }
  }}>
    <div className="brand"><span>BD</span><strong>Buyer Dash</strong></div>
    <div className="eyebrow">First login security</div>
    <h1>Create your private password</h1>
    <p>Your temporary password worked. Replace it now before entering the operations workspace.</p>
    <label>New password<input type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></label>
    <label>Confirm new password<input type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} /></label>
    <button className="primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Set password & continue"}</button>
    <button className="link-button" type="button" onClick={() => supabase?.auth.signOut()}>Sign out</button>
    {message ? <div className="form-error">{message}</div> : null}
  </form></div>;
}
