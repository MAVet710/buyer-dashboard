import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { supabase } from "../lib/supabase";

type AccountContext = { user: { display_name: string; email: string; role: string; must_change_password: boolean } };

function syncStoredContextFromSession(session: Awaited<ReturnType<NonNullable<typeof supabase>["auth"]["getSession"]>>["data"]["session"]): void {
  const metadata = session?.user.app_metadata ?? {};
  const organizationId = String(metadata.organization_id ?? "").trim();
  const facilityId = String(metadata.facility_id ?? "").trim();
  if (organizationId) localStorage.setItem("buyer-dash-organization", organizationId);
  else localStorage.removeItem("buyer-dash-organization");
  if (facilityId) localStorage.setItem("buyer-dash-facility", facilityId);
  else localStorage.removeItem("buyer-dash-facility");
}

async function loadAccountContext(signal?: AbortSignal): Promise<AccountContext> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    try {
      return await apiGet<AccountContext>("/api/v1/account/context", controller.signal);
    } catch (firstError) {
      if (signal?.aborted) throw firstError;
      if (timedOut) throw new Error("Workspace restoration timed out. Check your connection and retry.");
      if (!supabase) throw firstError;

      const refreshed = await supabase.auth.refreshSession();
      if (refreshed.error || !refreshed.data.session) throw firstError;

      // A stale facility in localStorage used to override the newly refreshed
      // Supabase access metadata and trap valid users on Access Context
      // Unavailable. Only reset that browser override when the API explicitly
      // says the supplied workspace context is invalid.
      if (firstError instanceof ApiError && (firstError.status === 400 || firstError.status === 403)) {
        syncStoredContextFromSession(refreshed.data.session);
      }
      return await apiGet<AccountContext>("/api/v1/account/context", controller.signal);
    }
  } catch (error) {
    if (timedOut) throw new Error("Workspace restoration timed out. Check your connection and retry.");
    throw error;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export function PasswordGate({ children }: PropsWithChildren) {
  const client = useQueryClient();
  const context = useQuery({
    queryKey: ["account-context", "password-gate"],
    queryFn: ({ signal }) => loadAccountContext(signal),
    retry: false,
    staleTime: 30_000,
  });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [recovering, setRecovering] = useState(false);

  async function recoverWorkspace() {
    setRecovering(true);
    setMessage("");
    try {
      if (supabase) {
        const refreshed = await supabase.auth.refreshSession();
        if (refreshed.error) throw refreshed.error;
        if (refreshed.data.session) syncStoredContextFromSession(refreshed.data.session);
      }
      await client.invalidateQueries({ queryKey: ["account-context"] });
      await context.refetch();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "DoobieLogic could not restore the workspace yet.");
    } finally {
      setRecovering(false);
    }
  }

  if (context.isLoading) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">Secure workspace</div><h2>Restoring your workspace</h2><p>Refreshing your session and facility access. This will automatically stop and offer recovery if the API does not respond.</p></div></div>;
  if (context.isError) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">Workspace recovery</div><h1>Access context unavailable</h1><p>{context.error.message}</p><p className="source-caption">Your login is still active. DoobieLogic can refresh the session, clear a stale facility selection, and retry without making you sign in again.</p><button className="primary" type="button" disabled={recovering} onClick={() => void recoverWorkspace()}>{recovering ? "Recovering workspace…" : "Recover workspace"}</button><button className="secondary" type="button" onClick={() => supabase?.auth.signOut()}>Sign out</button>{message ? <div className="form-error">{message}</div> : null}</div></div>;
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
      setMessage(error instanceof Error ? error.message : "Password changed, but DoobieLogic could not finish the account update.");
    } finally { setSaving(false); }
  }}>
    <div className="brand"><span>DL</span><strong>DoobieLogic</strong></div>
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
