// A free API can need about a minute to wake. Each attempt remains bounded,
// including time spent waiting for the auth SDK before fetch even starts.
export const WORKSPACE_ATTEMPT_TIMEOUT_MS = 30_000;
export const WORKSPACE_RETRIES = 2;

export class WorkspaceTimeoutError extends Error {
  constructor() {
    super("The workspace service is taking longer than expected to respond. Try again shortly.");
    this.name = "WorkspaceTimeoutError";
  }
}

export function isTransientWorkspaceError(error: unknown): boolean {
  if (error instanceof WorkspaceTimeoutError || error instanceof TypeError) return true;
  const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
  return status === 408 || status === 429 || status >= 500;
}

export function abortable<T>(operation: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
  if (!signal) return operation();
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    Promise.resolve().then(() => {
      if (signal.aborted) throw signal.reason ?? new DOMException("Aborted", "AbortError");
      return operation();
    }).then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
  });
}

export async function workspaceAttempt<T>(operation: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => controller.abort(new WorkspaceTimeoutError()), WORKSPACE_ATTEMPT_TIMEOUT_MS);
  try {
    return await abortable(() => operation(controller.signal), controller.signal);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export function retryWorkspace(failureCount: number, error: unknown): boolean {
  return failureCount < WORKSPACE_RETRIES && isTransientWorkspaceError(error);
}
