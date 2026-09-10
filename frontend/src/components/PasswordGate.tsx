import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { ApiError, apiGet, apiPost, refreshApiSession } from "../lib/api";
import { supabase } from "../lib/supabase";
import { isTransientWorkspaceError, retryWorkspace, workspaceAttempt } from "../lib/workspaceRecovery";

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
  return workspaceAttempt(async attemptSignal => {
    try {
      return await apiGet<AccountContext>("/api/v1/account/context", attemptSignal);
    } catch (firstError) {
      // authorizedFetch already handles expired tokens. A transport failure is
      // not evidence of stale credentials or of a bad facility selection.
      if (attemptSignal.aborted || !supabase || !(firstError instanceof ApiError)
          || (firstError.status !== 400 && firstError.status !== 403)) throw firstError;
      const refreshed = await refreshApiSession(attemptSignal);
      if (!refreshed || refreshed.error || !refreshed.data.session) throw firstError;
      attemptSignal.throwIfAborted();
      syncStoredContextFromSession(refreshed.data.session);
      return apiGet<AccountContext>("/api/v1/account/context", attemptSignal);
    }
  }, signal);
}

export function PasswordGate({ children, userId }: PropsWithChildren<{ userId: string }>) {
  const client = useQueryClient();
  const context = useQuery({
    queryKey: ["account-context", "password-gate", userId],
    queryFn: ({ signal }) => loadAccountContext(signal),
    retry: retryWorkspace,
    retryDelay: attempt => Math.min(1000 * 2 ** attempt, 3000),
    refetchOnReconnect: true,
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
      // One retry path; invalidation plus refetch previously cancelled and
      // restarted the same request, while also refreshing healthy sessions.
      await context.refetch({ throwOnError: true });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "DoobieLogic could not restore the workspace yet.");
    } finally {
      setRecovering(false);
    }
  }

  if (context.isLoading) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">Secure workspace</div><h2>Restoring your workspace</h2><p>Connecting securely to your facility. If the service is waking up, this can take about a minute. We’ll retry automatically.</p></div></div>;
  if (context.isError && (!context.data || !isTransientWorkspaceError(context.error))) return <div className="auth-screen"><div className="auth-card"><div className="brand"><span>DL</span><strong>DoobieLogic</strong></div><div className="eyebrow">Workspace recovery</div><h1>Access context unavailable</h1><p>{context.error.message}</p><p className="source-caption">We could not confirm workspace access yet. Retry to reconnect; your facility selection is only reset if the server reports an access-context problem.</p><button className="primary" type="button" disabled={recovering} onClick={() => void recoverWorkspace()}>{recovering ? "Recovering workspace…" : "Recover workspace"}</button><button className="secondary" type="button" onClick={() => supabase?.auth.signOut()}>Sign out</button>{message ? <div className="form-error">{message}</div> : null}</div></div>;
  if (!context.data) return <div className="auth-screen"><div className="auth-card"><h2>Waiting for a connection</h2><p>Your workspace will retry when the connection returns.</p></div></div>;
  if (!context.data.user.must_change_password) return <>
    {context.isError ? <div role="status" className="workspace-connection-notice">Connection interrupted. Your workspace is still open. <button type="button" disabled={context.isFetching} onClick={() => void recoverWorkspace()}>{context.isFetching ? "Reconnecting…" : "Reconnect"}</button></div> : null}
    {children}
  </>;

  return <div className="auth-screen"><form className="auth-card password-card" onSubmit={async event => {
    event.preventDefault();
    setMessage("");
    if (password.length < 12) return setMessage("Your new password must contain at least 12 characters.");
    if (password !== confirm) return setMessage("The passwords do not match.");
    setSaving(true);
    try {
      await apiPost("/api/v1/account/password", { password });
      await client.invalidateQueries();
      await context.refetch();
      setPassword(""); setConfirm("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "DoobieLogic could not finish the password change.");
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
