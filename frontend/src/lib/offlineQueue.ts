const DB_NAME = "doobielogic-offline";
const DB_VERSION = 1;
const STORE_NAME = "mutations";
const MAX_AUTOMATIC_ATTEMPTS = 5;

export type OfflineMutationStatus = "queued" | "replaying" | "conflict" | "failed";
export type OfflineSafetyClass = "local_draft" | "physical_capture";

export type OfflineMutation = {
  id: string;
  method: "POST";
  path: string;
  body: unknown;
  organizationId: string;
  facilityId: string;
  safetyClass: OfflineSafetyClass;
  idempotencyKey: string;
  createdAt: string;
  updatedAt: string;
  attempts: number;
  status: OfflineMutationStatus;
  lastError: string;
};

export type QueueOfflineMutationInput = {
  path: string;
  body: unknown;
  organizationId: string;
  facilityId: string;
  safetyClass: OfflineSafetyClass;
  idempotencyKey?: string;
};

const REGULATORY_BLOCKLIST = [
  "/metrc",
  "/regulatory",
  "/traceability",
  "/dispatch",
  "/provider",
  "/integrations",
  "/manifest",
  "/transfer",
];

function normalizePath(path: string): string {
  const value = String(path || "").trim();
  if (!value.startsWith("/api/")) throw new Error("Offline mutations must target a DoobieLogic API path.");
  return value;
}

export function isOfflineReplayAllowed(path: string, safetyClass: OfflineSafetyClass): boolean {
  let normalized = "";
  try {
    normalized = normalizePath(path).toLowerCase();
  } catch {
    return false;
  }
  if (safetyClass !== "local_draft" && safetyClass !== "physical_capture") return false;
  return !REGULATORY_BLOCKLIST.some(fragment => normalized.includes(fragment));
}

function assertScope(organizationId: string, facilityId: string): void {
  if (!organizationId.trim() || !facilityId.trim()) {
    throw new Error("Offline capture requires an explicit organization and facility scope.");
  }
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB is unavailable in this browser."));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("scope", ["organizationId", "facilityId"], { unique: false });
        store.createIndex("status", "status", { unique: false });
        store.createIndex("createdAt", "createdAt", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open the offline queue."));
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Offline queue operation failed."));
  });
}

async function writeMutation(entry: OfflineMutation): Promise<void> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    await requestResult(store.put(entry));
  } finally {
    database.close();
  }
}

export async function queueOfflineMutation(input: QueueOfflineMutationInput): Promise<OfflineMutation> {
  const path = normalizePath(input.path);
  assertScope(input.organizationId, input.facilityId);
  if (!isOfflineReplayAllowed(path, input.safetyClass)) {
    throw new Error("This action cannot be queued offline because it may change regulatory or provider state.");
  }
  const now = new Date().toISOString();
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `offline-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const entry: OfflineMutation = {
    id,
    method: "POST",
    path,
    body: input.body,
    organizationId: input.organizationId.trim(),
    facilityId: input.facilityId.trim(),
    safetyClass: input.safetyClass,
    idempotencyKey: input.idempotencyKey?.trim() || id,
    createdAt: now,
    updatedAt: now,
    attempts: 0,
    status: "queued",
    lastError: "",
  };
  await writeMutation(entry);
  window.dispatchEvent(new CustomEvent("doobielogic:offline-queue-changed"));
  return entry;
}

export async function listOfflineMutations(organizationId?: string, facilityId?: string): Promise<OfflineMutation[]> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const rows = await requestResult(store.getAll()) as OfflineMutation[];
    return rows
      .filter(row => (!organizationId || row.organizationId === organizationId) && (!facilityId || row.facilityId === facilityId))
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  } finally {
    database.close();
  }
}

export async function removeOfflineMutation(id: string): Promise<void> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    await requestResult(transaction.objectStore(STORE_NAME).delete(id));
  } finally {
    database.close();
  }
  window.dispatchEvent(new CustomEvent("doobielogic:offline-queue-changed"));
}

function errorStatus(error: unknown): number {
  if (!error || typeof error !== "object" || !("status" in error)) return 0;
  const value = Number((error as { status?: unknown }).status);
  return Number.isFinite(value) ? value : 0;
}

function errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return String(error || "Replay failed.");
}

export async function replayOfflineMutations(
  organizationId: string,
  facilityId: string,
  replay: (entry: OfflineMutation) => Promise<void>,
): Promise<{ replayed: number; conflicts: number; failed: number }> {
  assertScope(organizationId, facilityId);
  const rows = await listOfflineMutations(organizationId, facilityId);
  let replayed = 0;
  let conflicts = 0;
  let failed = 0;

  for (const entry of rows) {
    if (entry.status === "conflict" || entry.status === "failed") continue;
    if (!isOfflineReplayAllowed(entry.path, entry.safetyClass)) {
      await writeMutation({ ...entry, status: "failed", updatedAt: new Date().toISOString(), lastError: "Replay blocked by current offline safety policy." });
      failed += 1;
      continue;
    }

    const replaying = { ...entry, status: "replaying" as const, updatedAt: new Date().toISOString() };
    await writeMutation(replaying);
    try {
      await replay(replaying);
      await removeOfflineMutation(entry.id);
      replayed += 1;
    } catch (error) {
      const attempts = entry.attempts + 1;
      const status = errorStatus(error);
      const conflict = status === 409 || status === 412;
      const nextStatus: OfflineMutationStatus = conflict
        ? "conflict"
        : attempts >= MAX_AUTOMATIC_ATTEMPTS ? "failed" : "queued";
      await writeMutation({
        ...entry,
        attempts,
        status: nextStatus,
        updatedAt: new Date().toISOString(),
        lastError: errorText(error),
      });
      if (conflict) conflicts += 1;
      else if (nextStatus === "failed") failed += 1;
    }
  }

  window.dispatchEvent(new CustomEvent("doobielogic:offline-queue-changed"));
  return { replayed, conflicts, failed };
}
