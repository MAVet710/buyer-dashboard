import { useCallback, useEffect, useState } from "react";
import { listOfflineMutations } from "../lib/offlineQueue";

export function OfflineStatusBar() {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [queued, setQueued] = useState(0);

  const refreshQueue = useCallback(async () => {
    const organizationId = localStorage.getItem("buyer-dash-organization") ?? "";
    const facilityId = localStorage.getItem("buyer-dash-facility") ?? "";
    if (!organizationId || !facilityId) {
      setQueued(0);
      return;
    }
    try {
      const rows = await listOfflineMutations(organizationId, facilityId);
      setQueued(rows.length);
    } catch {
      setQueued(0);
    }
  }, []);

  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    const handleQueue = () => { void refreshQueue(); };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("storage", handleQueue);
    window.addEventListener("doobielogic:offline-queue-changed", handleQueue);
    void refreshQueue();
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("storage", handleQueue);
      window.removeEventListener("doobielogic:offline-queue-changed", handleQueue);
    };
  }, [refreshQueue]);

  if (online && queued === 0) return null;

  return (
    <div className="offline-status-bar" role="status" aria-live="polite">
      <strong>{online ? "Connection restored" : "Offline mode"}</strong>
      <span>
        {queued > 0 ? `${queued} local capture${queued === 1 ? "" : "s"} waiting for verified replay.` : "Local capture is available only for approved offline-safe workflows."}
      </span>
      {!online && <span>Regulatory, provider, manifest, and transfer writes remain blocked while offline.</span>}
    </div>
  );
}
