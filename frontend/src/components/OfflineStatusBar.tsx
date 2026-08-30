import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPostIdempotent } from "../lib/api";
import { listOfflineMutations, replayOfflineMutations } from "../lib/offlineQueue";

export function OfflineStatusBar() {
  const client = useQueryClient();
  const replaying = useRef(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [queued, setQueued] = useState(0);
  const [conflicts, setConflicts] = useState(0);
  const [failed, setFailed] = useState(0);

  const scope = useCallback(() => ({
    organizationId: localStorage.getItem("buyer-dash-organization") ?? "",
    facilityId: localStorage.getItem("buyer-dash-facility") ?? "",
  }), []);

  const refreshQueue = useCallback(async () => {
    const { organizationId, facilityId } = scope();
    if (!organizationId || !facilityId) {
      setQueued(0);
      setConflicts(0);
      setFailed(0);
      return;
    }
    try {
      const rows = await listOfflineMutations(organizationId, facilityId);
      setQueued(rows.filter(row => row.status === "queued" || row.status === "replaying").length);
      setConflicts(rows.filter(row => row.status === "conflict").length);
      setFailed(rows.filter(row => row.status === "failed").length);
    } catch {
      setQueued(0);
      setConflicts(0);
      setFailed(0);
    }
  }, [scope]);

  const flushQueue = useCallback(async () => {
    if (!navigator.onLine || replaying.current) return;
    const { organizationId, facilityId } = scope();
    if (!organizationId || !facilityId) return;
    replaying.current = true;
    try {
      const result = await replayOfflineMutations(
        organizationId,
        facilityId,
        entry => apiPostIdempotent(entry.path, entry.body, entry.idempotencyKey).then(() => undefined),
      );
      if (result.replayed > 0) {
        await Promise.all([
          client.invalidateQueries({ queryKey: ["audits"] }),
          client.invalidateQueries({ queryKey: ["audit"] }),
          client.invalidateQueries({ queryKey: ["audit-inventory"] }),
          client.invalidateQueries({ queryKey: ["inventory"] }),
        ]);
      }
    } finally {
      replaying.current = false;
      await refreshQueue();
    }
  }, [client, refreshQueue, scope]);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      void flushQueue();
    };
    const handleOffline = () => setOnline(false);
    const handleQueue = () => { void refreshQueue(); };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("storage", handleQueue);
    window.addEventListener("doobielogic:offline-queue-changed", handleQueue);
    void refreshQueue();
    if (navigator.onLine) void flushQueue();
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("storage", handleQueue);
      window.removeEventListener("doobielogic:offline-queue-changed", handleQueue);
    };
  }, [flushQueue, refreshQueue]);

  if (online && queued === 0 && conflicts === 0 && failed === 0) return null;

  return (
    <div className="offline-status-bar" role="status" aria-live="polite">
      <strong>{online ? "Offline capture sync" : "Offline mode"}</strong>
      <span>
        {queued > 0 ? `${queued} local capture${queued === 1 ? "" : "s"} waiting for verified replay.` : "No captures are waiting to replay."}
      </span>
      {conflicts > 0 ? <span>{conflicts} capture{conflicts === 1 ? " needs" : "s need"} operator review before it can be applied.</span> : null}
      {failed > 0 ? <span>{failed} capture{failed === 1 ? " has" : "s have"} stopped retrying and needs review.</span> : null}
      {!online && <span>Regulatory, provider, manifest, and transfer writes remain blocked while offline.</span>}
    </div>
  );
}
